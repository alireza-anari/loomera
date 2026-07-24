from django.db import models


class MessagingProviderKey(models.TextChoices):
    BALE = "bale", "بله"
    TELEGRAM = "telegram", "تلگرام"
    WHATSAPP = "whatsapp", "واتس‌اپ"
    RUBIKA = "rubika", "روبیکا"


class MessagingIdentityStatus(models.TextChoices):
    GUEST = "guest", "مهمان"
    LINKED = "linked", "متصل به حساب"
    DISCONNECTED = "disconnected", "قطع اتصال"
    BLOCKED = "blocked", "مسدود"


class MessagingConnectionStatus(models.TextChoices):
    ACTIVE = "active", "فعال"
    DISCONNECTED = "disconnected", "قطع‌شده"
    REVOKED = "revoked", "لغوشده"


class MessagingTokenPurpose(models.TextChoices):
    CONNECT_ACCOUNT = "connect_account", "اتصال حساب"
    DISCONNECT_ACCOUNT = "disconnect_account", "قطع اتصال حساب"
    ACTION = "action", "اکشن عملیاتی"


class MessagingWebhookEventStatus(models.TextChoices):
    RECEIVED = "received", "دریافت‌شده"
    DUPLICATE = "duplicate", "تکراری"
    IGNORED = "ignored", "نادیده‌گرفته‌شده"
    PROCESSED = "processed", "پردازش‌شده"
    FAILED = "failed", "ناموفق"


class MessagingMessageDirection(models.TextChoices):
    INBOUND = "inbound", "ورودی"
    OUTBOUND = "outbound", "خروجی"


class MessagingMessageStatus(models.TextChoices):
    RECEIVED = "received", "دریافت‌شده"
    QUEUED = "queued", "در صف"
    SENT = "sent", "ارسال‌شده"
    FAILED = "failed", "ناموفق"
    SKIPPED = "skipped", "ارسال‌نشده"


class MessagingActionStatus(models.TextChoices):
    STARTED = "started", "شروع‌شده"
    SUCCEEDED = "succeeded", "موفق"
    FAILED = "failed", "ناموفق"
    DENIED = "denied", "غیرمجاز"
    EXPIRED = "expired", "منقضی"
    ALREADY_USED = "already_used", "قبلاً استفاده‌شده"
