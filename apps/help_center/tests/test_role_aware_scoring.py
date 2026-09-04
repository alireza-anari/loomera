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

    def test_first_person_stylist_question_prefers_stylist_document(self):
        stylist = self._chunk(
            audience="stylist",
            title="نوبت‌های متخصص",
            aliases="قرارهای من\nرزروهای من متخصص",
            keywords="نوبت متخصص مراجعه مشتری",
            content="متخصص نوبت‌های مربوط به خودش را می‌بیند.",
        )
        customer = self._chunk(
            audience="customer",
            title="نوبت‌های من",
            aliases="قرارهای من",
            keywords="نوبت های من رزروها جزئیات پیگیری",
            content="مشتری نوبت‌های خودش را پیگیری می‌کند.",
        )

        question = "نوبت‌های من را از کجا ببینم؟"

        self.assertGreater(
            _score_chunk(
                stylist,
                question,
                role="stylist",
                allow_cross_role=True,
            ),
            _score_chunk(
                customer,
                question,
                role="stylist",
                allow_cross_role=True,
            ),
        )


    def test_customer_selecting_specialist_keeps_customer_booking_document_first(self):
        customer = self._chunk(
            audience="customer",
            title="مراحل رزرو نوبت برای مشتری",
            aliases="انتخاب متخصص برای رزرو",
            keywords="رزرو نوبت انتخاب متخصص زمان",
            content="مشتری هنگام رزرو متخصص مناسب را انتخاب می‌کند.",
        )
        manager = self._chunk(
            audience="manager",
            title="افزودن متخصص به مجموعه",
            aliases="اضافه کردن آرایشگر",
            keywords="متخصص تیم مجموعه",
            content="مدیر متخصص جدید را به مجموعه اضافه می‌کند.",
        )
        q = "متخصص رو چطور انتخاب کنم؟"
        self.assertGreater(
            _score_chunk(customer, q, role="customer", allow_cross_role=True),
            _score_chunk(manager, q, role="customer", allow_cross_role=True),
        )

    def test_stylist_leave_question_prefers_real_stylist_request_metadata(self):
        stylist = self._chunk(
            audience="stylist",
            title="درخواست مرخصی توسط متخصص",
            aliases="درخواست تایم آف\nleave request",
            keywords="مرخصی متخصص درخواست مدیر عدم حضور",
            content=(
                "برای ثبت درخواست مرخصی باید یک مجموعه فعال داشته باشی. "
                "از برنامه و مرخصی من وارد درخواست مرخصی شو."
            ),
        )
        manager = self._chunk(
            audience="manager",
            title="ثبت عدم حضور متخصص توسط مدیر",
            aliases="time off\nمرخصی آرایشگر\nبستن ساعت متخصص",
            keywords="عدم حضور مرخصی متخصص مدیر تایم آف شکستن شیفت",
            content=(
                "از برنامه کاری تیم، متخصص و روز موردنظر را انتخاب کن "
                "و وارد ثبت عدم حضور شو."
            ),
        )
        q = "چطور مرخصی ثبت کنم؟"
        self.assertGreater(
            _score_chunk(stylist, q, role="stylist", allow_cross_role=True),
            _score_chunk(manager, q, role="stylist", allow_cross_role=True),
        )

    def test_explicit_manager_leave_question_can_still_prefer_manager_document(self):
        stylist = self._chunk(
            audience="stylist",
            title="درخواست مرخصی توسط متخصص",
            aliases="درخواست تایم آف",
            keywords="مرخصی متخصص درخواست مدیر عدم حضور",
            content="متخصص درخواست مرخصی را برای بررسی مدیر ثبت می‌کند.",
        )
        manager = self._chunk(
            audience="manager",
            title="ثبت عدم حضور متخصص توسط مدیر",
            aliases="مرخصی آرایشگر",
            keywords="عدم حضور مرخصی متخصص مدیر",
            content="مدیر عدم حضور متخصص را مستقیم ثبت می‌کند.",
        )
        q = "مدیر چطور برای متخصص مرخصی ثبت می‌کند؟"
        self.assertGreater(
            _score_chunk(manager, q, role="stylist", allow_cross_role=True),
            _score_chunk(stylist, q, role="stylist", allow_cross_role=True),
        )

    def test_explicit_manager_actor_still_allows_manager_document_for_customer(self):
        manager = self._chunk(
            audience="manager",
            title="ثبت نوبت دستی توسط مدیر",
            aliases="مدیر برای مشتری نوبت ثبت کند",
            keywords="مدیر مشتری رزرو نوبت",
            content="مدیر برای مشتری نوبت ثبت می‌کند.",
        )
        customer = self._chunk(
            audience="customer",
            title="مراحل رزرو نوبت برای مشتری",
            aliases="نوبت گرفتن",
            keywords="مشتری رزرو نوبت",
            content="مشتری برای خودش نوبت رزرو می‌کند.",
        )
        q = "مدیر چطور برای مشتری نوبت ثبت می‌کند؟"
        self.assertGreater(
            _score_chunk(manager, q, role="customer", allow_cross_role=True),
            _score_chunk(customer, q, role="customer", allow_cross_role=True),
        )
