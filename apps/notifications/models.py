from __future__ import annotations

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.utils import timezone


class NotificationCategory(models.TextChoices):
    BOOKING = "booking", "رزرو"
    PAYMENT = "payment", "پرداخت"
    FINANCE = "finance", "مالی"
    STAFF = "staff", "متخصص و تیم"
    CONTENT = "content", "محتوا"
    SUPPORT = "support", "پشتیبانی"
    VERIFICATION = "verification", "احراز"
    SYSTEM = "system", "سیستمی"
    MARKETING = "marketing", "پیشنهادها"


class NotificationPriority(models.TextChoices):
    LOW = "low", "کم"
    NORMAL = "normal", "معمولی"
    HIGH = "high", "مهم"
    CRITICAL = "critical", "حیاتی"


class NotificationAudienceRole(models.TextChoices):
    CUSTOMER = "customer", "مشتری"
    STYLIST = "stylist", "متخصص"
    MANAGER = "manager", "مدیر سالن"
    ADMIN = "admin", "ادمین Loomera"
    SYSTEM = "system", "سیستم"


class NotificationChannel(models.TextChoices):
    DASHBOARD = "dashboard", "داشبورد"
    EMAIL = "email", "ایمیل"
    SMS = "sms", "پیامک"
    WHATSAPP = "whatsapp", "واتس‌اپ"
    BALE = "bale", "بله"
    TELEGRAM = "telegram", "تلگرام"
    RUBIKA = "rubika", "روبیکا"
    SYSTEM = "system", "سیستم"


class NotificationDeliveryStatus(models.TextChoices):
    PENDING = "pending", "در انتظار"
    QUEUED = "queued", "در صف"
    SENT = "sent", "ارسال شد"
    FAILED = "failed", "ناموفق"
    SKIPPED = "skipped", "ارسال نشد"
    PENDING_SETUP = "pending_setup", "نیازمند تنظیمات"


class NotificationTemplate(models.Model):
    """Optional editable template for one event/channel/audience combination."""

    event_type = models.CharField(max_length=96, db_index=True, verbose_name="نوع رویداد")
    audience_role = models.CharField(
        max_length=24,
        choices=NotificationAudienceRole.choices,
        blank=True,
        default="",
        db_index=True,
        verbose_name="نقش مخاطب",
    )
    channel = models.CharField(
        max_length=24,
        choices=NotificationChannel.choices,
        default=NotificationChannel.DASHBOARD,
        db_index=True,
        verbose_name="کانال",
    )
    category = models.CharField(
        max_length=32,
        choices=NotificationCategory.choices,
        default=NotificationCategory.SYSTEM,
        verbose_name="دسته‌بندی",
    )
    priority = models.CharField(
        max_length=16,
        choices=NotificationPriority.choices,
        default=NotificationPriority.NORMAL,
        verbose_name="اولویت",
    )
    title_template = models.CharField(max_length=180, verbose_name="قالب عنوان")
    body_template = models.TextField(blank=True, default="", verbose_name="قالب متن")
    action_url_template = models.CharField(max_length=500, blank=True, default="", verbose_name="قالب لینک اقدام")
    icon = models.CharField(max_length=80, blank=True, default="fa-regular fa-bell", verbose_name="آیکون")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="فعال")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="متادیتا")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین تغییر")

    class Meta:
        verbose_name = "قالب اعلان"
        verbose_name_plural = "قالب‌های اعلان"
        ordering = ["event_type", "audience_role", "channel"]
        constraints = [
            models.UniqueConstraint(
                fields=["event_type", "audience_role", "channel"],
                name="uniq_notif_template",
            )
        ]
        indexes = [
            models.Index(fields=["event_type", "channel"], name="notif_tmpl_evt_ch_idx"),
            models.Index(fields=["is_active", "event_type"], name="notif_tmpl_active_idx"),
        ]

    def __str__(self):
        return f"{self.event_type} / {self.audience_role or '-'} / {self.channel}"


class Notification(models.Model):
    """Unified event-driven notification record.

    Legacy CustomerNotification and AppointmentNotification are intentionally
    kept for compatibility. This model is the canonical future-facing layer.
    """

    event_type = models.CharField(max_length=96, db_index=True, verbose_name="نوع رویداد")
    category = models.CharField(
        max_length=32,
        choices=NotificationCategory.choices,
        default=NotificationCategory.SYSTEM,
        db_index=True,
        verbose_name="دسته‌بندی",
    )
    priority = models.CharField(
        max_length=16,
        choices=NotificationPriority.choices,
        default=NotificationPriority.NORMAL,
        db_index=True,
        verbose_name="اولویت",
    )
    title = models.CharField(max_length=180, verbose_name="عنوان")
    body = models.TextField(blank=True, default="", verbose_name="متن")
    action_url = models.CharField(max_length=500, blank=True, default="", verbose_name="لینک اقدام")
    icon = models.CharField(max_length=80, blank=True, default="fa-regular fa-bell", verbose_name="آیکون")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_notifications",
        verbose_name="ایجادکننده",
    )
    salon = models.ForeignKey(
        "salons.Salon",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notifications",
        verbose_name="سالن",
    )
    related_content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name="نوع آبجکت مرتبط",
    )
    related_object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="شناسه آبجکت مرتبط")
    related_object = GenericForeignKey("related_content_type", "related_object_id")
    dedupe_key = models.CharField(
        max_length=180,
        blank=True,
        default="",
        db_index=True,
        verbose_name="کلید جلوگیری از تکرار",
    )
    metadata = models.JSONField(default=dict, blank=True, verbose_name="متادیتا")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "اعلان یکپارچه"
        verbose_name_plural = "اعلان‌های یکپارچه"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["dedupe_key"],
                condition=~Q(dedupe_key=""),
                name="uniq_notif_dedupe",
            )
        ]
        indexes = [
            models.Index(fields=["event_type", "-created_at"], name="notif_evt_created_idx"),
            models.Index(fields=["category", "-created_at"], name="notif_cat_created_idx"),
            models.Index(fields=["salon", "-created_at"], name="notif_salon_created_idx"),
        ]

    def __str__(self):
        return self.title


class NotificationRecipient(models.Model):
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="recipients",
        verbose_name="اعلان",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_recipients",
        verbose_name="کاربر",
    )
    audience_role = models.CharField(
        max_length=24,
        choices=NotificationAudienceRole.choices,
        default=NotificationAudienceRole.CUSTOMER,
        db_index=True,
        verbose_name="نقش مخاطب",
    )
    is_read = models.BooleanField(default=False, db_index=True, verbose_name="خوانده شده")
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان خواندن")
    is_archived = models.BooleanField(default=False, db_index=True, verbose_name="آرشیو شده")
    archived_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان آرشیو")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "گیرنده اعلان"
        verbose_name_plural = "گیرندگان اعلان"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["notification", "user", "audience_role"],
                name="uniq_notif_recipient",
            )
        ]
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"], name="notif_rec_read_idx"),
            models.Index(fields=["user", "audience_role", "-created_at"], name="notif_rec_role_idx"),
        ]

    def mark_as_read(self, *, save=True):
        if self.is_read:
            return
        self.is_read = True
        self.read_at = timezone.now()
        if save:
            self.save(update_fields=["is_read", "read_at"])

    def __str__(self):
        return f"{self.notification} -> {self.user}"


class NotificationPreference(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
        verbose_name="کاربر",
    )
    audience_role = models.CharField(
        max_length=24,
        choices=NotificationAudienceRole.choices,
        blank=True,
        default="",
        verbose_name="نقش مخاطب",
    )
    category = models.CharField(
        max_length=32,
        choices=NotificationCategory.choices,
        blank=True,
        default="",
        verbose_name="دسته‌بندی",
    )
    event_type = models.CharField(max_length=96, blank=True, default="", verbose_name="نوع رویداد")
    channel = models.CharField(max_length=24, choices=NotificationChannel.choices, verbose_name="کانال")
    is_enabled = models.BooleanField(default=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین تغییر")

    class Meta:
        verbose_name = "تنظیم اعلان"
        verbose_name_plural = "تنظیمات اعلان"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "audience_role", "category", "event_type", "channel"],
                name="uniq_notif_pref",
            )
        ]
        indexes = [
            models.Index(fields=["user", "channel", "is_enabled"], name="notif_pref_user_ch_idx"),
        ]

    def __str__(self):
        return f"{self.user} / {self.channel} / {self.event_type or self.category or '*'}"


class NotificationDelivery(models.Model):
    recipient = models.ForeignKey(
        NotificationRecipient,
        on_delete=models.CASCADE,
        related_name="deliveries",
        verbose_name="گیرنده",
    )
    channel = models.CharField(max_length=24, choices=NotificationChannel.choices, verbose_name="کانال")
    status = models.CharField(
        max_length=24,
        choices=NotificationDeliveryStatus.choices,
        default=NotificationDeliveryStatus.QUEUED,
        db_index=True,
        verbose_name="وضعیت",
    )
    provider = models.CharField(max_length=64, blank=True, default="", verbose_name="provider")
    attempt_count = models.PositiveIntegerField(default=0, verbose_name="تعداد تلاش")
    scheduled_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان برنامه‌ریزی")
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان ارسال")
    failed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان خطا")
    last_error = models.TextField(blank=True, default="", verbose_name="آخرین خطا")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="متادیتا")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین تغییر")

    class Meta:
        verbose_name = "ارسال اعلان"
        verbose_name_plural = "ارسال‌های اعلان"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "channel"],
                name="uniq_notif_delivery",
            )
        ]
        indexes = [
            models.Index(fields=["channel", "status", "created_at"], name="notif_deliv_queue_idx"),
            models.Index(fields=["status", "created_at"], name="notif_deliv_status_idx"),
        ]

    def __str__(self):
        return f"{self.recipient} / {self.channel} / {self.status}"


class NotificationDeliveryAttempt(models.Model):
    delivery = models.ForeignKey(
        NotificationDelivery,
        on_delete=models.CASCADE,
        related_name="attempts",
        verbose_name="ارسال",
    )
    attempt_number = models.PositiveIntegerField(verbose_name="شماره تلاش")
    status = models.CharField(max_length=24, choices=NotificationDeliveryStatus.choices, verbose_name="وضعیت")
    provider = models.CharField(max_length=64, blank=True, default="", verbose_name="provider")
    provider_response = models.JSONField(default=dict, blank=True, verbose_name="پاسخ provider")
    error_message = models.TextField(blank=True, default="", verbose_name="خطا")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "تلاش ارسال اعلان"
        verbose_name_plural = "تلاش‌های ارسال اعلان"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["delivery", "attempt_number"],
                name="uniq_notif_deliv_att",
            )
        ]
        indexes = [
            models.Index(fields=["delivery", "-created_at"], name="notif_att_deliv_idx"),
        ]

    def __str__(self):
        return f"{self.delivery_id} / {self.attempt_number} / {self.status}"
