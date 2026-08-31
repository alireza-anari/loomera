from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.help_center.customer_inquiry import answer_business_customer_inquiry

from .models import (
    InstagramAccountConnection,
    InstagramInboundMessage,
    InstagramInboundMessageStatus,
)


@transaction.atomic
def process_inbound_with_lumi(inbound_message_id):
    # Lock only the inbound row. Joining the nullable stylist relation in the
    # same SELECT ... FOR UPDATE causes PostgreSQL to reject the query because
    # the nullable side is produced by an OUTER JOIN.
    inbound = InstagramInboundMessage.objects.select_for_update().get(
        pk=inbound_message_id
    )

    if inbound.status == InstagramInboundMessageStatus.PROCESSED:
        return inbound

    connection = (
        InstagramAccountConnection.objects.select_related(
            "salon",
            "stylist__user",
        )
        .get(pk=inbound.connection_id)
    )
    if not connection.is_context_active():
        inbound.lumi_disposition = "human_handoff"
        inbound.lumi_reply_text = ""
        inbound.lumi_facts = {"reason": "inactive_connection_context"}
        inbound.requires_human = True
        inbound.status = InstagramInboundMessageStatus.PROCESSED
        inbound.processed_at = timezone.now()
        inbound.save(update_fields=[
            "lumi_disposition", "lumi_reply_text", "lumi_facts",
            "requires_human", "status", "processed_at",
        ])
        return inbound

    inbound.status = InstagramInboundMessageStatus.PROCESSING
    inbound.save(update_fields=["status"])

    try:
        result = answer_business_customer_inquiry(
            salon=connection.salon,
            stylist=connection.stylist,
            message=inbound.message_text,
        )
    except Exception:
        inbound.lumi_disposition = "human_handoff"
        inbound.lumi_reply_text = ""
        inbound.lumi_facts = {"reason": "lumi_processing_error"}
        inbound.requires_human = True
        inbound.status = InstagramInboundMessageStatus.FAILED
        inbound.processed_at = timezone.now()
        inbound.save(update_fields=[
            "lumi_disposition", "lumi_reply_text", "lumi_facts",
            "requires_human", "status", "processed_at",
        ])
        return inbound

    inbound.lumi_disposition = result.disposition
    inbound.lumi_reply_text = result.answer[:4000]
    inbound.lumi_facts = result.facts
    inbound.requires_human = bool(result.requires_human)
    inbound.status = InstagramInboundMessageStatus.PROCESSED
    inbound.processed_at = timezone.now()
    inbound.save(update_fields=[
        "lumi_disposition", "lumi_reply_text", "lumi_facts",
        "requires_human", "status", "processed_at",
    ])
    return inbound
