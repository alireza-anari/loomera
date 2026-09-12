from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Customer


class PrivateCacheControlTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            mobile_number="09121112233", password="StrongPass123!"
        )
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        Customer.objects.create(user=self.user)

    def test_authenticated_html_response_is_no_store(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:customer_panel"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.get("Cache-Control", ""))
        self.assertIn("private", response.get("Cache-Control", ""))

    def test_anonymous_public_response_is_not_forced_no_store(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertNotIn("no-store", response.get("Cache-Control", ""))
