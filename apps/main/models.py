from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class PlatformSetting(models.Model):
    VALUE_TYPE_BOOL = "bool"
    VALUE_TYPE_INT = "int"
    VALUE_TYPE_STRING = "string"
    VALUE_TYPE_JSON = "json"

    VALUE_TYPE_CHOICES = [
        (VALUE_TYPE_BOOL, "Boolean"),
        (VALUE_TYPE_INT, "Integer"),
        (VALUE_TYPE_STRING, "String"),
        (VALUE_TYPE_JSON, "JSON"),
    ]

    key = models.SlugField(max_length=120, unique=True, verbose_name="کلید")
    value = models.JSONField(default=dict, blank=True, verbose_name="مقدار")
    value_type = models.CharField(
        max_length=16,
        choices=VALUE_TYPE_CHOICES,
        default=VALUE_TYPE_STRING,
        verbose_name="نوع مقدار",
    )
    description = models.TextField(blank=True, verbose_name="توضیح")
    is_sensitive = models.BooleanField(default=False, verbose_name="حساس است")
    is_runtime_editable = models.BooleanField(
        default=False,
        verbose_name="قابل تغییر از پنل عملیاتی",
        help_text="تنظیمات پرریسک باید از env/config کنترل شوند، نه صرفاً دیتابیس.",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_platform_settings",
        verbose_name="آخرین ویرایشگر",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        ordering = ["key"]
        verbose_name = "تنظیم پلتفرم"
        verbose_name_plural = "تنظیمات پلتفرم"
        db_table = "M_PlatformSettings"

    def __str__(self):
        return self.key

    @classmethod
    def get_value(cls, key, default=None):
        setting = cls.objects.filter(key=key).first()
        if setting is None:
            return default
        value = setting.value
        if setting.value_type == cls.VALUE_TYPE_BOOL:
            return bool(value.get("value", default)) if isinstance(value, dict) else bool(value)
        if setting.value_type == cls.VALUE_TYPE_INT:
            try:
                return int(value.get("value", default)) if isinstance(value, dict) else int(value)
            except (TypeError, ValueError):
                return default
        if setting.value_type == cls.VALUE_TYPE_STRING:
            return str(value.get("value", default)) if isinstance(value, dict) else str(value)
        return value if value not in (None, {}) else default


class AdminAuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="admin_audit_logs",
        verbose_name="اقدام‌کننده",
    )
    action = models.CharField(max_length=128, db_index=True, verbose_name="عملیات")
    target_content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name="نوع هدف",
    )
    target_object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="شناسه هدف")
    target_object = GenericForeignKey("target_content_type", "target_object_id")
    old_value = models.JSONField(default=dict, blank=True, verbose_name="مقدار قبلی")
    new_value = models.JSONField(default=dict, blank=True, verbose_name="مقدار جدید")
    reason = models.TextField(blank=True, verbose_name="دلیل")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="داده تکمیلی")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP")
    user_agent = models.TextField(blank=True, verbose_name="User Agent")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاریخ ایجاد")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["target_content_type", "target_object_id"]),
        ]
        verbose_name = "لاگ ادمین"
        verbose_name_plural = "لاگ‌های ادمین"
        db_table = "M_AdminAuditLogs"

    def __str__(self):
        return f"{self.action} - {self.created_at:%Y-%m-%d %H:%M}"


class SecurityAuditLog(models.Model):
    SEVERITY_INFO = "info"
    SEVERITY_WARNING = "warning"
    SEVERITY_CRITICAL = "critical"

    SEVERITY_CHOICES = [
        (SEVERITY_INFO, "اطلاع‌رسانی"),
        (SEVERITY_WARNING, "هشدار"),
        (SEVERITY_CRITICAL, "بحرانی"),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="security_audit_logs",
        verbose_name="کاربر",
    )
    event_type = models.CharField(max_length=128, db_index=True, verbose_name="نوع رویداد")
    severity = models.CharField(
        max_length=16,
        choices=SEVERITY_CHOICES,
        default=SEVERITY_INFO,
        verbose_name="شدت",
    )
    target_content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name="نوع هدف",
    )
    target_object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="شناسه هدف")
    target_object = GenericForeignKey("target_content_type", "target_object_id")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="داده تکمیلی")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP")
    user_agent = models.TextField(blank=True, verbose_name="User Agent")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاریخ ایجاد")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["event_type", "-created_at"]),
            models.Index(fields=["severity", "-created_at"]),
        ]
        verbose_name = "لاگ امنیتی"
        verbose_name_plural = "لاگ‌های امنیتی"
        db_table = "M_SecurityAuditLogs"

    def __str__(self):
        return f"{self.event_type} - {self.get_severity_display()}"


class AdminRoleAssignment(models.Model):
    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super Admin"
        SUPPORT_ADMIN = "support_admin", "Support Admin"
        FINANCE_ADMIN = "finance_admin", "Finance Admin"
        CONTENT_MODERATOR = "content_moderator", "Content Moderator"
        VERIFICATION_ADMIN = "verification_admin", "Verification Admin"
        READ_ONLY_ADMIN = "read_only_admin", "Read-only Admin"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="platform_admin_roles",
        verbose_name="کاربر ادمین",
    )
    role = models.CharField(max_length=48, choices=Role.choices, db_index=True, verbose_name="نقش داخلی")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="فعال")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_platform_admin_roles",
        verbose_name="اعطاکننده نقش",
    )
    note = models.TextField(blank=True, default="", verbose_name="یادداشت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        verbose_name = "نقش داخلی ادمین"
        verbose_name_plural = "نقش‌های داخلی ادمین"
        ordering = ["user_id", "role"]
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="uniq_admin_role_user"),
        ]
        indexes = [models.Index(fields=["role", "is_active"], name="admrole_role_active_idx")]
        db_table = "M_AdminRoleAssignments"

    def __str__(self):
        return f"{self.user} - {self.get_role_display()}"


class SuspensionRecord(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "فعال"
        EXPIRED = "expired", "منقضی"
        REVOKED = "revoked", "لغوشده"

    target_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="suspension_records",
        verbose_name="نوع هدف",
    )
    target_object_id = models.PositiveIntegerField(verbose_name="شناسه هدف")
    target_object = GenericForeignKey("target_content_type", "target_object_id")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.ACTIVE, db_index=True, verbose_name="وضعیت")
    reason = models.CharField(max_length=255, verbose_name="دلیل")
    internal_note = models.TextField(blank=True, default="", verbose_name="یادداشت داخلی")
    user_facing_reason = models.TextField(blank=True, default="", verbose_name="دلیل قابل نمایش به کاربر")
    starts_at = models.DateTimeField(default=timezone.now, verbose_name="شروع")
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="پایان/انقضا")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_suspensions",
        verbose_name="ثبت‌کننده",
    )
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revoked_suspensions",
        verbose_name="لغوکننده",
    )
    revoked_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان لغو")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="متادیتا")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        verbose_name = "رکورد تعلیق"
        verbose_name_plural = "رکوردهای تعلیق"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["target_content_type", "target_object_id"], name="susp_target_idx"),
            models.Index(fields=["status", "created_at"], name="susp_status_time_idx"),
        ]
        db_table = "M_SuspensionRecords"

    @property
    def is_effective(self):
        if self.status != self.Status.ACTIVE:
            return False
        if self.expires_at and self.expires_at <= timezone.now():
            return False
        return True

    def __str__(self):
        return f"{self.target_object} - {self.get_status_display()}"



class SupportTicket(models.Model):
    ISSUE_TYPE_CHOICES = [
        ("account_existing", "پشتیبانی حساب موجود"),
        ("account_join", "درخواست پیوستن کسب‌وکار"),
        ("appointment", "پشتیبانی نوبت"),
        ("other", "سایر موارد"),
    ]

    CATEGORY_CHOICES = [
        ("account", "حساب کاربری"),
        ("booking", "رزرو و نوبت"),
        ("cancellation", "لغو نوبت"),
        ("no_show", "عدم حضور"),
        ("payment", "پرداخت"),
        ("finance", "مالی"),
        ("staff_payout", "پرداخت سهم آرایشگر"),
        ("salon_verification", "احراز سالن"),
        ("content_report", "گزارش محتوا"),
        ("review_report", "گزارش نظر"),
        ("technical_bug", "خطای فنی"),
        ("refund", "برگشت وجه"),
        ("compensation", "جبران مشتری"),
        ("membership_access", "عضویت و دسترسی"),
        ("other", "سایر"),
    ]

    STATUS_CHOICES = [
        ("new", "جدید"),
        ("open", "باز"),
        ("in_progress", "در حال بررسی"),
        ("waiting_for_support", "در انتظار پشتیبانی"),
        ("waiting_for_user", "در انتظار کاربر"),
        ("waiting_for_salon", "در انتظار سالن"),
        ("waiting_for_stylist", "در انتظار آرایشگر"),
        ("waiting_for_finance", "در انتظار مالی"),
        ("waiting_for_admin_review", "در انتظار بررسی ادمین"),
        ("resolved", "حل شده"),
        ("closed", "بسته شده"),
        ("cancelled", "لغو شده"),
    ]

    PRIORITY_CHOICES = [
        ("normal", "عادی"),
        ("high", "مهم"),
        ("urgent", "فوری"),
        ("critical", "بحرانی"),
    ]

    TEAM_CHOICES = [
        ("support", "پشتیبانی"),
        ("finance", "مالی"),
        ("content_moderation", "کنترل محتوا"),
        ("verification", "احراز"),
        ("technical", "فنی"),
    ]

    REQUESTER_ROLE_CHOICES = [
        ("customer", "مشتری"),
        ("salon_manager", "مدیر سالن"),
        ("stylist", "آرایشگر"),
        ("guest", "مهمان"),
        ("admin", "ادمین"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets",
        verbose_name="کاربر",
    )
    email = models.EmailField(verbose_name="ایمیل")
    full_name = models.CharField(max_length=150, blank=True, verbose_name="نام کامل")
    city = models.CharField(max_length=120, blank=True, verbose_name="شهر")
    mobile = models.CharField(max_length=20, blank=True, verbose_name="شماره موبایل")
    issue_type = models.CharField(max_length=32, choices=ISSUE_TYPE_CHOICES, verbose_name="نوع درخواست")
    support_reason = models.CharField(max_length=64, blank=True, verbose_name="موضوع")
    subject = models.CharField(max_length=255, blank=True, default="", verbose_name="عنوان")
    description = models.TextField(blank=True, verbose_name="شرح درخواست")
    attachment = models.FileField(upload_to="support_tickets/", null=True, blank=True, verbose_name="پیوست")

    category = models.CharField(max_length=64, choices=CATEGORY_CHOICES, default="other", db_index=True, verbose_name="دسته‌بندی")
    sub_category = models.CharField(max_length=64, blank=True, default="", verbose_name="زیرگروه")
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default="new", db_index=True, verbose_name="وضعیت")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="normal", db_index=True, verbose_name="اولویت")
    requester_role = models.CharField(max_length=32, choices=REQUESTER_ROLE_CHOICES, default="customer", verbose_name="نقش درخواست‌کننده")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_support_tickets",
        verbose_name="مسئول رسیدگی",
    )
    assigned_team = models.CharField(max_length=64, choices=TEAM_CHOICES, default="support", db_index=True, verbose_name="تیم مسئول")

    salon = models.ForeignKey("salons.Salon", on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets", verbose_name="سالن مرتبط")
    stylist = models.ForeignKey("accounts.Stylist", on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets", verbose_name="آرایشگر مرتبط")
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets", verbose_name="سفارش مرتبط")
    order_detail = models.ForeignKey("orders.OrderDetail", on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets", verbose_name="آیتم نوبت مرتبط")
    related_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_related_tickets",
        verbose_name="نوع آبجکت مرتبط",
    )
    related_object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="شناسه آبجکت مرتبط")
    related_object = GenericForeignKey("related_content_type", "related_object_id")

    admin_reply = models.TextField(blank=True, verbose_name="آخرین پاسخ ادمین")
    sla_due_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="مهلت پاسخ/رسیدگی")
    first_response_at = models.DateTimeField(null=True, blank=True, verbose_name="اولین پاسخ")
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان حل")
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان بسته‌شدن")
    last_response_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="last_support_responses",
        verbose_name="آخرین پاسخ‌دهنده",
    )
    last_response_at = models.DateTimeField(null=True, blank=True, verbose_name="آخرین پاسخ")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="داده تکمیلی")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        verbose_name = "تیکت پشتیبانی"
        verbose_name_plural = "تیکت‌های پشتیبانی"
        indexes = [
            models.Index(fields=["status", "priority"], name="supp_status_prio_idx"),
            models.Index(fields=["category", "status"], name="supp_cat_status_idx"),
            models.Index(fields=["assigned_team", "status"], name="supp_team_status_idx"),
            models.Index(fields=["salon", "status"], name="supp_salon_status_idx"),
            models.Index(fields=["order_detail", "status"], name="supp_orddet_status_idx"),
        ]

    def __str__(self):
        label = self.full_name or self.email
        return f"{label} - {self.get_issue_type_display()}"

    @property
    def is_open(self):
        return self.status not in {"resolved", "closed", "cancelled"}


class SupportTicketMessage(models.Model):
    MESSAGE_TYPE_PUBLIC = "public"
    MESSAGE_TYPE_INTERNAL = "internal"
    MESSAGE_TYPE_SYSTEM = "system"
    MESSAGE_TYPE_CHOICES = [
        (MESSAGE_TYPE_PUBLIC, "عمومی"),
        (MESSAGE_TYPE_INTERNAL, "یادداشت داخلی"),
        (MESSAGE_TYPE_SYSTEM, "سیستمی"),
    ]
    SENDER_ROLE_CHOICES = SupportTicket.REQUESTER_ROLE_CHOICES + [
        ("support_admin", "ادمین پشتیبانی"),
        ("finance_admin", "ادمین مالی"),
        ("content_moderator", "ناظر محتوا"),
        ("system", "سیستم"),
    ]

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages", verbose_name="تیکت")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="support_messages", verbose_name="فرستنده")
    sender_role = models.CharField(max_length=40, choices=SENDER_ROLE_CHOICES, default="customer", verbose_name="نقش فرستنده")
    message_type = models.CharField(max_length=16, choices=MESSAGE_TYPE_CHOICES, default=MESSAGE_TYPE_PUBLIC, db_index=True, verbose_name="نوع پیام")
    body = models.TextField(verbose_name="متن پیام")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="زمان ثبت")

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "پیام تیکت"
        verbose_name_plural = "پیام‌های تیکت"
        indexes = [models.Index(fields=["ticket", "created_at"], name="suppmsg_ticket_time_idx")]

    def __str__(self):
        return f"پیام #{self.pk} برای تیکت #{self.ticket_id}"


class SupportAttachment(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="attachments", verbose_name="تیکت")
    message = models.ForeignKey(SupportTicketMessage, null=True, blank=True, on_delete=models.CASCADE, related_name="attachments", verbose_name="پیام")
    file = models.FileField(upload_to="support_attachments/", verbose_name="فایل")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="support_attachments", verbose_name="بارگذاری‌کننده")
    file_type = models.CharField(max_length=64, blank=True, default="", verbose_name="نوع فایل")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "پیوست تیکت"
        verbose_name_plural = "پیوست‌های تیکت"

    def __str__(self):
        return f"پیوست تیکت #{self.ticket_id}"


class SupportEvent(models.Model):
    EVENT_CHOICES = [
        ("created", "ایجاد شد"),
        ("message_added", "پیام ثبت شد"),
        ("status_changed", "وضعیت تغییر کرد"),
        ("assigned", "ارجاع شد"),
        ("priority_changed", "اولویت تغییر کرد"),
        ("closed", "بسته شد"),
        ("reopened", "بازگشایی شد"),
        ("dispute_linked", "پرونده اختلاف متصل شد"),
        ("note", "یادداشت"),
    ]

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="events", verbose_name="تیکت")
    event_type = models.CharField(max_length=64, choices=EVENT_CHOICES, db_index=True, verbose_name="نوع رویداد")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="support_events", verbose_name="انجام‌دهنده")
    old_value = models.JSONField(default=dict, blank=True, verbose_name="مقدار قبلی")
    new_value = models.JSONField(default=dict, blank=True, verbose_name="مقدار جدید")
    note = models.TextField(blank=True, default="", verbose_name="یادداشت")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="داده تکمیلی")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="زمان ثبت")

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "رویداد پشتیبانی"
        verbose_name_plural = "رویدادهای پشتیبانی"
        indexes = [models.Index(fields=["ticket", "created_at"], name="suppevt_ticket_time_idx")]

    def __str__(self):
        return f"{self.get_event_type_display()} - تیکت #{self.ticket_id}"


class DisputeCase(models.Model):
    TYPE_CHOICES = [
        ("no_show", "اعتراض عدم حضور"),
        ("financial", "اختلاف مالی"),
        ("cancellation", "لغو و جبران"),
        ("content_rights", "حقوق محتوا/تصویر"),
        ("review", "اختلاف نظر/امتیاز"),
        ("staff_payout", "اختلاف پرداخت سهم آرایشگر"),
        ("general", "سایر"),
    ]
    STATUS_CHOICES = [
        ("opened", "باز شده"),
        ("under_review", "در حال بررسی"),
        ("waiting_for_evidence", "در انتظار مدرک"),
        ("resolved_for_customer", "حل به نفع مشتری"),
        ("resolved_for_salon", "حل به نفع سالن"),
        ("resolved_partially", "حل جزئی"),
        ("rejected", "رد شده"),
        ("closed", "بسته شده"),
    ]
    PRIORITY_CHOICES = SupportTicket.PRIORITY_CHOICES

    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="opened_disputes", verbose_name="ثبت‌کننده")
    dispute_type = models.CharField(max_length=64, choices=TYPE_CHOICES, db_index=True, verbose_name="نوع اختلاف")
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default="opened", db_index=True, verbose_name="وضعیت")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="normal", db_index=True, verbose_name="اولویت")
    customer = models.ForeignKey("accounts.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="dispute_cases", verbose_name="مشتری")
    salon = models.ForeignKey("salons.Salon", null=True, blank=True, on_delete=models.SET_NULL, related_name="dispute_cases", verbose_name="سالن")
    stylist = models.ForeignKey("accounts.Stylist", null=True, blank=True, on_delete=models.SET_NULL, related_name="dispute_cases", verbose_name="آرایشگر")
    order = models.ForeignKey("orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="dispute_cases", verbose_name="سفارش")
    order_detail = models.ForeignKey("orders.OrderDetail", null=True, blank=True, on_delete=models.SET_NULL, related_name="dispute_cases", verbose_name="آیتم نوبت")
    support_ticket = models.ForeignKey(SupportTicket, null=True, blank=True, on_delete=models.SET_NULL, related_name="dispute_cases", verbose_name="تیکت پشتیبانی")
    financial_snapshot = models.ForeignKey("payments.OrderDetailFinancialSnapshot", null=True, blank=True, on_delete=models.SET_NULL, related_name="dispute_cases", verbose_name="سند مالی")
    financial_adjustment = models.ForeignKey("payments.FinancialAdjustment", null=True, blank=True, on_delete=models.SET_NULL, related_name="dispute_cases", verbose_name="اصلاح مالی")
    related_content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL, related_name="dispute_related_cases", verbose_name="نوع هدف مرتبط")
    related_object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="شناسه هدف مرتبط")
    related_object = GenericForeignKey("related_content_type", "related_object_id")
    subject = models.CharField(max_length=255, blank=True, default="", verbose_name="عنوان")
    description = models.TextField(blank=True, default="", verbose_name="شرح اختلاف")
    resolution = models.CharField(max_length=255, blank=True, default="", verbose_name="نتیجه")
    resolution_note = models.TextField(blank=True, default="", verbose_name="یادداشت نتیجه")
    refund_amount = models.PositiveBigIntegerField(default=0, verbose_name="مبلغ برگشت وجه")
    compensation_amount = models.PositiveBigIntegerField(default=0, verbose_name="مبلغ جبران")
    financial_impact_amount = models.BigIntegerField(default=0, verbose_name="اثر مالی")
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="resolved_disputes", verbose_name="حل‌کننده")
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان حل")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        verbose_name = "پرونده اختلاف"
        verbose_name_plural = "پرونده‌های اختلاف"
        indexes = [
            models.Index(fields=["dispute_type", "status"], name="disp_type_status_idx"),
            models.Index(fields=["salon", "status"], name="disp_salon_status_idx"),
            models.Index(fields=["order_detail", "status"], name="disp_orddet_status_idx"),
        ]

    def __str__(self):
        return f"پرونده #{self.pk} - {self.get_dispute_type_display()}"


class DisputeEvent(models.Model):
    EVENT_CHOICES = [
        ("created", "ایجاد شد"),
        ("status_changed", "تغییر وضعیت"),
        ("evidence_requested", "درخواست مدرک"),
        ("evidence_added", "مدرک ثبت شد"),
        ("resolved", "حل شد"),
        ("financial_adjustment_linked", "اصلاح مالی متصل شد"),
        ("note", "یادداشت"),
    ]

    dispute = models.ForeignKey(DisputeCase, on_delete=models.CASCADE, related_name="events", verbose_name="پرونده اختلاف")
    event_type = models.CharField(max_length=64, choices=EVENT_CHOICES, db_index=True, verbose_name="نوع رویداد")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="dispute_events", verbose_name="انجام‌دهنده")
    old_status = models.CharField(max_length=64, blank=True, default="", verbose_name="وضعیت قبلی")
    new_status = models.CharField(max_length=64, blank=True, default="", verbose_name="وضعیت جدید")
    note = models.TextField(blank=True, default="", verbose_name="یادداشت")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="داده تکمیلی")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="زمان ایجاد")

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "رویداد اختلاف"
        verbose_name_plural = "رویدادهای اختلاف"
        indexes = [models.Index(fields=["dispute", "created_at"], name="dispevt_case_time_idx")]

    def __str__(self):
        return f"{self.get_event_type_display()} - پرونده #{self.dispute_id}"



class OperationalJobRun(models.Model):
    class Status(models.TextChoices):
        STARTED = "started", "شروع شده"
        SUCCESS = "success", "موفق"
        FAILED = "failed", "ناموفق"
        SKIPPED = "skipped", "رد شده"

    job_name = models.CharField(max_length=128, db_index=True, verbose_name="نام job")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.STARTED, db_index=True, verbose_name="وضعیت")
    started_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="شروع")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="پایان")
    duration_ms = models.PositiveIntegerField(default=0, verbose_name="مدت اجرا به میلی‌ثانیه")
    summary = models.CharField(max_length=255, blank=True, default="", verbose_name="خلاصه")
    error_message = models.TextField(blank=True, default="", verbose_name="خطا")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="متادیتا")

    class Meta:
        verbose_name = "اجرای job عملیاتی"
        verbose_name_plural = "اجرای jobهای عملیاتی"
        ordering = ["-started_at", "-id"]
        indexes = [
            models.Index(fields=["job_name", "status"], name="jobrun_name_status_idx"),
            models.Index(fields=["started_at"], name="jobrun_started_idx"),
        ]
        db_table = "M_OperationalJobRuns"

    def mark_finished(self, *, status=None, summary="", error_message="", metadata=None):
        now = timezone.now()
        self.finished_at = now
        self.duration_ms = max(int((now - self.started_at).total_seconds() * 1000), 0)
        if status:
            self.status = status
        if summary:
            self.summary = summary[:255]
        if error_message:
            self.error_message = error_message
        if metadata:
            current = self.metadata or {}
            current.update(metadata)
            self.metadata = current
        self.save(update_fields=["finished_at", "duration_ms", "status", "summary", "error_message", "metadata"])

    def __str__(self):
        return f"{self.job_name} - {self.status}"


class MediaProcessingJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        PROCESSING = "processing", "در حال پردازش"
        COMPLETED = "completed", "کامل شده"
        FAILED = "failed", "ناموفق"
        SKIPPED = "skipped", "رد شده"

    class FileKind(models.TextChoices):
        PUBLIC_IMAGE = "public_image", "تصویر عمومی"
        PRIVATE_DOCUMENT = "private_document", "سند خصوصی"
        SUPPORT_ATTACHMENT = "support_attachment", "پیوست پشتیبانی"
        VERIFICATION_DOCUMENT = "verification_document", "مدرک احراز"
        OTHER = "other", "سایر"

    target_content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL, related_name="media_processing_jobs", verbose_name="نوع هدف")
    target_object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="شناسه هدف")
    target_object = GenericForeignKey("target_content_type", "target_object_id")
    source_file = models.FileField(upload_to="processing/source/%Y/%m/", verbose_name="فایل اصلی")
    processed_file = models.FileField(upload_to="processing/processed/%Y/%m/", blank=True, null=True, verbose_name="فایل پردازش‌شده")
    thumbnail_file = models.FileField(upload_to="processing/thumbs/%Y/%m/", blank=True, null=True, verbose_name="تصویر بندانگشتی")
    file_kind = models.CharField(max_length=48, choices=FileKind.choices, default=FileKind.OTHER, db_index=True, verbose_name="نوع فایل")
    mime_type = models.CharField(max_length=128, blank=True, default="", verbose_name="MIME")
    size_bytes = models.PositiveBigIntegerField(default=0, verbose_name="حجم")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING, db_index=True, verbose_name="وضعیت")
    attempts = models.PositiveIntegerField(default=0, verbose_name="تعداد تلاش")
    error_message = models.TextField(blank=True, default="", verbose_name="خطا")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="متادیتا")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_media_jobs", verbose_name="ثبت‌کننده")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان پردازش")

    class Meta:
        verbose_name = "job پردازش فایل"
        verbose_name_plural = "jobهای پردازش فایل"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="mediajob_status_time_idx"),
            models.Index(fields=["file_kind", "status"], name="mediajob_kind_status_idx"),
        ]
        db_table = "M_MediaProcessingJobs"

    def __str__(self):
        return f"Media job #{self.pk} - {self.status}"
