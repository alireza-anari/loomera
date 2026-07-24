"""Helpers for creating and reading in-app customer notifications.

This module intentionally avoids hard dependencies on orders/payments models so it
can be imported safely from different apps without circular imports.
"""

from __future__ import annotations

from typing import Any
import hashlib

from django.db import transaction
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from .models import Customer, CustomerNotification, CustomUser


DEFAULT_ICONS = {
    CustomerNotification.CATEGORY_BOOKING: "fa-regular fa-calendar-check",
    CustomerNotification.CATEGORY_PAYMENT: "fa-solid fa-credit-card",
    CustomerNotification.CATEGORY_WALLET: "fa-solid fa-wallet",
    CustomerNotification.CATEGORY_SUPPORT: "fa-regular fa-life-ring",
    CustomerNotification.CATEGORY_SYSTEM: "fa-regular fa-bell",
    CustomerNotification.CATEGORY_MARKETING: "fa-solid fa-gift",
}


def _safe_getattr(obj: Any, attr: str, default: Any = None) -> Any:
    try:
        return getattr(obj, attr, default)
    except Exception:
        return default


def _resolve_user_and_customer(*, user=None, customer=None):
    """Return a valid `(user, customer)` pair for customer notifications."""
    if customer is not None:
        resolved_user = _safe_getattr(customer, "user")
        return resolved_user, customer

    if user is None or not _safe_getattr(user, "is_authenticated", True):
        return None, None

    if not isinstance(user, CustomUser) and not _safe_getattr(user, "pk"):
        return None, None

    try:
        resolved_customer = user.customer_profile
    except Customer.DoesNotExist:
        resolved_customer = None
    except Exception:
        resolved_customer = None

    return user, resolved_customer


def _reverse_or_fallback(viewname: str, *, kwargs: dict[str, Any] | None = None, fallback: str = "") -> str:
    try:
        return reverse(viewname, kwargs=kwargs or {})
    except NoReverseMatch:
        return fallback
    except Exception:
        return fallback


def _first_order_detail_id(order) -> int | None:
    if order is None:
        return None

    try:
        first_item = order.order_details1.order_by("date", "time", "id").first()
        if first_item:
            return first_item.pk
    except Exception:
        pass

    return None


def _order_detail_action_url(order) -> str:
    first_item_id = _first_order_detail_id(order)
    if first_item_id:
        return _reverse_or_fallback(
            "orders:appointment_detail",
            kwargs={"pk": first_item_id},
            fallback=f"/orders/appointment_detail/{first_item_id}/",
        )
    return _reverse_or_fallback("orders:appointments", fallback="/orders/appointments/")


def _payment_result_action_url(payment) -> str:
    payment_id = _safe_getattr(payment, "id")
    token = _safe_getattr(payment, "callback_token")
    if payment_id and token:
        return _reverse_or_fallback(
            "payments:appointment_result",
            kwargs={"payment_id": payment_id, "token": token},
            fallback=f"/payments/appointment/result/{payment_id}/{token}/",
        )
    return ""


def create_customer_notification(
    *,
    user=None,
    customer=None,
    category: str = CustomerNotification.CATEGORY_SYSTEM,
    title: str,
    body: str = "",
    action_url: str = "",
    icon: str = "",
    priority: str = CustomerNotification.PRIORITY_NORMAL,
    metadata: dict[str, Any] | None = None,
    is_read: bool = False,
    respect_marketing_opt_out: bool = True,
    dedupe_key: str = "",
) -> CustomerNotification | None:
    """Create one in-app notification for a customer.

    Returns the created notification, or `None` when the recipient is not a
    customer user or the message should be skipped.

    `dedupe_key` is optional and prevents duplicate notifications on repeated
    gateway callbacks or double-submitted checkout requests.
    """
    resolved_user, resolved_customer = _resolve_user_and_customer(user=user, customer=customer)
    if resolved_user is None or not _safe_getattr(resolved_user, "pk"):
        return None

    if category == CustomerNotification.CATEGORY_MARKETING and respect_marketing_opt_out:
        if resolved_customer and not (
            resolved_customer.notify_marketing_email
            or resolved_customer.notify_marketing_sms
            or resolved_customer.notify_marketing_whatsapp
        ):
            return None

    notification_metadata = dict(metadata or {})
    dedupe_key = str(dedupe_key or notification_metadata.get("dedupe_key") or "").strip()
    if dedupe_key:
        notification_metadata["dedupe_key"] = dedupe_key
        try:
            existing_notification = CustomerNotification.objects.filter(
                user=resolved_user,
                metadata__dedupe_key=dedupe_key,
            ).first()
            if existing_notification:
                return existing_notification
        except Exception:
            # JSON key lookups are supported by Django's JSONField on common
            # backends. If a local DB backend cannot run this lookup, we still
            # create the notification rather than breaking the product flow.
            pass

    notification = CustomerNotification(
        user=resolved_user,
        customer=resolved_customer,
        category=category,
        title=str(title or "").strip()[:160],
        body=str(body or "").strip(),
        action_url=str(action_url or "").strip(),
        icon=icon or DEFAULT_ICONS.get(category, DEFAULT_ICONS[CustomerNotification.CATEGORY_SYSTEM]),
        priority=priority,
        metadata=notification_metadata,
        is_read=is_read,
    )
    if is_read:
        notification.read_at = timezone.now()

    notification.save()

    # Keep the new unified notification layer in sync without breaking the
    # legacy customer notification center. Some flows create the unified
    # notification first and then mirror a legacy CustomerNotification for the
    # old customer center; those callers pass skip_unified_sync to prevent a
    # second unified/Bale delivery for the same subject.
    if not notification_metadata.get("skip_unified_sync"):
        try:
            from apps.notifications.services import sync_legacy_customer_notification

            sync_legacy_customer_notification(notification)
        except Exception:
            pass

    return notification


def unread_notifications_count(user) -> int:
    resolved_user, _ = _resolve_user_and_customer(user=user)
    if resolved_user is None:
        return 0
    return CustomerNotification.objects.filter(user=resolved_user, is_read=False).count()


def latest_customer_notifications(user, *, limit: int = 5):
    resolved_user, _ = _resolve_user_and_customer(user=user)
    if resolved_user is None:
        return CustomerNotification.objects.none()
    return CustomerNotification.objects.filter(user=resolved_user).order_by("-created_at", "-id")[:limit]


@transaction.atomic
def mark_notifications_read(user, *, notification_ids: list[int] | None = None) -> int:
    resolved_user, _ = _resolve_user_and_customer(user=user)
    if resolved_user is None:
        return 0

    queryset = CustomerNotification.objects.filter(user=resolved_user, is_read=False)
    if notification_ids is not None:
        queryset = queryset.filter(id__in=notification_ids)

    return queryset.update(is_read=True, read_at=timezone.now())


def notify_booking_created(*, user=None, customer=None, order=None, action_url: str = ""):
    salon = _safe_getattr(order, "salon")
    salon_name = _safe_getattr(salon, "salon_name", "سالن")
    order_id = _safe_getattr(order, "id")
    if not action_url:
        action_url = _order_detail_action_url(order)

    return create_customer_notification(
        user=user,
        customer=customer,
        category=CustomerNotification.CATEGORY_BOOKING,
        title="رزرو شما ثبت شد",
        body=f"نوبت شما در {salon_name} با موفقیت ثبت شد.",
        action_url=action_url,
        priority=CustomerNotification.PRIORITY_HIGH,
        metadata={"order_id": order_id} if order_id else {},
        dedupe_key=f"booking-created:{order_id}" if order_id else "",
    )


def notify_booking_cancelled(*, user=None, customer=None, order=None, refund_amount=None, action_url: str = ""):
    order_id = _safe_getattr(order, "id")
    refund_text = ""
    try:
        amount = int(refund_amount or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount:
        refund_text = f" مبلغ {amount:,} تومان به کیف پول شما برگشت داده شد."

    return create_customer_notification(
        user=user,
        customer=customer,
        category=CustomerNotification.CATEGORY_BOOKING,
        title="نوبت شما لغو شد",
        body=f"لغو نوبت شما با موفقیت ثبت شد.{refund_text}",
        action_url=action_url or _reverse_or_fallback("orders:appointments", fallback="/orders/appointments/"),
        priority=CustomerNotification.PRIORITY_HIGH,
        metadata={"order_id": order_id, "refund_amount": amount},
        dedupe_key=f"booking-cancelled:{order_id}" if order_id else "",
    )


def notify_payment_success(*, user=None, customer=None, payment=None, order=None, action_url: str = ""):
    payment_id = _safe_getattr(payment, "id")
    resolved_order = order or _safe_getattr(payment, "order")
    order_id = _safe_getattr(resolved_order, "id")
    if not action_url:
        action_url = _order_detail_action_url(resolved_order) if resolved_order else ""

    return create_customer_notification(
        user=user,
        customer=customer,
        category=CustomerNotification.CATEGORY_PAYMENT,
        title="پرداخت موفق بود",
        body="پرداخت شما با موفقیت ثبت شد و جزئیات آن در حساب شما قابل مشاهده است.",
        action_url=action_url,
        priority=CustomerNotification.PRIORITY_HIGH,
        metadata={"payment_id": payment_id, "order_id": order_id},
        dedupe_key=f"payment-success:{payment_id}" if payment_id else "",
    )


def notify_payment_failed(*, user=None, customer=None, payment=None, order=None, action_url: str = "", title: str = ""):
    payment_id = _safe_getattr(payment, "id")
    resolved_order = order or _safe_getattr(payment, "order")
    order_id = _safe_getattr(resolved_order, "id")
    payment_state = _safe_getattr(payment, "state", "")
    if not action_url:
        action_url = _payment_result_action_url(payment) or _order_detail_action_url(resolved_order)

    return create_customer_notification(
        user=user,
        customer=customer,
        category=CustomerNotification.CATEGORY_PAYMENT,
        title=title or "پرداخت ناموفق بود",
        body="پرداخت شما کامل نشد. می‌توانید دوباره تلاش کنید یا وضعیت رزرو را بررسی کنید.",
        action_url=action_url,
        priority=CustomerNotification.PRIORITY_HIGH,
        metadata={"payment_id": payment_id, "order_id": order_id, "state": payment_state},
        dedupe_key=f"payment-failed:{payment_id}" if payment_id else "",
    )



def notify_appointment_reminder(*, user=None, customer=None, order=None, action_url: str = ""):
    """Create the in-app notification shown in the customer notification center when an appointment reminder is due."""
    order_id = _safe_getattr(order, "id")
    salon = _safe_getattr(order, "salon")
    salon_name = _safe_getattr(salon, "salon_name", "سالن")
    reminder_due_at = _safe_getattr(order, "reminder_due_at")
    reminder_due_label = ""
    if reminder_due_at:
        try:
            reminder_due_label = timezone.localtime(reminder_due_at).strftime("%H:%M")
        except Exception:
            reminder_due_label = ""

    body = f"نوبت شما در {salon_name} نزدیک است. لطفاً قبل از زمان رزرو در سالن حاضر باشید."
    if reminder_due_label:
        body = f"یادآوری نوبت شما در {salon_name} فعال شد. زمان یادآوری: {reminder_due_label}."

    return create_customer_notification(
        user=user,
        customer=customer,
        category=CustomerNotification.CATEGORY_BOOKING,
        title="یادآوری نوبت شما",
        body=body,
        action_url=action_url or _order_detail_action_url(order),
        icon="fa-regular fa-clock",
        priority=CustomerNotification.PRIORITY_HIGH,
        metadata={
            "order_id": order_id,
            "reminder_due_at": reminder_due_at.isoformat() if reminder_due_at else "",
        },
        dedupe_key=f"appointment-reminder:{order_id}:{reminder_due_at.isoformat() if reminder_due_at else 'due'}" if order_id else "",
    )

def notify_wallet_charge(*, user=None, customer=None, amount=None, transaction=None, payment=None, action_url: str = ""):
    tx_id = _safe_getattr(transaction, "id")
    payment_id = _safe_getattr(payment, "id")
    try:
        amount_int = int(amount or _safe_getattr(payment, "amount", 0) or 0)
    except (TypeError, ValueError):
        amount_int = 0
    amount_label = f" به مبلغ {amount_int:,} تومان" if amount_int else ""
    return create_customer_notification(
        user=user,
        customer=customer,
        category=CustomerNotification.CATEGORY_WALLET,
        title="کیف پول شارژ شد",
        body=f"شارژ کیف پول شما{amount_label} با موفقیت انجام شد.",
        action_url=action_url or _reverse_or_fallback("payments:detail", fallback="/payments/wallet/"),
        metadata={"transaction_id": tx_id, "payment_id": payment_id, "amount": amount_int},
        dedupe_key=f"wallet-charge:payment:{payment_id}" if payment_id else (f"wallet-charge:{tx_id}" if tx_id else ""),
    )


def notify_wallet_charge_failed(*, user=None, customer=None, amount=None, payment=None, action_url: str = "", title: str = ""):
    payment_id = _safe_getattr(payment, "id")
    payment_state = _safe_getattr(payment, "state", "")
    try:
        amount_int = int(amount or _safe_getattr(payment, "amount", 0) or 0)
    except (TypeError, ValueError):
        amount_int = 0
    amount_label = f" مبلغ {amount_int:,} تومان" if amount_int else ""
    return create_customer_notification(
        user=user,
        customer=customer,
        category=CustomerNotification.CATEGORY_WALLET,
        title=title or "شارژ کیف پول ناموفق بود",
        body=f"شارژ کیف پول شما{amount_label} کامل نشد. می‌توانید دوباره تلاش کنید.",
        action_url=action_url or _reverse_or_fallback("payments:charge", fallback="/payments/wallet/charge/"),
        priority=CustomerNotification.PRIORITY_HIGH,
        metadata={"payment_id": payment_id, "amount": amount_int, "state": payment_state},
        dedupe_key=f"wallet-charge-failed:{payment_id}:{payment_state}" if payment_id else "",
    )


def notify_wallet_withdraw_requested(*, user=None, customer=None, amount=None, withdrawal=None, action_url: str = ""):
    withdrawal_id = _safe_getattr(withdrawal, "id")
    try:
        amount_int = int(amount or _safe_getattr(withdrawal, "amount", 0) or 0)
    except (TypeError, ValueError):
        amount_int = 0
    amount_label = f" به مبلغ {amount_int:,} تومان" if amount_int else ""
    return create_customer_notification(
        user=user,
        customer=customer,
        category=CustomerNotification.CATEGORY_WALLET,
        title="درخواست برداشت ثبت شد",
        body=f"درخواست برداشت شما{amount_label} ثبت شد و پس از بررسی انجام می‌شود.",
        action_url=action_url or _reverse_or_fallback("payments:withdraw", fallback="/payments/wallet/withdraw/"),
        metadata={"withdrawal_id": withdrawal_id, "amount": amount_int},
        dedupe_key=f"wallet-withdraw-requested:{withdrawal_id}" if withdrawal_id else "",
    )


def notify_wallet_withdraw_cancelled(*, user=None, customer=None, amount=None, withdrawal=None, action_url: str = ""):
    withdrawal_id = _safe_getattr(withdrawal, "id")
    try:
        amount_int = int(amount or _safe_getattr(withdrawal, "amount", 0) or 0)
    except (TypeError, ValueError):
        amount_int = 0
    amount_label = f" مبلغ {amount_int:,} تومان" if amount_int else ""
    return create_customer_notification(
        user=user,
        customer=customer,
        category=CustomerNotification.CATEGORY_WALLET,
        title="درخواست برداشت لغو شد",
        body=f"درخواست برداشت شما لغو شد و{amount_label} به کیف پول برگشت داده شد.",
        action_url=action_url or _reverse_or_fallback("payments:detail", fallback="/payments/wallet/"),
        metadata={"withdrawal_id": withdrawal_id, "amount": amount_int},
        dedupe_key=f"wallet-withdraw-cancelled:{withdrawal_id}" if withdrawal_id else "",
    )


def notify_support_ticket_created(*, user=None, customer=None, ticket=None, action_url: str = ""):
    ticket_id = _safe_getattr(ticket, "id")
    reason = _safe_getattr(ticket, "support_reason", "")
    reason_text = f" با موضوع «{reason}»" if reason else ""
    return create_customer_notification(
        user=user,
        customer=customer,
        category=CustomerNotification.CATEGORY_SUPPORT,
        title="درخواست پشتیبانی ثبت شد",
        body=f"درخواست پشتیبانی شما{reason_text} ثبت شد و از همین بخش قابل پیگیری است.",
        action_url=action_url or _reverse_or_fallback("main:contact", fallback="/support/"),
        metadata={"ticket_id": ticket_id},
        dedupe_key=f"support-created:{ticket_id}" if ticket_id else "",
    )


def notify_support_reply(*, user=None, customer=None, ticket=None, action_url: str = ""):
    ticket_id = _safe_getattr(ticket, "id")
    reply_text = str(_safe_getattr(ticket, "admin_reply", "") or "").strip()
    reply_hash = hashlib.sha1(reply_text.encode("utf-8")).hexdigest()[:12] if reply_text else "empty"
    return create_customer_notification(
        user=user,
        customer=customer,
        category=CustomerNotification.CATEGORY_SUPPORT,
        title="پاسخ پشتیبانی ثبت شد",
        body="تیم پشتیبانی به درخواست شما پاسخ داده است.",
        action_url=action_url or _reverse_or_fallback("main:contact", fallback="/support/"),
        metadata={"ticket_id": ticket_id, "reply_hash": reply_hash},
        dedupe_key=f"support-reply:{ticket_id}:{reply_hash}" if ticket_id else "",
    )
