from django.test import SimpleTestCase

from apps.help_center.services import _local_answer


class LumiLocalFallbackTests(SimpleTestCase):
    def test_unsupported_capability_does_not_reuse_irrelevant_payment_article(self):
        groups = [
            {
                "title": "پرداخت نامشخص یا در انتظار بررسی",
                "article_key": "customer.payment.pending-review",
                "score": 42.0,
                "chunks": [
                    {
                        "heading": "خلاصه",
                        "content": (
                            "وقتی نتیجه پرداخت قطعی نیست، دوباره پرداخت نکن."
                        ),
                        "score": 42.0,
                    }
                ],
            }
        ]

        answer = _local_answer(
            groups,
            question="آیا پرداخت قسطی دارید؟",
            requester_role="customer",
            provider_unavailable=True,
        )

        self.assertIn(
            "در مستندات فعلی لومرا پاسخ قطعی این مورد را پیدا نکردم",
            answer,
        )
        self.assertNotIn("دوباره پرداخت نکن", answer)

    def test_near_tie_fallback_surfaces_both_verified_sources(self):
        groups = [
            {
                "title": "مراحل رزرو نوبت برای مشتری",
                "article_key": "customer.booking.flow",
                "score": 56.144,
                "chunks": [
                    {
                        "heading": "پیش‌نمایش رزرو",
                        "content": (
                            "در پیش‌نمایش رزرو زمان و مبلغ را بررسی کن."
                        ),
                        "score": 56.144,
                    }
                ],
            },
            {
                "title": "تغییر زمان نوبت مشتری",
                "article_key": "customer.booking.reschedule",
                "score": 55.944,
                "chunks": [
                    {
                        "heading": "تغییر زمان",
                        "content": (
                            "اگر زمان دلخواه نمایش داده نمی‌شود، ظرفیت متخصص "
                            "و برنامه کاری همان روز را در نظر بگیر و زمان دیگری را بررسی کن."
                        ),
                        "score": 55.944,
                    }
                ],
            },
        ]

        answer = _local_answer(
            groups,
            question="اگر زمان مناسبی برای نوبت پیدا نکردم چه کار کنم؟",
            requester_role="customer",
            provider_unavailable=True,
        )

        self.assertIn("دو راهنمای خیلی نزدیک", answer)
        self.assertIn("مراحل رزرو نوبت برای مشتری", answer)
        self.assertIn("تغییر زمان نوبت مشتری", answer)
        self.assertIn("اگر زمان دلخواه نمایش داده نمی‌شود", answer)

    def test_clear_primary_fallback_keeps_single_source_behavior(self):
        groups = [
            {
                "title": "نوبت‌های متخصص",
                "article_key": "stylist.appointments.overview",
                "score": 55.0,
                "chunks": [
                    {
                        "heading": "خلاصه",
                        "content": "متخصص نوبت‌های خودش را می‌بیند.",
                        "score": 55.0,
                    }
                ],
            },
            {
                "title": "نوبت‌های مشتری",
                "article_key": "customer.appointments.overview",
                "score": 40.0,
                "chunks": [
                    {
                        "heading": "خلاصه",
                        "content": "مشتری نوبت‌های خودش را پیگیری می‌کند.",
                        "score": 40.0,
                    }
                ],
            },
        ]

        answer = _local_answer(
            groups,
            question="نوبت‌های من را از کجا ببینم؟",
            requester_role="stylist",
            provider_unavailable=True,
        )

        self.assertIn("متخصص نوبت‌های خودش را می‌بیند", answer)
        self.assertIn("منبع: نوبت‌های متخصص", answer)
        self.assertNotIn("نوبت‌های مشتری:", answer)

    def test_supported_capability_with_inflected_noun_is_not_marked_unsupported(self):
        groups = [
            {
                "title": "لغو نوبت توسط مشتری",
                "article_key": "customer.booking.cancel",
                "audience": "customer",
                "score": 50.0,
                "chunks": [
                    {
                        "heading": "خلاصه",
                        "content": "مشتری می‌تواند نوبت را لغو کند.",
                        "score": 50.0,
                    }
                ],
            }
        ]

        answer = _local_answer(
            groups,
            question="آیا میشه نوبتم رو لغو کنم؟",
            requester_role="customer",
            provider_unavailable=True,
        )

        self.assertIn("مشتری می‌تواند نوبت را لغو کند", answer)
        self.assertNotIn("پاسخ قطعی این مورد را پیدا نکردم", answer)

    def test_near_tie_does_not_surface_other_role_without_explicit_role_question(self):
        groups = [
            {
                "title": "نوبت‌های من",
                "article_key": "customer.appointments.overview",
                "audience": "customer",
                "score": 50.0,
                "chunks": [
                    {
                        "heading": "پیگیری",
                        "content": "از نوبت‌های من وضعیت رزرو را ببین.",
                        "score": 50.0,
                    }
                ],
            },
            {
                "title": "مدیریت نوبت‌های مجموعه",
                "article_key": "manager.appointments.overview",
                "audience": "manager",
                "score": 49.5,
                "chunks": [
                    {
                        "heading": "مدیریت",
                        "content": "مدیر مجموعه کنترل‌های عملیاتی نوبت را می‌بیند.",
                        "score": 49.5,
                    }
                ],
            },
        ]

        answer = _local_answer(
            groups,
            question="وضعیت نوبتم را از کجا ببینم؟",
            requester_role="customer",
            provider_unavailable=True,
        )

        self.assertIn("منبع: نوبت‌های من", answer)
        self.assertNotIn("مدیریت نوبت‌های مجموعه", answer)
        self.assertNotIn("کنترل‌های عملیاتی", answer)

    def test_near_tie_without_query_title_signal_keeps_primary_only(self):
        groups = [
            {
                "title": "نوبت‌های متخصص",
                "article_key": "stylist.appointments.overview",
                "audience": "stylist",
                "score": 42.0,
                "chunks": [
                    {
                        "heading": "جزئیات نوبت",
                        "content": "برای دیدن جزئیات، همان نوبت را باز کن.",
                        "score": 42.0,
                    }
                ],
            },
            {
                "title": "ثبت نوبت توسط متخصص",
                "article_key": "stylist.booking.manual",
                "audience": "stylist",
                "score": 41.5,
                "chunks": [
                    {
                        "heading": "ثبت نوبت",
                        "content": "متخصص می‌تواند برای مشتری نوبت ثبت کند.",
                        "score": 41.5,
                    }
                ],
            },
        ]

        answer = _local_answer(
            groups,
            question="بعد از کجا جزئیاتش رو ببینم؟",
            requester_role="stylist",
            provider_unavailable=True,
        )

        self.assertIn("منبع: نوبت‌های متخصص", answer)
        self.assertNotIn("ثبت نوبت توسط متخصص:", answer)
