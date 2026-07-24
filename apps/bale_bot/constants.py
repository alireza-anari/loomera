from __future__ import annotations

from django.db import models


class BaleUpdateType(models.TextChoices):
    MESSAGE = "message", "پیام"
    EDITED_MESSAGE = "edited_message", "پیام ویرایش‌شده"
    CALLBACK_QUERY = "callback_query", "کلیک دکمه"
    PRE_CHECKOUT_QUERY = "pre_checkout_query", "درخواست پرداخت"
    UNKNOWN = "unknown", "نامشخص"


BALE_PROVIDER_KEY = "bale"

# Internal/custom header used by local tests or trusted reverse proxies.
BALE_WEBHOOK_SECRET_HEADER = "HTTP_X_LOOMERA_BALE_SECRET"

# Telegram-compatible provider secret header. Bale Bot API is designed to be
# close to Telegram Bot API, so accepting this header keeps webhook secret
# validation compatible with providers that support setWebhook secret_token.
BALE_WEBHOOK_PROVIDER_SECRET_HEADER = "HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN"
