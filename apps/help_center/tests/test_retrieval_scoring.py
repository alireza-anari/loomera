from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.help_center.retrieval import _alias_phrase_bonus, _score_chunk, normalize_persian


class HelpRetrievalScoringTests(SimpleTestCase):
    def _chunk(self, *, audience, title, aliases="", keywords="", content="", article_type="workflow"):
        article = SimpleNamespace(
            title=title,
            key="test.key",
            keywords=keywords,
            aliases=aliases,
            article_type=article_type,
            audience=audience,
        )
        return SimpleNamespace(
            article=article,
            heading="خلاصه",
            content=content,
            search_text=" ".join([title, aliases, keywords, content]),
        )

    def test_alias_phrase_bonus(self):
        query = normalize_persian("چطور برای مشتری خودم نوبت ثبت کنم؟")
        self.assertGreaterEqual(
            _alias_phrase_bonus(query, "برای مشتری خودم نوبت ثبت کنم"),
            8,
        )

    def test_exact_role_breaks_close_tie(self):
        stylist = self._chunk(
            audience="stylist",
            title="ثبت نوبت توسط متخصص",
            aliases="برای مشتری خودم نوبت ثبت کنم",
            content="متخصص می‌تواند برای مشتری نوبت ثبت کند.",
        )
        customer = self._chunk(
            audience="customer",
            title="مراحل رزرو نوبت برای مشتری",
            aliases="نوبت گرفتن",
            content="مشتری می‌تواند نوبت رزرو کند.",
        )
        question = "چطور برای مشتری خودم نوبت ثبت کنم؟"
        self.assertGreater(
            _score_chunk(stylist, question, role="stylist"),
            _score_chunk(customer, question, role="stylist"),
        )

    def test_salon_hours_beat_stylist_shift_for_salon_hours_question(self):
        salon = self._chunk(
            audience="manager",
            title="ثبت ساعات کاری مجموعه",
            aliases="تنظیم ساعت کاری مجموعه",
            keywords="ساعات کاری مجموعه روز باز",
            content="ساعات کاری مجموعه در پروفایل ثبت می‌شوند.",
        )
        shift = self._chunk(
            audience="manager",
            title="تنظیم شیفت منظم متخصص",
            aliases="شیفت ثابت",
            keywords="شیفت متخصص برنامه کاری",
            content="شیفت متخصص باید داخل ساعت کاری مجموعه باشد.",
        )
        question = "چطور ساعت کاری مجموعه رو تنظیم کنم؟"
        self.assertGreater(
            _score_chunk(salon, question, role="manager"),
            _score_chunk(shift, question, role="manager"),
        )


class HelpRetrievalIntentTests(SimpleTestCase):
    def _chunk(self, title, keywords, aliases, content):
        article = SimpleNamespace(
            title=title,
            key="test.key",
            keywords=keywords,
            aliases=aliases,
            article_type="workflow",
            audience="manager",
        )
        return SimpleNamespace(
            article=article,
            heading="خلاصه",
            content=content,
            search_text=" ".join([title, keywords, aliases, content]),
        )

    def test_cancel_intent_beats_generic_invite(self):
        cancel = self._chunk(
            "لغو دعوت همکاری متخصص",
            "لغو دعوت همکاری متخصص",
            "کنسل دعوت متخصص",
            "دعوت منتظر را لغو کن.",
        )
        invite = self._chunk(
            "دعوت متخصص به همکاری",
            "دعوت متخصص همکاری",
            "دعوت همکار",
            "برای متخصص دعوت همکاری بساز.",
        )
        question = "چطور دعوت همکاری متخصص رو لغو کنم؟"
        self.assertGreater(
            _score_chunk(cancel, question, role="manager"),
            _score_chunk(invite, question, role="manager"),
        )
