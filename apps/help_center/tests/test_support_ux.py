from django.test import SimpleTestCase
from django.urls import reverse

from apps.help_center.services import _clean_ai_answer


class HelpSupportUxTests(SimpleTestCase):
    def test_conversation_api_has_named_route(self):
        self.assertEqual(
            reverse("help_center:conversation_api"),
            "/help/api/conversation/",
        )

    def test_clean_answer_keeps_valid_inline_citations(self):
        value = _clean_ai_answer(
            "اول خدمت رو بررسی کن. [1]\nبعد برنامه کاری رو ببین. [2]",
            2,
        )
        self.assertIn("[1]", value)
        self.assertIn("[2]", value)
