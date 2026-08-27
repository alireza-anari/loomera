from django.test import TestCase

from apps.help_center.models import Audience, ArticleType, HelpArticle, HelpCategory
from apps.help_center.retrieval import normalize_persian, retrieve_help_chunks


class HelpRetrievalTests(TestCase):
    def setUp(self):
        team = HelpCategory.objects.create(
            slug="test-team",
            title="تیم مجموعه",
            audience=Audience.MANAGER,
        )
        discounts = HelpCategory.objects.create(
            slug="test-discounts",
            title="تخفیف‌ها",
            audience=Audience.MANAGER,
        )
        customer = HelpCategory.objects.create(
            slug="test-customer",
            title="رزرو مشتری",
            audience=Audience.CUSTOMER,
        )
        self.team = HelpArticle.objects.create(
            category=team,
            key="manager.test.team",
            slug="manager-test-team",
            title="مدیریت تیم مجموعه",
            audience=Audience.MANAGER,
            article_type=ArticleType.GUIDE,
            summary="اعضای تیم و متخصص‌ها را مدیریت کن.",
            body="## افزودن متخصص\nمتخصص جدید را به تیم مجموعه اضافه کن.",
            keywords="متخصص تیم استایلیست",
        )
        self.coupon = HelpArticle.objects.create(
            category=discounts,
            key="manager.test.coupon",
            slug="manager-test-coupon",
            title="ساخت کد تخفیف",
            audience=Audience.MANAGER,
            article_type=ArticleType.WORKFLOW,
            summary="برای رزرو مشتری یک کد تخفیف بساز.",
            body="## کد تخفیف\nدرصد، سقف مبلغ و بازه اعتبار کد را مشخص کن.",
            keywords="کد تخفیف کوپن درصد اعتبار",
        )
        self.customer_booking = HelpArticle.objects.create(
            category=customer,
            key="customer.test.booking",
            slug="customer-test-booking",
            title="تغییر زمان نوبت",
            audience=Audience.CUSTOMER,
            article_type=ArticleType.WORKFLOW,
            summary="مشتری می‌تواند زمان نوبت خودش را تغییر دهد.",
            body="زمان جدید را از ظرفیت‌های آزاد انتخاب کن.",
            keywords="رزرو نوبت تغییر زمان",
        )

    def test_normalizes_arabic_and_persian_forms(self):
        self.assertEqual(normalize_persian("كیف پول ۱۲۳"), "کیف پول 123")

    def test_current_page_does_not_override_unrelated_question(self):
        hits = retrieve_help_chunks(
            "چطور کد تخفیف بسازم؟",
            role="manager",
            page_key=self.team.key,
            limit=3,
        )
        self.assertTrue(hits)
        self.assertEqual(hits[0].article_key, self.coupon.key)

    def test_explicit_this_page_question_can_use_page_context(self):
        hits = retrieve_help_chunks(
            "این صفحه چیه و اینجا چه کاری انجام میدم؟",
            role="manager",
            page_key=self.team.key,
            limit=3,
        )
        self.assertTrue(hits)
        self.assertEqual(hits[0].article_key, self.team.key)

    def test_customer_cannot_retrieve_manager_internal_docs(self):
        hits = retrieve_help_chunks("چطور کد تخفیف بسازم؟", role="customer", limit=3)
        self.assertFalse(any(hit.article_key == self.coupon.key for hit in hits))

    def test_manager_can_retrieve_customer_journey_docs(self):
        hits = retrieve_help_chunks("مشتری چطور زمان نوبتش را تغییر بدهد؟", role="manager", limit=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0].article_key, self.customer_booking.key)
