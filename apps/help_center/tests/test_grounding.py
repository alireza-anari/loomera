from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.help_center.services import _clean_ai_answer, _evidence_groups


class HelpGroundingUtilityTests(SimpleTestCase):
    def _hit(self, article_id, key, title, heading, content, score=10):
        return SimpleNamespace(
            article_id=article_id,
            article_key=key,
            slug=key.replace(".", "-"),
            title=title,
            article_type="workflow",
            heading=heading,
            content=content,
            score=score,
        )

    def test_groups_two_chunks_under_one_source(self):
        hits = [
            self._hit(1, "manager.team.add", "افزودن متخصص", "مراحل", "مرحله اول", 20),
            self._hit(1, "manager.team.add", "افزودن متخصص", "بعد از ذخیره", "تضمین رزرو نیست", 18),
            self._hit(2, "manager.schedule", "برنامه کاری", "شیفت", "شیفت را ثبت کن", 15),
        ]
        groups = _evidence_groups(hits)
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(groups[0]["chunks"]), 2)
        self.assertEqual(groups[0]["article_key"], "manager.team.add")

    def test_removes_invalid_citations_and_markdown_bold(self):
        answer = "متن **مهم** [1]\nادعای دیگر [9]"
        cleaned = _clean_ai_answer(answer, 2)
        self.assertEqual(cleaned, "متن مهم [1]\nادعای دیگر")
