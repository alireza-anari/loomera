from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.help_center.models import ArticleType, HelpArticle, HelpCategory
from apps.help_center.retrieval import retrieve_help_chunks


BENCHMARKS = (
    ('manager', 'چطور متخصص جدید اضافه کنم؟', 'manager.team.add-stylist'),
    ('manager', 'چطور برای متخصص دعوت همکاری بفرستم؟', 'manager.team.invite-stylist'),
    ('manager', 'چطور دعوت همکاری متخصص رو لغو کنم؟', 'manager.team.cancel-invite'),
    ('manager', 'متخصص درخواست همکاری داده چطور تاییدش کنم؟', 'manager.team.review-request'),
    ('manager', 'چطور همکاری یک متخصص رو تموم کنم؟', 'manager.team.end-collaboration'),
    ('manager', 'چرا نمی\u200cتونم همکاری متخصص رو پایان بدم و میگه نوبت آینده داره؟', 'manager.team.end-collaboration-blocked'),
    ('manager', 'چرا متخصصی که اضافه کردم برای رزرو نمایش داده نمی\u200cشود؟', 'manager.team.stylist-not-bookable'),
    ('manager', 'چطور شیفت ثابت برای متخصص بگذارم؟', 'manager.schedule.regular'),
    ('manager', 'درخواست برنامه کاری متخصص رو چطور تایید کنم؟', 'manager.schedule.review-request'),
    ('manager', 'درخواست مرخصی متخصص رو چطور بررسی کنم؟', 'manager.schedule.review-leave'),
    ('manager', 'چطور برنامه فقط یک روز متخصص رو عوض کنم؟', 'manager.schedule.edit-day'),
    ('manager', 'چطور برای مشتری نوبت دستی ثبت کنم؟', 'manager.booking.manual'),
    ('manager', 'چطور لینک مستقیم رزرو بسازم؟', 'manager.booking.quick-link-create'),
    ('manager', 'چرا برای لینک رزرو متخصص هیچ ساعت آزادی نمیاد؟', 'manager.booking.quick-link-no-time'),
    ('manager', 'چطور نوبت مشتری رو از سمت مجموعه لغو کنم؟', 'manager.appointments.cancel'),
    ('manager', 'چه زمانی دریافت وجه حضوری رو ثبت کنم؟', 'manager.appointments.mark-paid'),
    ('manager', 'مرکز مالی مجموعه چه چیزهایی نشون میده؟', 'manager.finance.overview'),
    ('manager', 'شماره شبا مقصد برداشت مجموعه رو کجا ثبت کنم؟', 'manager.finance.payout-destination'),
    ('manager', 'چطور از موجودی مجموعه درخواست برداشت بدم؟', 'manager.finance.withdraw'),
    ('manager', 'چطور درخواست برداشت مجموعه رو کنسل کنم؟', 'manager.finance.withdraw-cancel'),
    ('manager', 'چطور گزارش مالی رو بر اساس تاریخ فیلتر کنم؟', 'manager.finance.reports'),
    ('manager', 'قانون سهم متخصص و مواد مصرفی رو کجا تنظیم کنم؟', 'manager.finance.cost-center'),
    ('manager', 'مواد مصرفی یک نوبت رو کجا ثبت کنم؟', 'manager.finance.appointment-materials'),
    ('manager', 'چطور مالی یک نوبت انجام شده رو نهایی کنم؟', 'manager.finance.finalize-appointment'),
    ('manager', 'چرا سود گزارش شده برای یک خدمت عجیب شده؟', 'manager.finance.profit-report'),
    ('manager', 'چرا متخصصی که از تیم رفته هنوز تو گزارش مالی هست؟', 'manager.finance.stylist-wallets'),
    ('manager', 'چطور درخواست برداشت متخصص رو تایید یا رد کنم؟', 'manager.finance.review-stylist-withdrawal'),
    ('manager', 'چطور کد تخفیف بسازم؟', 'manager.discounts.coupons'),
    ('manager', 'چطور اعلان\u200cهای بله مدیر رو تنظیم کنم؟', 'manager.communications.settings'),
    ('stylist', 'چطور برنامه کاری جدید درخواست کنم؟', 'stylist.schedule.request'),
    ('stylist', 'چطور مرخصی ثبت کنم؟', 'stylist.leave.request'),
    ('stylist', 'چطور درخواست دریافت درآمد بدم؟', 'stylist.finance.withdraw'),
    ('stylist', 'چطور لینک رزرو مخصوص خودم بسازم؟', 'stylist.booking.quick-links'),
    ('stylist', 'چطور اعلان\u200cهای بله متخصص رو تنظیم کنم؟', 'stylist.communications.settings'),
    ('customer', 'چطور زمان نوبتم را عوض کنم؟', 'customer.booking.reschedule'),
    ('customer', 'چطور نوبتم رو لغو کنم؟', 'customer.booking.cancel'),
    ('customer', 'بعد از انجام خدمت پرداخت در مجموعه رو آنلاین چطور تسویه کنم؟', 'customer.booking.pay-in-salon'),
    ('customer', 'پول از حسابم کم شده ولی نتیجه پرداخت مشخص نیست چیکار کنم؟', 'customer.payment.pending-review'),
    ('customer', 'مهلت پرداخت تموم شد و وقتم آزاد شد حالا چیکار کنم؟', 'customer.payment.expired'),
    ('customer', 'چرا زمان انتخابی موقع پرداخت دیگر آزاد نیست؟', 'customer.booking.slot-taken'),
    ('customer', 'حداقل مبلغ شارژ کیف پول چقدر است؟', 'customer.wallet.charge'),
    ('customer', 'چطور از کیف پولم برداشت کنم؟', 'customer.wallet.withdraw'),
    ('customer', 'چطور پروفایلم رو ویرایش کنم؟', 'customer.account.profile-edit'),
    ('customer', 'رمزم یادم رفته چطور عوضش کنم؟', 'customer.account.password'),
    ('customer', 'چرا نمی\u200cتونم حسابم رو حذف کنم؟', 'customer.account.delete'),
    ('customer', 'پیام\u200cهای نوبت و تبلیغاتی رو چطور تنظیم کنم؟', 'customer.communications.settings'),
    ('customer', 'اعلان\u200cهای خوانده نشده رو از کجا ببینم؟', 'customer.account.notifications'),
    ('customer', 'چطور حساب بله رو به لومرا وصل کنم؟', 'messaging.bale.connect'),
    ('customer', 'چطور اتصال بله رو قطع کنم؟', 'messaging.bale.disconnect'),
    ('customer', 'چطور تیکت پشتیبانی قبلیم رو پیگیری کنم؟', 'support.tickets.overview'),
    ('customer', 'چطور به تیکت پشتیبانی جواب بدم یا ببندمش؟', 'support.tickets.reply-close'),
)


class Command(BaseCommand):
    help = "Audit docs-first Help Center quality, chunks, source references and retrieval benchmarks."

    def handle(self, *args, **options):
        failures = []
        published = HelpArticle.objects.filter(is_published=True)
        article_count = published.count()
        chunk_count = sum(article.chunks.count() for article in published.iterator())

        self.stdout.write(self.style.MIGRATE_HEADING("Loomera Help docs audit"))
        self.stdout.write(f"Published articles: {article_count}")
        self.stdout.write(f"Searchable chunks: {chunk_count}")

        no_chunks = list(
            published.annotate(chunk_count=Count("chunks"))
            .filter(chunk_count=0)
            .values_list("key", flat=True)
        )
        if no_chunks:
            failures.append("published articles without chunks")
            self.stdout.write(self.style.ERROR("Published articles without chunks:"))
            for key in no_chunks:
                self.stdout.write(f"  - {key}")
        else:
            self.stdout.write(self.style.SUCCESS("All published articles have searchable chunks."))

        no_sources = list(
            published.filter(source_refs=[]).values_list("key", flat=True)
        )
        if no_sources:
            failures.append("published articles without source_refs")
            self.stdout.write(self.style.ERROR("Published articles without internal source_refs:"))
            for key in no_sources:
                self.stdout.write(f"  - {key}")
        else:
            self.stdout.write(self.style.SUCCESS("All published articles have internal source_refs."))

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Article-type coverage"))
        for category in HelpCategory.objects.filter(is_published=True).order_by("sort_order", "title"):
            counts = {
                value: category.articles.filter(is_published=True, article_type=value).count()
                for value in ArticleType.values
            }
            self.stdout.write(
                f"{category.title}: "
                + ", ".join(f"{key}={value}" for key, value in counts.items())
            )

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Retrieval benchmarks"))
        for role, query, expected_key in BENCHMARKS:
            hits = retrieve_help_chunks(query, role=role, limit=3)
            top_key = hits[0].article_key if hits else "<none>"
            ok = top_key == expected_key
            mark = "PASS" if ok else "FAIL"
            renderer = self.style.SUCCESS if ok else self.style.ERROR
            self.stdout.write(renderer(f"{mark} [{role}] {query} -> {top_key} (expected {expected_key})"))
            if not ok:
                failures.append(f"benchmark: {query}")

        if failures:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(f"Audit failed: {len(failures)} issue(s)."))
            raise SystemExit(1)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Help docs audit passed."))
