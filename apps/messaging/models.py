from __future__ import annotations

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .constants import (
    MessagingActionStatus,
    MessagingConnectionStatus,
    MessagingIdentityStatus,
    MessagingMessageDirection,
    MessagingMessageStatus,
    MessagingProviderKey,
    MessagingTokenPurpose,
    MessagingWebhookEventStatus,
)


class MessagingProvider(models.Model):
    key = models.CharField(
        max_length=32,
        choices=MessagingProviderKey.choices,
        unique=True,
        db_index=True,
        verbose_name="کلید provider",
    )
    title = models.CharField(max_length=80, verbose_name="عنوان")
    is_active = models.BooleanField(default=False, db_index=True, verbose_name="فعال")
    supports_webhook = models.BooleanField(default=True, verbose_name="پشتیبانی webhook")
    supports_callback = models.BooleanField(default=True, verbose_name="پشتیبانی callback")
    supports_outbound = models.BooleanField(default=True, verbose_name="پشتیبانی ارسال پیام")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="متادیتا")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین تغییر")

    class Meta:
        verbose_name = "provider پیام‌رسان"
        verbose_name_plural = "providerهای پیام‌رسان"
        ordering = ["key"]

    def __str__(self):
        return self.title or self.key


class MessagingIdentity(models.Model):
    provider = models.ForeignKey(
        MessagingProvider,
        on_delete=models.PROTECT,
        related_name="identities",
        verbose_name="provider",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="messaging_identities",
        verbose_name="کاربر متصل",
    )
    provider_user_id = models.CharField(max_length=128, db_index=True, verbose_name="شناسه کاربر در provider")
    chat_id = models.CharField(max_length=128, blank=True, default="", db_index=True, verbose_name="chat_id")
    phone_number = models.CharField(max_length=20, blank=True, default="", db_index=True, verbose_name="شماره موبایل")
    username = models.CharField(max_length=120, blank=True, default="", verbose_name="نام کاربری")
    display_name = models.CharField(max_length=160, blank=True, default="", verbose_name="نام نمایشی")
    language_code = models.CharField(max_length=16, blank=True, default="", verbose_name="زبان")
    status = models.CharField(
        max_length=24,
        choices=MessagingIdentityStatus.choices,
        default=MessagingIdentityStatus.GUEST,
        db_index=True,
        verbose_name="وضعیت",
    )
    raw_profile = models.JSONField(default=dict, blank=True, verbose_name="پروفایل خام")
    first_seen_at = models.DateTimeField(auto_now_add=True, verbose_name="اولین مشاهده")
    last_seen_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="آخرین مشاهده")
    connected_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان اتصال")
    disconnected_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان قطع اتصال")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین تغییر")

    class Meta:
        verbose_name = "هویت پیام‌رسان"
        verbose_name_plural = "هویت‌های پیام‌رسان"
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_user_id"],
                name="msg_ident_provider_user_u",
            ),
            models.UniqueConstraint(
                fields=["provider", "chat_id"],
                condition=~Q(chat_id=""),
                name="msg_ident_provider_chat_u",
            ),
        ]
        indexes = [
            models.Index(fields=["provider", "status"], name="msg_ident_prov_status_idx"),
            models.Index(fields=["user", "provider", "status"], name="msg_identity_user_provider_idx"),
        ]

    def mark_seen(self, *, save=True):
        self.last_seen_at = timezone.now()
        if save:
            self.save(update_fields=["last_seen_at", "updated_at"])

    def link_to_user(self, user, *, save=True):
        self.user = user
        self.status = MessagingIdentityStatus.LINKED
        self.connected_at = timezone.now()
        self.disconnected_at = None
        if save:
            self.save(update_fields=["user", "status", "connected_at", "disconnected_at", "updated_at"])

    def disconnect(self, *, save=True):
        self.status = MessagingIdentityStatus.DISCONNECTED
        self.disconnected_at = timezone.now()
        if save:
            self.save(update_fields=["status", "disconnected_at", "updated_at"])

    def __str__(self):
        label = self.display_name or self.username or self.provider_user_id
        return f"{self.provider.key}:{label}"


class MessagingAccountConnection(models.Model):
    provider = models.ForeignKey(
        MessagingProvider,
        on_delete=models.PROTECT,
        related_name="account_connections",
        verbose_name="provider",
    )
    identity = models.ForeignKey(
        MessagingIdentity,
        on_delete=models.CASCADE,
        related_name="account_connections",
        verbose_name="هویت پیام‌رسان",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="messaging_account_connections",
        verbose_name="کاربر",
    )
    status = models.CharField(
        max_length=24,
        choices=MessagingConnectionStatus.choices,
        default=MessagingConnectionStatus.ACTIVE,
        db_index=True,
        verbose_name="وضعیت",
    )
    connected_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="زمان اتصال")
    disconnected_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان قطع اتصال")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="متادیتا")

    class Meta:
        verbose_name = "اتصال حساب پیام‌رسان"
        verbose_name_plural = "اتصال‌های حساب پیام‌رسان"
        ordering = ["-connected_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["identity"],
                condition=Q(status=MessagingConnectionStatus.ACTIVE),
                name="uniq_msg_active_conn_identity",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "provider", "status"], name="msg_conn_user_provider_idx"),
        ]

    def disconnect(self, *, save=True):
        self.status = MessagingConnectionStatus.DISCONNECTED
        self.disconnected_at = timezone.now()
        if save:
            self.save(update_fields=["status", "disconnected_at"])

    def __str__(self):
        return f"{self.user} / {self.provider.key} / {self.status}"


class MessagingToken(models.Model):
    purpose = models.CharField(max_length=32, choices=MessagingTokenPurpose.choices, db_index=True, verbose_name="کاربرد")
    token_hash = models.CharField(max_length=64, unique=True, db_index=True, verbose_name="هش توکن")
    token_prefix = models.CharField(max_length=12, db_index=True, verbose_name="پیشوند توکن")
    provider = models.ForeignKey(
        MessagingProvider,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="tokens",
        verbose_name="provider",
    )
    identity = models.ForeignKey(
        MessagingIdentity,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="tokens",
        verbose_name="هویت پیام‌رسان",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="messaging_tokens",
        verbose_name="کاربر",
    )
    notification_delivery = models.ForeignKey(
        "notifications.NotificationDelivery",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="messaging_tokens",
        verbose_name="ارسال اعلان",
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
    action_key = models.CharField(max_length=120, blank=True, default="", db_index=True, verbose_name="کلید اکشن")
    audience_role = models.CharField(max_length=24, blank=True, default="", db_index=True, verbose_name="نقش مخاطب")
    salon_id = models.PositiveIntegerField(null=True, blank=True, db_index=True, verbose_name="شناسه سالن scope")
    expires_at = models.DateTimeField(db_index=True, verbose_name="زمان انقضا")
    used_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="زمان استفاده")
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="زمان لغو")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="متادیتا")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "توکن پیام‌رسان"
        verbose_name_plural = "توکن‌های پیام‌رسان"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["purpose", "expires_at"], name="msg_token_purpose_exp_idx"),
            models.Index(fields=["user", "purpose", "used_at"], name="msg_token_user_purpose_idx"),
            models.Index(fields=["identity", "purpose", "used_at"], name="msg_token_identity_idx"),
        ]

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_used(self) -> bool:
        return bool(self.used_at)

    @property
    def is_revoked(self) -> bool:
        return bool(self.revoked_at)

    @property
    def is_active(self) -> bool:
        return not self.is_expired and not self.is_used and not self.is_revoked

    def mark_used(self, *, save=True):
        self.used_at = timezone.now()
        if save:
            self.save(update_fields=["used_at"])

    def revoke(self, *, save=True):
        self.revoked_at = timezone.now()
        if save:
            self.save(update_fields=["revoked_at"])

    def __str__(self):
        return f"{self.purpose} / {self.token_prefix}"


class MessagingWebhookEvent(models.Model):
    provider = models.ForeignKey(
        MessagingProvider,
        on_delete=models.PROTECT,
        related_name="webhook_events",
        verbose_name="provider",
    )
    identity = models.ForeignKey(
        MessagingIdentity,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="webhook_events",
        verbose_name="هویت پیام‌رسان",
    )
    event_id = models.CharField(max_length=160, blank=True, default="", db_index=True, verbose_name="event_id")
    update_id = models.CharField(max_length=160, blank=True, default="", db_index=True, verbose_name="update_id")
    event_type = models.CharField(max_length=80, blank=True, default="", db_index=True, verbose_name="نوع event")
    payload = models.JSONField(default=dict, blank=True, verbose_name="payload خام")
    headers = models.JSONField(default=dict, blank=True, verbose_name="headers")
    status = models.CharField(
        max_length=24,
        choices=MessagingWebhookEventStatus.choices,
        default=MessagingWebhookEventStatus.RECEIVED,
        db_index=True,
        verbose_name="وضعیت",
    )
    error_message = models.TextField(blank=True, default="", verbose_name="خطا")
    received_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="زمان دریافت")
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان پردازش")

    class Meta:
        verbose_name = "event وبهوک پیام‌رسان"
        verbose_name_plural = "eventهای وبهوک پیام‌رسان"
        ordering = ["-received_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "event_id"],
                condition=~Q(event_id=""),
                name="msg_hook_provider_event_u",
            ),
            models.UniqueConstraint(
                fields=["provider", "update_id"],
                condition=~Q(update_id=""),
                name="msg_hook_provider_update_u",
            ),
        ]
        indexes = [
            models.Index(fields=["provider", "status", "received_at"], name="msg_hook_prov_status_idx"),
        ]

    def mark_processed(self, *, save=True):
        self.status = MessagingWebhookEventStatus.PROCESSED
        self.processed_at = timezone.now()
        self.error_message = ""
        if save:
            self.save(update_fields=["status", "processed_at", "error_message"])

    def mark_failed(self, error: str, *, save=True):
        self.status = MessagingWebhookEventStatus.FAILED
        self.processed_at = timezone.now()
        self.error_message = str(error or "")
        if save:
            self.save(update_fields=["status", "processed_at", "error_message"])

    def __str__(self):
        return f"{self.provider.key} / {self.event_type or self.event_id or self.update_id or self.pk}"


class MessagingMessageLog(models.Model):
    provider = models.ForeignKey(
        MessagingProvider,
        on_delete=models.PROTECT,
        related_name="message_logs",
        verbose_name="provider",
    )
    identity = models.ForeignKey(
        MessagingIdentity,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="message_logs",
        verbose_name="هویت پیام‌رسان",
    )
    notification_delivery = models.ForeignKey(
        "notifications.NotificationDelivery",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="messaging_message_logs",
        verbose_name="ارسال اعلان",
    )
    direction = models.CharField(max_length=16, choices=MessagingMessageDirection.choices, db_index=True, verbose_name="جهت")
    status = models.CharField(
        max_length=24,
        choices=MessagingMessageStatus.choices,
        default=MessagingMessageStatus.QUEUED,
        db_index=True,
        verbose_name="وضعیت",
    )
    external_message_id = models.CharField(max_length=160, blank=True, default="", db_index=True, verbose_name="شناسه پیام provider")
    text = models.TextField(blank=True, default="", verbose_name="متن")
    payload = models.JSONField(default=dict, blank=True, verbose_name="payload")
    provider_response = models.JSONField(default=dict, blank=True, verbose_name="پاسخ provider")
    error_message = models.TextField(blank=True, default="", verbose_name="خطا")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاریخ ایجاد")
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان ارسال")
    received_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان دریافت")

    class Meta:
        verbose_name = "لاگ پیام پیام‌رسان"
        verbose_name_plural = "لاگ پیام‌های پیام‌رسان"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["provider", "direction", "status", "created_at"], name="msg_log_provider_dir_idx"),
            models.Index(fields=["identity", "created_at"], name="msg_log_identity_idx"),
            models.Index(fields=["notification_delivery", "created_at"], name="msg_log_delivery_idx"),
        ]

    def __str__(self):
        return f"{self.provider.key} / {self.direction} / {self.status}"


class MessagingActionExecution(models.Model):
    provider = models.ForeignKey(
        MessagingProvider,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="action_executions",
        verbose_name="provider",
    )
    identity = models.ForeignKey(
        MessagingIdentity,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="action_executions",
        verbose_name="هویت پیام‌رسان",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="messaging_action_executions",
        verbose_name="کاربر",
    )
    token = models.OneToOneField(
        MessagingToken,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="action_execution",
        verbose_name="توکن",
    )
    action_key = models.CharField(max_length=120, db_index=True, verbose_name="کلید اکشن")
    related_content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name="نوع آبجکت مرتبط",
    )
    related_object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="شناسه آبجکت مرتبط")
    related_object = GenericForeignKey("related_content_type", "related_object_id")
    status = models.CharField(
        max_length=24,
        choices=MessagingActionStatus.choices,
        default=MessagingActionStatus.STARTED,
        db_index=True,
        verbose_name="وضعیت",
    )
    result = models.JSONField(default=dict, blank=True, verbose_name="نتیجه")
    error_message = models.TextField(blank=True, default="", verbose_name="خطا")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاریخ ایجاد")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان پایان")

    class Meta:
        verbose_name = "اجرای اکشن پیام‌رسان"
        verbose_name_plural = "اجرای اکشن‌های پیام‌رسان"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["action_key", "status", "created_at"], name="msg_action_key_status_idx"),
            models.Index(fields=["user", "action_key", "created_at"], name="msg_action_user_idx"),
        ]

    def mark_finished(self, *, status: str, result: dict | None = None, error_message: str = "", save=True):
        self.status = status
        self.result = result or {}
        self.error_message = error_message or ""
        self.finished_at = timezone.now()
        if save:
            self.save(update_fields=["status", "result", "error_message", "finished_at"])

    def __str__(self):
        return f"{self.action_key} / {self.status}"
