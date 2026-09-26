"""Regression tests: all authenticated identities can use personal customer features."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Customer, SalonManager, Stylist
from tests_stage1_helpers import Stage1DomainFactoryMixin


class CustomerCapabilityTests(Stage1DomainFactoryMixin, TestCase):
    def test_manager_and_stylist_can_open_personal_customer_panel(self):
        for role in ("manager", "stylist", "both"):
            with self.subTest(role=role):
                user = self.make_user()
                if role in ("manager", "both"):
                    SalonManager.objects.create(user=user)
                if role in ("stylist", "both"):
                    Stylist.objects.create(user=user)
                self.client.force_login(user)
                response = self.client.get(reverse("accounts:customer_panel"))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(Customer.objects.filter(user=user).count(), 1)
                customer = Customer.objects.get(user=user)
                self.assertFalse(customer.notify_marketing_sms)
                self.assertFalse(customer.notify_marketing_email)
                self.assertFalse(customer.notify_marketing_whatsapp)
                self.client.logout()

    def test_existing_customer_profile_is_preserved_for_professional_user(self):
        user = self.make_user()
        SalonManager.objects.create(user=user)
        customer = Customer.objects.create(
            user=user, address="Existing address", notify_marketing_sms=True,
            notify_marketing_email=False,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:customer_panel"))
        self.assertEqual(response.status_code, 200)
        customer.refresh_from_db()
        self.assertEqual(Customer.objects.filter(user=user).count(), 1)
        self.assertEqual(customer.address, "Existing address")
        self.assertTrue(customer.notify_marketing_sms)
        self.assertFalse(customer.notify_marketing_email)

    def test_anonymous_user_cannot_create_customer_by_visiting_panel(self):
        response = self.client.get(reverse("accounts:customer_panel"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Customer.objects.count(), 0)
