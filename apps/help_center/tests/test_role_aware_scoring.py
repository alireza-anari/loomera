from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.help_center.retrieval import (
    _alias_phrase_bonus,
    _score_chunk,
    normalize_persian,
    retrieval_audiences,
)
from apps.help_center.models import Audience


class RoleAwareRetrievalRegressionTests(SimpleTestCase):
    def _chunk(self, *, audience, title, aliases="", keywords="", content=""):
        article = SimpleNamespace(
            title=title,
            key="test.key",
            keywords=keywords,
            aliases=aliases,
            article_type="workflow",
            audience=audience,
        )
        return SimpleNamespace(
            article=article,
            heading="خلاصه",
            content=content,
            search_text=" ".join([title, aliases, keywords, content]),
        )

    def test_alias_phrase_bonus_is_preserved(self):
        query = normalize_persian("چطور برای مشتری خودم نوبت ثبت کنم؟")
        self.assertGreaterEqual(
            _alias_phrase_bonus(query, "برای مشتری خودم نوبت ثبت کنم"),
            8,
        )

    def test_connect_bale_beats_disconnect_for_connect_question(self):
        connect = self._chunk(
            audience="all",
            title="اتصال حساب بله به لومرا",
            aliases="وصل کردن بله",
            keywords="اتصال بله ربات",
            content="حساب بله را به لومرا متصل کن.",
        )
        disconnect = self._chunk(
            audience="all",
            title="قطع اتصال بله از حساب لومرا",
            aliases="قطع بله",
            keywords="قطع اتصال بله",
            content="اتصال بله را قطع کن.",
        )
        q = "چطور حساب بله رو به لومرا وصل کنم؟"
        self.assertGreater(
            _score_chunk(connect, q, role="customer"),
            _score_chunk(disconnect, q, role="customer"),
        )

    def test_missing_catalog_service_prefers_request_doc(self):
        request = self._chunk(
            audience="manager",
            title="درخواست افزودن خدمت جدید به کاتالوگ",
            aliases="خدمت در کاتالوگ نیست",
            keywords="درخواست خدمت کاتالوگ",
            content="اگر خدمت وجود ندارد درخواست خدمت جدید ثبت کن.",
        )
        add = self._chunk(
            audience="manager",
            title="افزودن خدمت از کاتالوگ",
            aliases="افزودن خدمت",
            keywords="افزودن خدمت کاتالوگ",
            content="یک خدمت موجود را از کاتالوگ انتخاب کن.",
        )
        q = "خدمتی که می‌خوام تو کاتالوگ نیست چیکار کنم؟"
        self.assertGreater(
            _score_chunk(request, q, role="manager"),
            _score_chunk(add, q, role="manager"),
        )

    def test_cross_role_mode_exposes_all_document_audiences(self):
        audiences = retrieval_audiences("stylist", allow_cross_role=True)
        self.assertEqual(
            set(audiences),
            {Audience.ALL, Audience.CUSTOMER, Audience.STYLIST, Audience.MANAGER},
        )

    def test_cross_role_mode_prefers_same_role_on_equal_evidence(self):
        stylist = self._chunk(
            audience="stylist",
            title="راهنمای برنامه کاری",
            aliases="برنامه کاری",
            keywords="برنامه کاری",
            content="برنامه کاری را مدیریت کن.",
        )
        manager = self._chunk(
            audience="manager",
            title="راهنمای برنامه کاری",
            aliases="برنامه کاری",
            keywords="برنامه کاری",
            content="برنامه کاری را مدیریت کن.",
        )
        q = "برنامه کاری رو چطور مدیریت کنم؟"
        self.assertGreater(
            _score_chunk(stylist, q, role="stylist", allow_cross_role=True),
            _score_chunk(manager, q, role="stylist", allow_cross_role=True),
        )
