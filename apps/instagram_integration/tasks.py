from __future__ import annotations

from celery import shared_task
from django.conf import settings

from .models import InstagramInboundMessage
from .send_api import process_and_dispatch_lumi_reply


def auto_reply_runtime_enabled():
    return bool(
        getattr(settings, "INSTAGRAM_ENABLED", False)
        and getattr(settings, "INSTAGRAM_MESSAGING_ENABLED", False)
        and getattr(settings, "INSTAGRAM_SEND_ENABLED", False)
        and getattr(settings, "INSTAGRAM_AUTO_REPLY_ENABLED", False)
    )


@shared_task(
    name="instagram.process_inbound_message",
    ignore_result=True,
)
def process_instagram_inbound_message(inbound_message_id):
    # No Celery auto-retry here. An ambiguous provider timeout may mean Meta
    # accepted the reply even if Loomera did not receive the response.
    try:
        InstagramInboundMessage.objects.only("pk").get(pk=inbound_message_id)
    except InstagramInboundMessage.DoesNotExist:
        return "missing"

    result = process_and_dispatch_lumi_reply(inbound_message_id)
    return str(result.status)


def enqueue_instagram_inbound_message(inbound_message_id):
    # Auto Reply OFF still lets the webhook persist and ACK the inbound DM.
    if not auto_reply_runtime_enabled():
        return False

    process_instagram_inbound_message.delay(inbound_message_id)
    return True
