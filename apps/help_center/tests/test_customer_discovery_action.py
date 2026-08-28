from unittest.mock import patch

from django.contrib.gis.geos import Polygon
from django.test import TestCase

from apps.help_center.actions.customer_discovery import (
    _extract_budget,
    _phrase_match_score,
    run_customer_discovery,
)
from apps.locations.models import Neighborhood
from apps.services.models import Services


class CustomerDiscoveryParserTests(TestCase):
    def test_parses_persian_thousand_budget(self):
        self.assertEqual(_extract_budget("کوتاهی مو تا ۵۰۰ هزار تومان"), (500_000, None))

    def test_does_not_guess_ambiguous_short_budget(self):
        self.assertEqual(_extract_budget("تا ۵۰۰ تومن"), (None, 500))

    def test_haircut_phrase_matches_kootahi(self):
        score = _phrase_match_score("میخوام موهامو کوتاه کنم", "کوتاهی مو")
        self.assertGreaterEqual(score, 0.7)


class CustomerDiscoveryActionTests(TestCase):
    def setUp(self):
        self.service = Services.objects.create(
            service_name="کوتاهی مو",
            is_active=True,
            is_platform_catalog=True,
            base_price=400000,
        )
        Neighborhood.objects.create(
            name="سعادت آباد",
            polygon=Polygon(((0, 0), (0, 1), (1, 1), (1, 0), (0, 0)), srid=4326),
        )

    @patch("apps.help_center.actions.customer_discovery.search_salons")
    def test_builds_real_search_filters_from_natural_message(self, search_salons):
        search_salons.return_value = {
            "salons": [],
            "distance_supported": False,
        }
        result = run_customer_discovery(
            "میخوام موهامو تا ۵۰۰ هزار تومان تو سعادت آباد کوتاه کنم"
        )
        self.assertTrue(result["handled"])
        self.assertEqual(result["action_state"]["service_id"], self.service.pk)
        self.assertEqual(result["action_state"]["max_price"], 500000)
        self.assertEqual(result["action_state"]["location"], "سعادت آباد")
        search_salons.assert_called_once()
        filters = search_salons.call_args.args[0]
        self.assertEqual(filters.q_id, self.service.pk)
        self.assertEqual(filters.max_price, 500000)
        self.assertEqual(filters.location, "سعادت آباد")

    def test_near_me_requires_browser_location_before_search(self):
        result = run_customer_discovery("یه کوتاهی مو نزدیک من پیدا کن")
        self.assertTrue(result["handled"])
        self.assertTrue(result["request_location"])
        self.assertEqual(result["kind"], "discovery_clarification")

    def test_unrelated_help_question_is_not_captured(self):
        result = run_customer_discovery("چطور رمز عبورم رو عوض کنم؟")
        self.assertFalse(result["handled"])

    def test_cancel_clears_discovery_state(self):
        result = run_customer_discovery(
            "بیخیال",
            state={"mode": "customer_discovery", "service_id": self.service.pk, "awaiting": ""},
        )
        self.assertTrue(result["handled"])
        self.assertIsNone(result["action_state"])

    def test_ordinal_result_selection_starts_booking_request(self):
        result = run_customer_discovery(
            "اولی",
            state={
                "mode": "customer_discovery",
                "service_id": self.service.pk,
                "service_name": self.service.service_name,
                "awaiting": "",
                "result_salons": [
                    {"salon_id": 44, "catalog_service_id": self.service.pk},
                    {"salon_id": 55, "catalog_service_id": self.service.pk},
                ],
            },
        )
        self.assertTrue(result["handled"])
        self.assertEqual(result["kind"], "discovery_select_result")
        self.assertEqual(result["booking_request"]["salon_id"], 44)

    def test_short_unrelated_help_topic_escapes_pending_discovery(self):
        result = run_customer_discovery(
            "رمزم یادم رفته",
            state={"mode": "customer_discovery", "awaiting": "service"},
        )
        self.assertFalse(result["handled"])
