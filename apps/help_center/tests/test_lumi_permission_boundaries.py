from __future__ import annotations

from datetime import time

from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.models import CustomUser, SalonManager, Stylist
from apps.help_center.actions.manager_operations import _manager_salon
from apps.help_center.actions.stylist_operations import run_stylist_read_operation
from apps.salons.models import (
    Salon,
    SalonMembership,
    SalonMembershipStatus,
    StaffDashboardPermission,
)
from apps.stylists.models import StylistSchedule


class LumiPermissionBoundaryTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _manager(self, mobile: str):
        user = CustomUser.objects.create_user(
            mobile_number=mobile,
            name="مدیر",
            family=mobile[-2:],
        )
        manager = SalonManager.objects.create(user=user, is_active=True)
        return user, manager

    def test_multi_salon_manager_is_not_silently_scoped_to_first_salon(self):
        user, manager = self._manager("09121000001")
        first = Salon.objects.create(
            salon_name="سالن آفتاب",
            salon_manager=manager,
            is_active=True,
        )
        second = Salon.objects.create(
            salon_name="سالن مهتاب",
            salon_manager=manager,
            is_active=True,
        )
        request = self.factory.get("/")
        request.user = user

        with self.assertRaises(ValidationError) as exc:
            _manager_salon(request)
        self.assertIn("نام مجموعه", str(exc.exception))

        resolved = _manager_salon(
            request,
            message="نوبت‌های امروز سالن مهتاب رو بگو",
        )
        self.assertEqual(resolved.pk, second.pk)
        self.assertNotEqual(resolved.pk, first.pk)

    def test_manager_cannot_resolve_another_managers_salon_by_id(self):
        user, manager = self._manager("09121000002")
        own = Salon.objects.create(
            salon_name="مجموعه خودم",
            salon_manager=manager,
            is_active=True,
        )
        _, other_manager = self._manager("09121000003")
        other = Salon.objects.create(
            salon_name="مجموعه دیگر",
            salon_manager=other_manager,
            is_active=True,
        )
        request = self.factory.get("/")
        request.user = user

        self.assertEqual(_manager_salon(request, salon_id=own.pk).pk, own.pk)
        with self.assertRaises(ValidationError):
            _manager_salon(request, salon_id=other.pk)

    def test_stylist_without_client_permission_cannot_read_appointments(self):
        _, manager = self._manager("09121000004")
        salon = Salon.objects.create(
            salon_name="سالن تست دسترسی",
            salon_manager=manager,
            is_active=True,
        )
        stylist_user = CustomUser.objects.create_user(
            mobile_number="09121000005",
            name="سارا",
            family="رضایی",
        )
        stylist = Stylist.objects.create(user=stylist_user, is_active=True)
        membership = SalonMembership.objects.create(
            salon=salon,
            stylist=stylist,
            status=SalonMembershipStatus.ACTIVE,
        )
        StaffDashboardPermission.objects.create(
            membership=membership,
            can_view_own_clients=False,
        )

        request = self.factory.get("/")
        request.user = stylist_user
        request.session = {"active_stylist_salon_id": salon.pk}

        result = run_stylist_read_operation(
            request,
            "نوبت‌های امروزم رو نشون بده",
        )

        self.assertEqual(result["result"]["type"], "permission_denied")
        self.assertEqual(
            result["result"]["permission"],
            "can_view_own_clients",
        )
        self.assertIn("دسترسی", result["answer"])

    def test_stylist_schedule_is_scoped_to_active_authorized_salon(self):
        _, manager1 = self._manager("09121000006")
        salon1 = Salon.objects.create(
            salon_name="سالن یک",
            salon_manager=manager1,
            is_active=True,
        )
        _, manager2 = self._manager("09121000007")
        salon2 = Salon.objects.create(
            salon_name="سالن دو",
            salon_manager=manager2,
            is_active=True,
        )
        stylist_user = CustomUser.objects.create_user(
            mobile_number="09121000008",
            name="نیما",
            family="صالحی",
        )
        stylist = Stylist.objects.create(user=stylist_user, is_active=True)

        membership1 = SalonMembership.objects.create(
            salon=salon1,
            stylist=stylist,
            status=SalonMembershipStatus.ACTIVE,
        )
        membership2 = SalonMembership.objects.create(
            salon=salon2,
            stylist=stylist,
            status=SalonMembershipStatus.ACTIVE,
        )
        StaffDashboardPermission.objects.create(membership=membership1)
        StaffDashboardPermission.objects.create(membership=membership2)

        today = timezone.localdate()
        StylistSchedule.objects.create(
            salon=salon1,
            stylist=stylist,
            date=today,
            start_time=time(9, 0),
            end_time=time(14, 0),
        )
        StylistSchedule.objects.create(
            salon=salon2,
            stylist=stylist,
            date=today,
            start_time=time(16, 0),
            end_time=time(21, 0),
        )

        request = self.factory.get("/")
        request.user = stylist_user
        request.session = {"active_stylist_salon_id": salon2.pk}

        result = run_stylist_read_operation(
            request,
            "امروز تا چه ساعتی کار دارم؟",
        )

        self.assertEqual(result["result"]["end_time"], "21:00")
        self.assertNotIn("14:00", result["answer"])
