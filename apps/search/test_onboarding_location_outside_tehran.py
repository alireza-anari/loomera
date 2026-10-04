from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from apps.salons.forms import SalonProfileStep2Form
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

    def test_numeric_zone_remains_backward_compatible(self):
        zone, zone_label = _extract_reverse_geocode_zone(
            {"address_compound": {"municipal_zone": "منطقه ۵"}}
        )

        self.assertEqual(zone, 5)
        self.assertEqual(zone_label, "منطقه ۵")

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
        self.assertEqual(payload["zone_label"], "ناحیه ۵")
        self.assertEqual(payload["neighborhood"], "جلفا")

    @override_settings(
        MAPIR_API_KEY="test-key",
        MAPIR_SEARCH_BASE_URL="https://map.ir/search/v2",
        MAPIR_ALLOWED_HOSTS={"map.ir"},
        MAPIR_UPSTREAM_RETRY_COUNT=0,
    )
    @patch("apps.search.location_geo._perform_mapir_json_post")
    def test_city_search_returns_coordinates_used_for_map_focus(self, upstream):
        upstream.return_value = (
            """{
                "value": [
                    {
                        "title": "اصفهان",
                        "province": "اصفهان",
                        "geom": {"coordinates": [51.667982, 32.654627]}
                    }
                ]
            }""".encode("utf-8"),
            "application/json",
        )

        response = self.client.get(
            reverse("search:city_search_proxy"),
            {"q": "اصفهان"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["results"]), 1)
        result = payload["results"][0]
        self.assertEqual(result["city"], "اصفهان")
        self.assertAlmostEqual(result["lat"], 32.654627)
        self.assertAlmostEqual(result["lon"], 51.667982)

    @override_settings(
        MAPIR_API_KEY="test-key",
        MAPIR_SEARCH_BASE_URL="https://evil.example/search",
        MAPIR_ALLOWED_HOSTS={"map.ir"},
        MAPIR_UPSTREAM_RETRY_COUNT=0,
    )
    def test_city_search_rejects_unallowed_upstream_host(self):
        response = self.client.get(
            reverse("search:city_search_proxy"),
            {"q": "اصفهان"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["ok"])

    def test_salon_persists_city_and_textual_zone(self):
        field_names = {field.name for field in Salon._meta.get_fields()}
        self.assertIn("city", field_names)
        self.assertIn("zone_label", field_names)

        form = SalonProfileStep2Form(
            data={
                "address": "خیابان حکیم نظامی",
                "address_plaque": "۱۲",
                "address_unit": "۳",
                "latitude": "32.6342",
                "longitude": "51.6574",
                "city": "اصفهان",
                "zone_label": "ناحیه ۵",
                "neighborhood_name": "جلفا",
                "zone": "5",
                "neighborhood": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        salon = form.save(commit=False)
        self.assertEqual(salon.city, "اصفهان")
        self.assertEqual(salon.zone_label, "ناحیه ۵")

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
