from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser, SalonManager
from apps.salons.models import Salon
from apps.search.models import SearchResultClick


@override_settings(SEARCH_CLICK_POST_MAX_BYTES=512)
class RecordSearchClickSecurityTests(TestCase):

    def _authenticated_salon(self, *, mobile="09121112233"):
        user = CustomUser.objects.create(
            mobile_number=mobile,
            name="کاربر",
            family="تست کلیک",
            is_active=True,
        )
        manager = SalonManager.objects.create(user=user, is_active=True)
        salon = Salon.objects.create(
            salon_name="سالن تست کلیک",
            salon_manager=manager,
            is_active=True,
            address="تهران",
        )
        self.client.force_login(user)
        return user, salon

    def test_record_search_click_persists_valid_salon_id_and_position(self):
        user, salon = self._authenticated_salon()

        response = self.client.post(
            reverse("search:record_search_click"),
            {
                "salon_id": str(salon.pk),
                "position": "3",
                "q": "رنگ مو",
                "target_url": "/salons/test-click/",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "recorded": True})
        click = SearchResultClick.objects.get()
        self.assertEqual(click.salon_id, salon.pk)
        self.assertEqual(click.user_id, user.pk)
        self.assertEqual(click.rank, 3)

    def test_record_search_click_persists_supported_salon_and_rank_aliases(self):
        _user, salon = self._authenticated_salon(mobile="09121112234")

        response = self.client.post(
            reverse("search:record_search_click"),
            {
                "salon": str(salon.pk),
                "rank": "2",
                "query": "کوتاهی",
                "href": "/salons/test-click-alias/",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["recorded"])
        click = SearchResultClick.objects.get()
        self.assertEqual(click.salon_id, salon.pk)
        self.assertEqual(click.rank, 2)

    def test_record_search_click_rejects_get_method(self):
        response = self.client.get(
            reverse("search:record_search_click"),
            {"salon_id": "1"},
        )

        self.assertEqual(response.status_code, 405)

    @override_settings(SEARCH_CLICK_POST_MAX_BYTES=32)
    def test_record_search_click_rejects_oversized_payload(self):
        response = self.client.post(
            reverse("search:record_search_click"),
            {
                "salon_id": "1",
                "query": "x" * 100,
            },
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"], "payload_too_large")

    @override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1"])
    def test_record_search_click_rejects_external_target_url(self):
        response = self.client.post(
            reverse("search:record_search_click"),
            {
                "salon_id": "1",
                "target_url": "https://evil.example/phish",
            },
            HTTP_HOST="127.0.0.1:8000",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_payload")

    def test_record_search_click_rejects_javascript_target_url(self):
        response = self.client.post(
            reverse("search:record_search_click"),
            {
                "salon_id": "1",
                "target_url": "javascript:alert(1)",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_payload")

    def test_record_search_click_accepts_relative_target_url_when_model_missing(self):
        # This case is specifically about the optional analytics model being
        # unavailable. Mock that condition explicitly so the test does not
        # create a click with a non-existent salon foreign key.
        with patch(
            "django.apps.apps.get_model",
            side_effect=LookupError("SearchResultClick unavailable"),
        ):
            response = self.client.post(
                reverse("search:record_search_click"),
                {
                    "salon_id": "1",
                    "target_url": "/salons/local-seed-salon-5/",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"ok": True, "recorded": False, "reason": "model_not_available"},
        )

    def test_record_search_click_does_not_expose_internal_exception(self):
        with patch(
            "django.apps.apps.get_model",
            side_effect=RuntimeError("sensitive database failure"),
        ):
            response = self.client.post(
                reverse("search:record_search_click"),
                {
                    "salon_id": "1",
                    "target_url": "/salons/local-seed-salon-5/",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["recorded"])
        self.assertEqual(payload["reason"], "recording_failed")
        self.assertNotIn("sensitive", str(payload))
