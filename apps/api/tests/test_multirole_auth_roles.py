"""Authenticated API should expose all current roles without extra profiles."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Customer, SalonManager, Stylist
from apps.api.v1.auth_serializers import user_role_flags
from tests_stage1_helpers import Stage1DomainFactoryMixin


class MultiroleApiRoleTests(Stage1DomainFactoryMixin, TestCase):
    def test_provider_is_customer_without_customer_record(self):
        user = self.make_user()
        SalonManager.objects.create(user=user, is_active=True)
        Stylist.objects.create(user=user, is_active=True)
        flags = user_role_flags(user)
        self.assertEqual(
            {key: flags[key] for key in ("is_customer", "is_stylist", "is_salon_manager")},
            {"is_customer": True, "is_stylist": True, "is_salon_manager": True},
        )
        self.assertFalse(Customer.objects.filter(user=user).exists())
        self.client.force_login(user)
        response = self.client.get(reverse("api:v1:auth_me"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["user"]["roles"], flags)
        self.assertFalse(Customer.objects.filter(user=user).exists())

    def test_stale_related_cache_does_not_expose_revoked_professional_role(self):
        user = self.make_user()
        SalonManager.objects.create(user=user, is_active=True)
        Stylist.objects.create(user=user, is_active=True)
        self.assertIsNotNone(user.salon_manager_profile)
        self.assertIsNotNone(user.stylist)
        SalonManager.objects.filter(user=user).delete()
        Stylist.objects.filter(user=user).delete()
        flags = user_role_flags(user)
        self.assertTrue(flags["is_customer"])
        self.assertFalse(flags["is_salon_manager"])
        self.assertFalse(flags["is_stylist"])

    def test_inactive_identity_has_no_product_roles(self):
        user = self.make_user(is_active=False)
        SalonManager.objects.create(user=user, is_active=True)
        Stylist.objects.create(user=user, is_active=True)
        flags = user_role_flags(user)
        self.assertFalse(flags["is_customer"])
        self.assertFalse(flags["is_stylist"])
        self.assertFalse(flags["is_salon_manager"])
