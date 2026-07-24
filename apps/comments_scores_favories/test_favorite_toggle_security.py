from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from tests_stage1_helpers import Stage1DomainFactoryMixin

from apps.comments_scores_favories.models import Favorits


class FavoriteToggleSecurityTests(Stage1DomainFactoryMixin, TestCase):
    def test_add_favorite_rejects_get_method(self):
        customer = self.make_customer()
        salon = self.make_salon(manager=self.make_salon_manager())

        self.client.force_login(customer.user)
        response = self.client.get(
            reverse("csf:add_favorite"),
            {"salonId": str(salon.pk)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 405)
        self.assertFalse(
            Favorits.objects.filter(favorite_user=customer, salon=salon).exists()
        )

    def test_add_favorite_requires_login_for_ajax_post(self):
        salon = self.make_salon(manager=self.make_salon_manager())

        response = self.client.post(
            reverse("csf:add_favorite"),
            {"salonId": str(salon.pk)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(Favorits.objects.filter(salon=salon).exists())

    def test_add_favorite_forbids_non_customer_user(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)

        self.client.force_login(manager.user)
        response = self.client.post(
            reverse("csf:add_favorite"),
            {"salonId": str(salon.pk)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Favorits.objects.filter(salon=salon).exists())

    def test_add_favorite_rejects_invalid_salon_id(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.post(
            reverse("csf:add_favorite"),
            {"salonId": "abc"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Favorits.objects.filter(favorite_user=customer).exists())

    def test_add_favorite_adds_salon_for_customer(self):
        customer = self.make_customer()
        salon = self.make_salon(manager=self.make_salon_manager())

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("csf:add_favorite"),
            {"salonId": str(salon.pk)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "added")
        self.assertTrue(payload["is_favorite"])
        self.assertTrue(
            Favorits.objects.filter(favorite_user=customer, salon=salon).exists()
        )

    def test_add_favorite_second_post_removes_salon_for_customer(self):
        customer = self.make_customer()
        salon = self.make_salon(manager=self.make_salon_manager())
        Favorits.objects.create(favorite_user=customer, salon=salon)

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("csf:add_favorite"),
            {"salonId": str(salon.pk)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "removed")
        self.assertFalse(payload["is_favorite"])
        self.assertFalse(
            Favorits.objects.filter(favorite_user=customer, salon=salon).exists()
        )