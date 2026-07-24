from __future__ import annotations

from django.conf import settings
from django.db import models


class SearchLog(models.Model):
    """ثبت سبک جستجو برای تحلیل رفتار و بهبود ranking.

    این مدل عمداً داده حساس زیادی ذخیره نمی‌کند و برای گزارش‌های محصولی،
    جستجوهای بدون نتیجه و بهبود فیلترها استفاده می‌شود.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="search_logs",
        verbose_name="کاربر",
    )
    session_key = models.CharField(max_length=64, blank=True, default="", verbose_name="کلید نشست")
    query = models.CharField(max_length=255, blank=True, default="", verbose_name="عبارت جستجو")
    normalized_query = models.CharField(max_length=255, blank=True, default="", db_index=True, verbose_name="عبارت نرمال‌شده")
    location = models.CharField(max_length=255, blank=True, default="", verbose_name="موقعیت")
    q_type = models.CharField(max_length=32, blank=True, default="", verbose_name="نوع پیشنهاد انتخاب‌شده")
    q_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="شناسه پیشنهاد انتخاب‌شده")
    filters = models.JSONField(default=dict, blank=True, verbose_name="فیلترها")
    sort = models.CharField(max_length=64, blank=True, default="recommended", verbose_name="مرتب‌سازی")
    results_count = models.PositiveIntegerField(default=0, verbose_name="تعداد نتایج")
    no_result = models.BooleanField(default=False, db_index=True, verbose_name="بدون نتیجه")
    first_result_salon_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="اولین نتیجه")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP")
    user_agent = models.TextField(blank=True, default="", verbose_name="User Agent")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="زمان ثبت")

    def __str__(self):
        return self.normalized_query or self.query or f"Search #{self.pk}"

    class Meta:
        verbose_name = "لاگ جستجو"
        verbose_name_plural = "لاگ‌های جستجو"
        indexes = [
            models.Index(fields=["created_at"], name="srchlog_created_idx"),
            models.Index(fields=["no_result", "created_at"], name="srchlog_nores_dt_idx"),
            models.Index(fields=["normalized_query"], name="srchlog_normq_idx"),
        ]


class SearchResultClick(models.Model):
    search_log = models.ForeignKey(
        SearchLog,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="clicks",
        verbose_name="لاگ جستجو",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="search_result_clicks",
        verbose_name="کاربر",
    )
    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.CASCADE,
        related_name="search_clicks",
        verbose_name="سالن",
    )
    rank = models.PositiveIntegerField(default=0, verbose_name="رتبه در نتایج")
    source = models.CharField(max_length=64, blank=True, default="search", verbose_name="منبع")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="زمان ثبت")

    class Meta:
        verbose_name = "کلیک نتیجه جستجو"
        verbose_name_plural = "کلیک‌های نتیجه جستجو"
        indexes = [
            models.Index(fields=["salon", "created_at"], name="srchclk_salon_dt_idx"),
            models.Index(fields=["search_log", "created_at"], name="srchclk_log_dt_idx"),
        ]


class SearchConversion(models.Model):
    search_log = models.ForeignKey(
        SearchLog,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conversions",
        verbose_name="لاگ جستجو",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="search_conversions",
        verbose_name="کاربر",
    )
    salon = models.ForeignKey(
        "salons.Salon",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="search_conversions",
        verbose_name="سالن",
    )
    order = models.ForeignKey(
        "orders.Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="search_conversions",
        verbose_name="سفارش",
    )
    conversion_type = models.CharField(max_length=64, default="booking_started", verbose_name="نوع تبدیل")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="زمان ثبت")

    class Meta:
        verbose_name = "تبدیل جستجو"
        verbose_name_plural = "تبدیل‌های جستجو"
        indexes = [
            models.Index(fields=["conversion_type", "created_at"], name="srchconv_type_dt_idx"),
            models.Index(fields=["salon", "created_at"], name="srchconv_salon_dt_idx"),
        ]


class SearchAlias(models.Model):
    """واژه‌های معادل فارسی/بازاری برای اتصال جستجوی کاربر به خدمت/دسته.

    مثال: مش، هایلایت، لایت -> خدمت یا دسته رنگ مو.
    """

    TARGET_CHOICES = [
        ("service", "خدمت"),
        ("group", "دسته خدمت"),
        ("salon", "سالن"),
    ]
    keyword = models.CharField(max_length=120, unique=True, verbose_name="کلیدواژه")
    normalized_keyword = models.CharField(max_length=120, db_index=True, verbose_name="کلیدواژه نرمال‌شده")
    target_type = models.CharField(max_length=32, choices=TARGET_CHOICES, verbose_name="نوع مقصد")
    target_id = models.PositiveIntegerField(verbose_name="شناسه مقصد")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین ویرایش")

    def save(self, *args, **kwargs):
        from apps.search.services import normalize_search_text

        self.normalized_keyword = normalize_search_text(self.keyword)
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.keyword

    class Meta:
        verbose_name = "معادل جستجو"
        verbose_name_plural = "معادل‌های جستجو"
        indexes = [
            models.Index(fields=["normalized_keyword", "is_active"], name="srchalias_norm_act_idx"),
        ]
