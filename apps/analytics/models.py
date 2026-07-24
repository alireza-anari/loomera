from __future__ import annotations
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class AnalyticsEvent(models.Model):
    CATEGORY_CHOICES = [
        ("appointment", "نوبت"),
        ("finance", "مالی"),
        ("content", "محتوا"),
        ("search", "جستجو"),
        ("notification", "اعلان"),
        ("support", "پشتیبانی"),
        ("security", "امنیت"),
        ("system", "سیستمی"),
    ]
    category = models.CharField(
        max_length=32, choices=CATEGORY_CHOICES, db_index=True, verbose_name="دسته"
    )
    event_type = models.CharField(
        max_length=96, db_index=True, verbose_name="نوع رویداد"
    )
    occurred_at = models.DateTimeField(
        default=timezone.now, db_index=True, verbose_name="زمان وقوع"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="analytics_events",
        verbose_name="کاربر مرتبط",
    )
    salon = models.ForeignKey(
        "salons.Salon",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="analytics_events",
        verbose_name="سالن",
    )
    stylist = models.ForeignKey(
        "accounts.Stylist",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="analytics_events",
        verbose_name="آرایشگر",
    )
    order = models.ForeignKey(
        "orders.Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="analytics_events",
        verbose_name="سفارش",
    )
    order_detail = models.ForeignKey(
        "orders.OrderDetail",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="analytics_events",
        verbose_name="آیتم رزرو",
    )
    target_content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="analytics_events",
        verbose_name="نوع آبجکت هدف",
    )
    target_object_id = models.PositiveBigIntegerField(
        null=True, blank=True, verbose_name="شناسه آبجکت هدف"
    )
    target_object = GenericForeignKey("target_content_type", "target_object_id")
    session_key = models.CharField(
        max_length=64, blank=True, default="", verbose_name="کلید نشست"
    )
    source = models.CharField(
        max_length=64, blank=True, default="", verbose_name="منبع"
    )
    metadata = models.JSONField(default=dict, blank=True, verbose_name="فراداده")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP")
    user_agent = models.TextField(blank=True, default="", verbose_name="User Agent")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")

    class Meta:
        verbose_name = "رویداد Analytics"
        verbose_name_plural = "رویدادهای Analytics"
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=["category", "occurred_at"], name="an_evt_cat_dt"),
            models.Index(fields=["event_type", "occurred_at"], name="an_evt_type_dt"),
            models.Index(fields=["salon", "occurred_at"], name="an_evt_salon_dt"),
            models.Index(fields=["stylist", "occurred_at"], name="an_evt_staff_dt"),
            models.Index(fields=["order_detail"], name="an_evt_od_idx"),
            models.Index(
                fields=["target_content_type", "target_object_id"],
                name="an_evt_target_idx",
            ),
        ]

    def __str__(self):
        return f"{self.category}:{self.event_type}"


class DailyPlatformMetric(models.Model):
    date = models.DateField(unique=True, verbose_name="تاریخ")
    users_total = models.PositiveIntegerField(default=0, verbose_name="کل کاربران")
    customers_total = models.PositiveIntegerField(default=0, verbose_name="کل مشتریان")
    salons_total = models.PositiveIntegerField(default=0, verbose_name="کل سالن‌ها")
    stylists_total = models.PositiveIntegerField(default=0, verbose_name="کل آرایشگران")
    appointments_count = models.PositiveIntegerField(
        default=0, verbose_name="کل نوبت‌ها"
    )
    completed_count = models.PositiveIntegerField(
        default=0, verbose_name="نوبت‌های تکمیل‌شده"
    )
    cancelled_count = models.PositiveIntegerField(
        default=0, verbose_name="نوبت‌های لغوشده"
    )
    no_show_count = models.PositiveIntegerField(default=0, verbose_name="عدم حضور")
    disputed_count = models.PositiveIntegerField(default=0, verbose_name="اختلاف‌ها")
    gross_revenue = models.PositiveBigIntegerField(default=0, verbose_name="فروش خام")
    customer_paid_total = models.PositiveBigIntegerField(
        default=0, verbose_name="مبلغ پرداختی/ثبت‌شده مشتری"
    )
    platform_commission = models.PositiveBigIntegerField(
        default=0, verbose_name="کمیسیون پلتفرم"
    )
    salon_net_profit = models.PositiveBigIntegerField(
        default=0, verbose_name="سود خالص سالن‌ها"
    )
    staff_net_profit = models.PositiveBigIntegerField(
        default=0, verbose_name="سود خالص آرایشگران"
    )
    material_cost_total = models.PositiveBigIntegerField(
        default=0, verbose_name="هزینه مواد"
    )
    content_reports_count = models.PositiveIntegerField(
        default=0, verbose_name="گزارش‌های محتوا"
    )
    support_open_count = models.PositiveIntegerField(
        default=0, verbose_name="تیکت‌های باز"
    )
    disputes_open_count = models.PositiveIntegerField(
        default=0, verbose_name="اختلاف‌های باز"
    )
    notifications_failed_count = models.PositiveIntegerField(
        default=0, verbose_name="اعلان‌های ناموفق"
    )
    searches_count = models.PositiveIntegerField(default=0, verbose_name="جستجوها")
    no_result_searches_count = models.PositiveIntegerField(
        default=0, verbose_name="جستجوهای بدون نتیجه"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "شاخص روزانه پلتفرم"
        verbose_name_plural = "شاخص‌های روزانه پلتفرم"
        ordering = ["-date"]

    def __str__(self):
        return str(self.date)


class DailySalonMetric(models.Model):
    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.CASCADE,
        related_name="daily_metrics",
        verbose_name="سالن",
    )
    date = models.DateField(verbose_name="تاریخ")
    appointments_count = models.PositiveIntegerField(default=0)
    completed_count = models.PositiveIntegerField(default=0)
    cancelled_count = models.PositiveIntegerField(default=0)
    no_show_count = models.PositiveIntegerField(default=0)
    late_count = models.PositiveIntegerField(default=0)
    overrun_count = models.PositiveIntegerField(default=0)
    unique_customers = models.PositiveIntegerField(default=0)
    new_customers = models.PositiveIntegerField(default=0)
    repeat_customers = models.PositiveIntegerField(default=0)
    gross_revenue = models.PositiveBigIntegerField(default=0)
    customer_paid_total = models.PositiveBigIntegerField(default=0)
    platform_commission = models.PositiveBigIntegerField(default=0)
    salon_net_profit = models.PositiveBigIntegerField(default=0)
    staff_payout_total = models.PositiveBigIntegerField(default=0)
    material_cost_total = models.PositiveBigIntegerField(default=0)
    reviews_count = models.PositiveIntegerField(default=0)
    average_rating = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "شاخص روزانه سالن"
        verbose_name_plural = "شاخص‌های روزانه سالن"
        ordering = ["-date", "salon_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["salon", "date"], name="uniq_d_salon_metric"
            )
        ]
        indexes = [
            models.Index(fields=["date"], name="dsalon_date_idx"),
            models.Index(fields=["salon", "date"], name="dsalon_lookup_idx"),
        ]


class DailyStaffMetric(models.Model):
    stylist = models.ForeignKey(
        "accounts.Stylist",
        on_delete=models.CASCADE,
        related_name="daily_metrics",
        verbose_name="آرایشگر",
    )
    salon = models.ForeignKey(
        "salons.Salon",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="staff_daily_metrics",
        verbose_name="سالن",
    )
    date = models.DateField(verbose_name="تاریخ")
    appointments_count = models.PositiveIntegerField(default=0)
    completed_count = models.PositiveIntegerField(default=0)
    late_count = models.PositiveIntegerField(default=0)
    overrun_count = models.PositiveIntegerField(default=0)
    no_show_count = models.PositiveIntegerField(default=0)
    gross_share = models.PositiveBigIntegerField(default=0)
    net_profit = models.BigIntegerField(default=0)
    material_deduction = models.PositiveBigIntegerField(default=0)
    payable_amount = models.BigIntegerField(default=0)
    reviews_count = models.PositiveIntegerField(default=0)
    average_rating = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "شاخص روزانه آرایشگر"
        verbose_name_plural = "شاخص‌های روزانه آرایشگران"
        ordering = ["-date", "stylist_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["stylist", "salon", "date"], name="uniq_d_staff_metric"
            )
        ]
        indexes = [
            models.Index(fields=["date"], name="dstaff_date_idx"),
            models.Index(fields=["stylist", "date"], name="dstaff_lookup_idx"),
        ]


class DailyContentMetric(models.Model):
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, verbose_name="نوع محتوا"
    )
    object_id = models.PositiveBigIntegerField(verbose_name="شناسه محتوا")
    content_object = GenericForeignKey("content_type", "object_id")
    content_kind = models.CharField(
        max_length=32, blank=True, default="", verbose_name="گونه محتوا"
    )
    salon = models.ForeignKey(
        "salons.Salon",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="content_daily_metrics",
        verbose_name="سالن",
    )
    date = models.DateField(verbose_name="تاریخ")
    views = models.PositiveIntegerField(default=0)
    cta_clicks = models.PositiveIntegerField(default=0)
    booking_starts = models.PositiveIntegerField(default=0)
    booking_completed = models.PositiveIntegerField(default=0)
    reports_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "شاخص روزانه محتوا"
        verbose_name_plural = "شاخص‌های روزانه محتوا"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id", "date"],
                name="uniq_d_content_metric",
            )
        ]
        indexes = [
            models.Index(fields=["date"], name="dcontent_date_idx"),
            models.Index(fields=["content_type", "object_id"], name="dcontent_obj_idx"),
        ]


class DailySearchMetric(models.Model):
    date = models.DateField(verbose_name="تاریخ")
    normalized_query = models.CharField(max_length=255, blank=True, default="")
    query = models.CharField(max_length=255, blank=True, default="")
    filters_hash = models.CharField(max_length=64, blank=True, default="")
    searches_count = models.PositiveIntegerField(default=0)
    results_total = models.PositiveIntegerField(default=0)
    no_result_count = models.PositiveIntegerField(default=0)
    clicks_count = models.PositiveIntegerField(default=0)
    booking_starts = models.PositiveIntegerField(default=0)
    booking_completed = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "شاخص روزانه جستجو"
        verbose_name_plural = "شاخص‌های روزانه جستجو"
        ordering = ["-date", "normalized_query"]
        constraints = [
            models.UniqueConstraint(
                fields=["date", "normalized_query", "filters_hash"],
                name="uniq_d_search_metric",
            )
        ]
        indexes = [
            models.Index(fields=["date"], name="dsearch_date_idx"),
            models.Index(fields=["normalized_query"], name="dsearch_q_idx"),
        ]


class ReportExportJob(models.Model):
    class ReportType(models.TextChoices):
        PLATFORM_DAILY = "platform_daily", "شاخص‌های روزانه پلتفرم"
        SALON_DAILY = "salon_daily", "شاخص‌های روزانه سالن"
        STAFF_DAILY = "staff_daily", "شاخص‌های روزانه آرایشگر"
        CONTENT_DAILY = "content_daily", "شاخص‌های روزانه محتوا"
        SEARCH_DAILY = "search_daily", "شاخص‌های روزانه جستجو"

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        PROCESSING = "processing", "در حال پردازش"
        COMPLETED = "completed", "تکمیل شده"
        FAILED = "failed", "ناموفق"
        EXPIRED = "expired", "منقضی شده"

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="report_export_jobs",
    )
    report_type = models.CharField(max_length=64, choices=ReportType.choices)
    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    filters = models.JSONField(default=dict, blank=True)
    file = models.FileField(upload_to="report_exports/", null=True, blank=True)
    rows_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "درخواست خروجی گزارش"
        verbose_name_plural = "درخواست‌های خروجی گزارش"
        ordering = ["-created_at"]

        indexes = [
            # Existing queue-claim and legacy-created-at index.
            models.Index(
                fields=[
                    "status",
                    "created_at",
                ],
                name="rexport_status_dt",
            ),
            # Used when recovering stale processing jobs.
            models.Index(
                fields=[
                    "started_at",
                ],
                name="rexport_proc_start",
                condition=models.Q(
                    status="processing",
                ),
            ),
            # Used by modern completed exports with explicit expires_at.
            models.Index(
                fields=[
                    "expires_at",
                ],
                name="rexport_done_exp",
                condition=models.Q(
                    status="completed",
                ),
            ),
            # Used by completed legacy exports without expires_at.
            models.Index(
                fields=[
                    "completed_at",
                ],
                name="rexport_done_comp",
                condition=models.Q(
                    status="completed",
                ),
            ),
            # Used when cleaning old failed exports.
            models.Index(
                fields=[
                    "completed_at",
                ],
                name="rexport_fail_comp",
                condition=models.Q(
                    status="failed",
                ),
            ),
            # Used when cleaning rows already marked expired.
            models.Index(
                fields=[
                    "updated_at",
                ],
                name="rexport_exp_upd",
                condition=models.Q(
                    status="expired",
                ),
            ),
        ]
