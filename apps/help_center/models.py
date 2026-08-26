from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class Audience(models.TextChoices):
    ALL = "all", "همه"
    CUSTOMER = "customer", "مشتری"
    MANAGER = "manager", "مدیر مجموعه"
    STYLIST = "stylist", "متخصص"


class HelpCategory(models.Model):
    slug = models.SlugField(max_length=100, unique=True, verbose_name="اسلاگ")
    title = models.CharField(max_length=160, verbose_name="عنوان")
    description = models.TextField(blank=True, default="", verbose_name="توضیح")
    icon = models.CharField(
        max_length=100,
        blank=True,
        default="fa-regular fa-circle-question",
        verbose_name="کلاس آیکون",
    )
    audience = models.CharField(
        max_length=20,
        choices=Audience.choices,
        default=Audience.ALL,
        db_index=True,
        verbose_name="مخاطب",
    )
    sort_order = models.PositiveIntegerField(default=100, db_index=True, verbose_name="ترتیب")
    is_published = models.BooleanField(default=True, db_index=True, verbose_name="منتشر شده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="بروزرسانی")

    class Meta:
        ordering = ["sort_order", "title", "id"]
        db_table = "HC_Categories"
        verbose_name = "دسته راهنما"
        verbose_name_plural = "دسته‌های راهنما"
        indexes = [
            models.Index(fields=["audience", "is_published", "sort_order"], name="hc_cat_aud_pub_sort"),
        ]

    def __str__(self):
        return self.title


class HelpArticle(models.Model):
    category = models.ForeignKey(
        HelpCategory,
        on_delete=models.PROTECT,
        related_name="articles",
        verbose_name="دسته",
    )
    key = models.CharField(
        max_length=140,
        unique=True,
        db_index=True,
        verbose_name="کلید صفحه/مقاله",
        help_text="مثال: manager.team یا customer.addresses",
    )
    slug = models.SlugField(max_length=180, unique=True, verbose_name="اسلاگ")
    title = models.CharField(max_length=220, verbose_name="عنوان")
    audience = models.CharField(
        max_length=20,
        choices=Audience.choices,
        default=Audience.ALL,
        db_index=True,
        verbose_name="مخاطب",
    )
    summary = models.TextField(verbose_name="خلاصه")
    body = models.TextField(
        blank=True,
        default="",
        verbose_name="متن تکمیلی",
    )
    steps = models.JSONField(default=list, blank=True, verbose_name="مراحل")
    tips = models.JSONField(default=list, blank=True, verbose_name="نکته‌ها")
    keywords = models.TextField(blank=True, default="", verbose_name="کلیدواژه‌ها")
    sort_order = models.PositiveIntegerField(default=100, db_index=True, verbose_name="ترتیب")
    is_published = models.BooleanField(default=True, db_index=True, verbose_name="منتشر شده")
    published_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان انتشار")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_help_articles",
        verbose_name="سازنده",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_help_articles",
        verbose_name="آخرین ویرایشگر",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="ایجاد")
    updated_at = models.DateTimeField(auto_now=True, db_index=True, verbose_name="بروزرسانی")

    class Meta:
        ordering = ["category__sort_order", "sort_order", "title", "id"]
        db_table = "HC_Articles"
        verbose_name = "مقاله راهنما"
        verbose_name_plural = "مقالات راهنما"
        indexes = [
            models.Index(fields=["audience", "is_published", "sort_order"], name="hc_art_aud_pub_sort"),
            models.Index(fields=["category", "is_published", "sort_order"], name="hc_art_cat_pub_sort"),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.is_published and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)


class HelpPageContext(models.Model):
    page_key = models.CharField(max_length=140, db_index=True, verbose_name="کلید صفحه")
    role = models.CharField(
        max_length=20,
        choices=Audience.choices,
        default=Audience.ALL,
        db_index=True,
        verbose_name="نقش",
    )
    path_pattern = models.CharField(max_length=500, verbose_name="Regex مسیر")
    article = models.ForeignKey(
        HelpArticle,
        on_delete=models.PROTECT,
        related_name="page_contexts",
        verbose_name="مقاله مرتبط",
    )
    quick_prompts = models.JSONField(default=list, blank=True, verbose_name="سؤال‌های پیشنهادی")
    priority = models.PositiveIntegerField(default=100, db_index=True, verbose_name="اولویت تطبیق")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="بروزرسانی")

    class Meta:
        ordering = ["-priority", "id"]
        db_table = "HC_PageContexts"
        verbose_name = "زمینه صفحه"
        verbose_name_plural = "زمینه‌های صفحات"
        constraints = [
            models.UniqueConstraint(fields=["role", "path_pattern"], name="hc_unique_role_path_pattern"),
        ]
        indexes = [
            models.Index(fields=["role", "is_active", "-priority"], name="hc_ctx_role_active_prio"),
            models.Index(fields=["page_key", "is_active"], name="hc_ctx_key_active"),
        ]

    def __str__(self):
        return f"{self.page_key} · {self.path_pattern}"


class HelpLegalDocument(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PUBLISHED = "published", "منتشر شده"
        ARCHIVED = "archived", "آرشیو"

    slug = models.SlugField(max_length=120, db_index=True, verbose_name="اسلاگ")
    title = models.CharField(max_length=220, verbose_name="عنوان")
    version = models.CharField(max_length=40, verbose_name="نسخه")
    summary = models.TextField(blank=True, default="", verbose_name="خلاصه")
    content = models.TextField(blank=True, default="", verbose_name="متن سند")
    audience = models.CharField(
        max_length=20,
        choices=Audience.choices,
        default=Audience.ALL,
        db_index=True,
        verbose_name="مخاطب",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name="وضعیت",
    )
    is_current = models.BooleanField(default=False, db_index=True, verbose_name="نسخه جاری")
    effective_at = models.DateTimeField(null=True, blank=True, verbose_name="تاریخ اجرا")
    published_at = models.DateTimeField(null=True, blank=True, verbose_name="تاریخ انتشار")
    legacy_url_name = models.CharField(max_length=180, blank=True, default="", verbose_name="نام URL قدیمی")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_help_legal_documents",
        verbose_name="سازنده",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_help_legal_documents",
        verbose_name="آخرین ویرایشگر",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="بروزرسانی")

    class Meta:
        ordering = ["slug", "-is_current", "-published_at", "-id"]
        db_table = "HC_LegalDocuments"
        verbose_name = "سند حقوقی"
        verbose_name_plural = "اسناد حقوقی"
        constraints = [
            models.UniqueConstraint(fields=["slug", "version"], name="hc_unique_legal_slug_version"),
        ]
        indexes = [
            models.Index(fields=["slug", "status", "is_current"], name="hc_legal_slug_status_current"),
        ]

    def __str__(self):
        return f"{self.title} · {self.version}"

    def save(self, *args, **kwargs):
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
        with transaction.atomic():
            if self.is_current:
                qs = type(self).objects.filter(slug=self.slug, is_current=True)
                if self.pk:
                    qs = qs.exclude(pk=self.pk)
                qs.update(is_current=False)
            super().save(*args, **kwargs)


class HelpConversation(models.Model):
    class Role(models.TextChoices):
        GUEST = "guest", "مهمان"
        CUSTOMER = "customer", "مشتری"
        MANAGER = "manager", "مدیر مجموعه"
        STYLIST = "stylist", "متخصص"

    class Status(models.TextChoices):
        ACTIVE = "active", "فعال"
        ESCALATED = "escalated", "ارجاع به پشتیبانی"
        CLOSED = "closed", "بسته"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="help_conversations",
        verbose_name="کاربر",
    )
    session_key_hash = models.CharField(max_length=64, blank=True, default="", db_index=True, verbose_name="هش نشست")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.GUEST, db_index=True, verbose_name="نقش")
    page_key = models.CharField(max_length=140, blank=True, default="", db_index=True, verbose_name="کلید صفحه")
    page_path = models.CharField(max_length=500, blank=True, default="", verbose_name="مسیر صفحه")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True, verbose_name="وضعیت")
    support_ticket = models.ForeignKey(
        "main.SupportTicket",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="help_conversations",
        verbose_name="تیکت پشتیبانی",
    )
    metadata = models.JSONField(default=dict, blank=True, verbose_name="متادیتا")
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="آخرین پیام")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="بروزرسانی")

    class Meta:
        ordering = ["-last_message_at", "-created_at", "-id"]
        db_table = "HC_Conversations"
        verbose_name = "گفتگوی دستیار"
        verbose_name_plural = "گفتگوهای دستیار"
        indexes = [
            models.Index(fields=["user", "status", "-created_at"], name="hc_conv_user_status_time"),
            models.Index(fields=["role", "status", "-created_at"], name="hc_conv_role_status_time"),
            models.Index(fields=["page_key", "-created_at"], name="hc_conv_page_time"),
        ]

    def __str__(self):
        return f"{self.role} · {self.public_id}"


class HelpMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "کاربر"
        ASSISTANT = "assistant", "دستیار"
        SYSTEM = "system", "سیستم"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    conversation = models.ForeignKey(
        HelpConversation,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="گفتگو",
    )
    role = models.CharField(max_length=20, choices=Role.choices, db_index=True, verbose_name="نقش پیام")
    content = models.TextField(verbose_name="متن پاک‌سازی‌شده")
    used_ai = models.BooleanField(default=False, verbose_name="با AI")
    model_name = models.CharField(max_length=120, blank=True, default="", verbose_name="مدل")
    sources = models.JSONField(default=list, blank=True, verbose_name="منابع")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="متادیتا")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="ایجاد")

    class Meta:
        ordering = ["created_at", "id"]
        db_table = "HC_Messages"
        verbose_name = "پیام دستیار"
        verbose_name_plural = "پیام‌های دستیار"
        indexes = [
            models.Index(fields=["conversation", "created_at"], name="hc_msg_conv_time"),
            models.Index(fields=["role", "-created_at"], name="hc_msg_role_time"),
        ]

    def __str__(self):
        return f"{self.role} · {self.public_id}"


class HelpFeedback(models.Model):
    class Rating(models.TextChoices):
        HELPFUL = "helpful", "مفید"
        NOT_HELPFUL = "not_helpful", "مفید نبود"

    message = models.OneToOneField(
        HelpMessage,
        on_delete=models.CASCADE,
        related_name="feedback",
        verbose_name="پاسخ دستیار",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="help_feedback",
        verbose_name="کاربر",
    )
    rating = models.CharField(max_length=20, choices=Rating.choices, db_index=True, verbose_name="امتیاز")
    note = models.CharField(max_length=500, blank=True, default="", verbose_name="توضیح اختیاری")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="بروزرسانی")

    class Meta:
        ordering = ["-updated_at", "-id"]
        db_table = "HC_Feedback"
        verbose_name = "بازخورد دستیار"
        verbose_name_plural = "بازخوردهای دستیار"
        indexes = [
            models.Index(fields=["rating", "-created_at"], name="hc_feedback_rating_time"),
        ]

    def __str__(self):
        return f"{self.get_rating_display()} · {self.message_id}"
