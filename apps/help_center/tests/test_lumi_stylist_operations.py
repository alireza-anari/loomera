from django.test import SimpleTestCase

from apps.help_center.actions.stylist_operations import _parse_amount_toman, is_stylist_operation_candidate


class LumiStylistParserTests(SimpleTestCase):
    def test_payout_amount_understands_million(self):
        self.assertEqual(_parse_amount_toman("۲ میلیون تومان برداشت میخوام"), 2_000_000)

    def test_full_payable_amount_is_explicit(self):
        self.assertIsNone(_parse_amount_toman("کل مبلغ قابل دریافت رو برداشت کن"))

    def test_how_to_question_still_goes_to_help_rag(self):
        self.assertFalse(
            is_stylist_operation_candidate(
                "چطور درخواست مرخصی ثبت کنم؟",
                None,
                has_stylist_role=True,
            )
        )

    def test_direct_schedule_request_is_action_candidate(self):
        self.assertTrue(
            is_stylist_operation_candidate(
                "شنبه تا چهارشنبه از ۹ تا ۵ برام برنامه کاری ثبت کن",
                None,
                has_stylist_role=True,
            )
        )
