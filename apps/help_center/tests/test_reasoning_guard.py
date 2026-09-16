from django.test import SimpleTestCase

from apps.help_center.services import (
    _clean_ai_answer,
    _strip_visible_reasoning,
    _workflow_intro,
)


class HelpReasoningGuardTests(SimpleTestCase):
    def test_removes_think_block_and_keeps_final_text(self):
        answer = "<think>secret scratchpad</think>\nحتماً. این پاسخ نهایی است. [1]"
        self.assertEqual(
            _clean_ai_answer(answer, 1),
            "حتماً. این پاسخ نهایی است. [1]",
        )

    def test_extracts_explicit_final_answer_after_reasoning(self):
        answer = (
            "Here's a thinking process:\n"
            "1. Analyze User Input\n"
            "2. Identify Relevant Sources\n\n"
            "Final Answer:\n"
            "حتماً. از صفحه نوبت‌ها ادامه بده. [1]"
        )
        self.assertEqual(
            _clean_ai_answer(answer, 1),
            "حتماً. از صفحه نوبت‌ها ادامه بده. [1]",
        )

    def test_rejects_reasoning_without_final_boundary(self):
        answer = (
            "Here's a thinking process:\n"
            "Analyze User Input\n"
            "Identify Relevant Sources"
        )
        self.assertEqual(_strip_visible_reasoning(answer), "")

    def test_normal_answer_is_unchanged(self):
        answer = "اول وضعیت نوبت را بررسی کن. [1]"
        self.assertEqual(_clean_ai_answer(answer, 1), answer)

    def test_workflow_intro_is_short_and_context_aware(self):
        guide = {
            "role_matches": True,
            "required_role_label": "مشتری",
            "steps": [
                {
                    "contextual": True,
                    "url": "/orders/reschedule/42/",
                }
            ],
        }
        intro = _workflow_intro(guide)
        self.assertIn("مسیر دقیق", intro)
        self.assertIn("همین مورد", intro)

    def test_cross_role_workflow_intro_names_required_role(self):
        guide = {
            "role_matches": False,
            "required_role_label": "مدیر مجموعه",
            "steps": [],
        }
        intro = _workflow_intro(guide)
        self.assertTrue(intro.startswith("این کار از حساب مدیر مجموعه انجام می‌شود"))
