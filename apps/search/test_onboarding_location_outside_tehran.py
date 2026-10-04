from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from apps.salons.models import Salon
from apps.search.views import (
    _extract_reverse_geocode_neighborhood,
    _extract_reverse_geocode_zone,
)


class NationwideOnboardingLocationRegressionTests(SimpleTestCase):
    def test_textual_zone_outside_tehran_is_preserved(self):
        zone, zone_label = _extract_reverse_geocode_zone(
            {"address_compound": {"district": "بخش مرکزی"}}
        )

        self.assertEqual(zone, "")
        self.assertEqual(zone_label, "بخش مرکزی")

    def test_specific_neighborhood_wins_over_city_locality(self):
        neighborhood = _extract_reverse_geocode_neighborhood(
            {
                "address_compound": {
                    "locality": "اصفهان",
                    "neighborhood": "جلفا",
                }
            }
        )

        self.assertEqual(neighborhood, "جلفا")

    @override_settings(
        MAPIR_API_KEY="test-key",
        MAPIR_REVERSE_BASE_URL="https://map.ir/reverse/no",
        MAPIR_ALLOWED_HOSTS={"map.ir"},
        MAPIR_UPSTREAM_RETRY_COUNT=0,
    )
    @patch("apps.search.views._perform_upstream_request")
    def test_reverse_geocode_returns_city_for_non_tehran_location(self, upstream):
        upstream.return_value = (
            """{
                "address": "اصفهان، جلفا، خیابان حکیم نظامی",
                "address_compound": {
                    "city": "اصفهان",
                    "district": "ناحیه ۵",
                    "neighborhood": "جلفا"
                }
            }""".encode("utf-8"),
            "application/json",
        )

        response = self.client.get(
            reverse("search:reverse_geocode_proxy"),
            {"lat": "32.6342", "lon": "51.6574"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload.get("city"), "اصفهان")
        self.assertEqual(payload["neighborhood"], "جلفا")

    def test_salon_has_persistent_location_metadata_relation(self):
        self.assertTrue(hasattr(Salon, "location_metadata"))

    def test_onboarding_location_ui_exposes_city_search_and_zoom_wiring(self):
        base_dir = Path(settings.BASE_DIR)
        template = (
            base_dir / "templates/dashboards/salon_profile_creator_step2.html"
        ).read_text(encoding="utf-8")
        script = (base_dir / "static/js/pages/salon_location_step.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="id_city_search"', template)
        self.assertIn("data-city-search-url=", template)
        self.assertIn("citySearchInput", script)
        self.assertIn("focusCityOnMap", script)
