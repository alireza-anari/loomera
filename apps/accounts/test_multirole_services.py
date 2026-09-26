"""Database contract for shared role and workspace authorization services."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from apps.accounts.models import Customer, SalonManager, Stylist
from apps.accounts.services.access import (
    capabilities_for,
    ensure_customer,
    managed_salons,
    resolve_manager_salon,
    resolve_stylist_membership,
    WorkspaceSelectionRequired,
)
from apps.accounts.services.workspaces import Workspace, available_workspaces
from apps.salons.models import SalonMembership, SalonMembershipStatus, StaffDashboardPermission
from tests_stage1_helpers import Stage1DomainFactoryMixin


class MultiroleServiceTests(Stage1DomainFactoryMixin, TestCase):
    def test_active_identity_has_customer_capability_without_customer_profile(self):
        user = self.make_user()

        self.assertEqual(capabilities_for(user), frozenset({"customer"}))
        spaces = available_workspaces(user)
        self.assertEqual([(space.kind, space.salon_id) for space in spaces],
                         [("customer", None)])
        self.assertTrue(all(isinstance(space.label, str) and space.label for space in spaces))
        self.assertFalse(Customer.objects.filter(user=user).exists())

    def test_stylist_profile_adds_one_global_workspace_without_membership(self):
        user = self.make_user()
        Stylist.objects.create(user=user)  # A new profile is inactive until onboarding.

        self.assertEqual(capabilities_for(user), frozenset({"customer", "stylist"}))
        spaces = available_workspaces(user)
        self.assertEqual([(space.kind, space.salon_id) for space in spaces],
                         [("customer", None), ("stylist", None)])
        self.assertFalse(SalonMembership.objects.filter(stylist__user=user).exists())

    def test_manager_profile_with_no_salon_has_onboarding_workspace(self):
        user = self.make_user()
        SalonManager.objects.create(user=user)  # The historical default is inactive.

        self.assertEqual(capabilities_for(user), frozenset({"customer", "manager"}))
        self.assertFalse(managed_salons(user).exists())
        self.assertIsNone(resolve_manager_salon(user))
        spaces = available_workspaces(user)
        self.assertEqual([(space.kind, space.salon_id) for space in spaces],
                         [("customer", None), ("manager", None)])

    def test_manager_onboarding_requires_current_manager_profile(self):
        customer_only = self.make_user()
        deleted_manager = self.make_user()
        manager = SalonManager.objects.create(user=deleted_manager)
        self.assertEqual(deleted_manager.salon_manager_profile.pk, manager.pk)
        SalonManager.objects.filter(user=deleted_manager).delete()

        for user in (customer_only, deleted_manager):
            with self.subTest(user=user), self.assertRaises(PermissionDenied):
                resolve_manager_salon(user)

    def test_one_draft_manager_salon_is_owned_and_selectable(self):
        user = self.make_user()
        manager = SalonManager.objects.create(user=user)
        salon = self.make_salon(manager=manager, is_active=False)

        self.assertEqual(list(managed_salons(user)), [salon])
        self.assertEqual(resolve_manager_salon(user).pk, salon.pk)
        self.assertEqual(resolve_manager_salon(user, str(salon.pk)).pk, salon.pk)
        self.assertEqual([(space.kind, space.salon_id) for space in available_workspaces(user)],
                         [("customer", None), ("manager", salon.pk)])

    def test_two_manager_salons_require_explicit_selection(self):
        user = self.make_user()
        manager = SalonManager.objects.create(user=user)
        first = self.make_salon(manager=manager)
        second = self.make_salon(manager=manager, is_active=False)

        with self.assertRaises(WorkspaceSelectionRequired):
            resolve_manager_salon(user)
        self.assertEqual(resolve_manager_salon(user, second.pk).pk, second.pk)
        self.assertEqual(set(managed_salons(user).values_list("pk", flat=True)),
                         {first.pk, second.pk})
        self.assertEqual([(space.kind, space.salon_id) for space in available_workspaces(user)],
                         [("customer", None), ("manager", first.pk), ("manager", second.pk)])

    def test_manager_and_stylist_capabilities_coexist_without_membership(self):
        user = self.make_user()
        manager = SalonManager.objects.create(user=user)
        Stylist.objects.create(user=user)
        salon = self.make_salon(manager=manager)

        self.assertEqual(capabilities_for(user),
                         frozenset({"customer", "stylist", "manager"}))
        self.assertEqual([(space.kind, space.salon_id) for space in available_workspaces(user)],
                         [("customer", None), ("stylist", None), ("manager", salon.pk)])
        with self.assertRaises(PermissionDenied):
            resolve_stylist_membership(user, salon.pk)
        self.assertFalse(SalonMembership.objects.filter(salon=salon).exists())
        self.assertFalse(StaffDashboardPermission.objects.exists())

    def test_deleted_profile_cannot_survive_related_object_cache(self):
        user = self.make_user()
        stylist = Stylist.objects.create(user=user)
        manager = SalonManager.objects.create(user=user)
        self.assertEqual(user.stylist.pk, stylist.pk)
        self.assertEqual(user.salon_manager_profile.pk, manager.pk)
        Stylist.objects.filter(user=user).delete()
        SalonManager.objects.filter(user=user).delete()

        self.assertEqual(capabilities_for(user), frozenset({"customer"}))
        self.assertEqual([(space.kind, space.salon_id) for space in available_workspaces(user)],
                         [("customer", None)])

    def test_manager_salon_resolution_rejects_foreign_and_malformed_ids(self):
        user = self.make_user()
        owner = SalonManager.objects.create(user=user)
        owned = self.make_salon(manager=owner)
        foreign = self.make_salon(manager=self.make_salon_manager())

        for invalid_id in (foreign.pk, 0, -1, "wrong", "", True, 1.5,
                           Decimal("1.5")):
            with self.subTest(invalid_id=invalid_id), self.assertRaises(PermissionDenied):
                resolve_manager_salon(user, invalid_id)
        self.assertEqual(resolve_manager_salon(user, owned.pk).pk, owned.pk)

    def test_stylist_membership_requires_exact_active_membership(self):
        user = self.make_user()
        stylist = Stylist.objects.create(user=user)
        own_manager = SalonManager.objects.create(user=user)
        active_salon = self.make_salon(manager=own_manager)
        active = SalonMembership.objects.create(
            salon=active_salon, stylist=stylist, status=SalonMembershipStatus.ACTIVE
        )
        other_salon = self.make_salon(manager=self.make_salon_manager())
        paused = SalonMembership.objects.create(
            salon=other_salon, stylist=stylist, status=SalonMembershipStatus.PAUSED
        )
        ended_salon = self.make_salon(manager=self.make_salon_manager())
        ended = SalonMembership.objects.create(
            salon=ended_salon, stylist=stylist, status=SalonMembershipStatus.ENDED
        )
        another_stylist = self.make_stylist()
        foreign_salon = self.make_salon(manager=self.make_salon_manager())
        SalonMembership.objects.create(
            salon=foreign_salon, stylist=another_stylist,
            status=SalonMembershipStatus.ACTIVE,
        )

        self.assertEqual(resolve_stylist_membership(user, active_salon.pk).pk, active.pk)
        for invalid_id in (paused.salon_id, ended.salon_id, foreign_salon.pk,
                           0, -1, "bad", "", True, 1.5, Decimal("1.5")):
            with self.subTest(invalid_id=invalid_id), self.assertRaises(PermissionDenied):
                resolve_stylist_membership(user, invalid_id)
        self.assertEqual(SalonMembership.objects.filter(stylist=stylist).count(), 3)
        self.assertFalse(StaffDashboardPermission.objects.exists())

    def test_inactive_and_anonymous_identities_have_no_access(self):
        inactive = self.make_user(is_active=False)
        manager = SalonManager.objects.create(user=inactive)
        stylist = Stylist.objects.create(user=inactive)
        salon = self.make_salon(manager=manager)
        SalonMembership.objects.create(
            salon=salon, stylist=stylist, status=SalonMembershipStatus.ACTIVE
        )

        for user in (inactive, AnonymousUser()):
            with self.subTest(user=user):
                self.assertEqual(capabilities_for(user), frozenset())
                self.assertEqual(available_workspaces(user), ())
                self.assertFalse(managed_salons(user).exists())
                with self.assertRaises(PermissionDenied):
                    ensure_customer(user)
                with self.assertRaises(PermissionDenied):
                    resolve_manager_salon(user, salon.pk)
                with self.assertRaises(PermissionDenied):
                    resolve_stylist_membership(user, salon.pk)
        self.assertFalse(Customer.objects.filter(user=inactive).exists())

    def test_ensure_customer_creates_once_with_marketing_opted_out(self):
        user = self.make_user()

        first = ensure_customer(user)
        second = ensure_customer(user)

        self.assertEqual(first.pk, user.pk)
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(Customer.objects.filter(user=user).count(), 1)
        self.assertFalse(first.notify_marketing_email)
        self.assertFalse(first.notify_marketing_sms)
        self.assertFalse(first.notify_marketing_whatsapp)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_ensure_customer_preserves_existing_profile_preferences(self):
        user = self.make_user()
        existing = Customer.objects.create(
            user=user, address="Kept address", notify_marketing_email=True,
            notify_marketing_sms=True, notify_marketing_whatsapp=True,
            notify_appointment_sms=False,
        )

        returned = ensure_customer(user)
        existing.refresh_from_db()

        self.assertEqual(returned.pk, existing.pk)
        self.assertEqual(existing.address, "Kept address")
        self.assertTrue(existing.notify_marketing_email)
        self.assertTrue(existing.notify_marketing_sms)
        self.assertTrue(existing.notify_marketing_whatsapp)
        self.assertFalse(existing.notify_appointment_sms)

    def test_workspace_value_is_immutable(self):
        workspace = Workspace("manager", 42, "Salon")

        with self.assertRaises(FrozenInstanceError):
            workspace.salon_id = 43
