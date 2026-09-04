from django.test import SimpleTestCase

from apps.help_center.services import _retrieval_question_with_history


class LumiConversationContextTests(SimpleTestCase):
    def test_referential_follow_up_uses_previous_user_question_for_retrieval(self):
        query = _retrieval_question_with_history(
            "بعد چطور عوضش کنم؟",
            [
                {
                    "role": "user",
                    "content": "چطور نوبت رزرو کنم؟",
                }
            ],
        )

        self.assertIn("چطور نوبت رزرو کنم؟", query)
        self.assertIn("بعد چطور عوضش کنم؟", query)

    def test_self_contained_question_does_not_inherit_old_topic(self):
        question = "آدرس‌هایم را از کجا مدیریت کنم؟"

        query = _retrieval_question_with_history(
            question,
            [
                {
                    "role": "user",
                    "content": "چطور نوبت رزرو کنم؟",
                }
            ],
        )

        self.assertEqual(query, question)
