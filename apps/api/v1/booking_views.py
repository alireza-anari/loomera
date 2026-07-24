from __future__ import annotations

from datetime import datetime, timedelta
from apps.accounts.models import Stylist
from django.conf import settings
from django.contrib.auth import get_user
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from django.db import transaction
from django.utils import timezone
from apps.orders.models import Order, OrderDetail
from apps.orders.booking_utils import (
    DEFAULT_SLOT_STEP,
    get_available_slots_for_service,
    get_price_for_stylist_service,
    get_service_buffer_minutes,
    get_service_duration_minutes,
)
from apps.stylists.profile_services import can_show_stylist_on_salon_profile

from .availability_views import (
    _clean_positive_int,
    _date_allowed,
    _parse_api_date,
    _public_service_for_salon,
)
from .public_views import _get_public_salon_by_slug
from .responses import api_error, api_success


def _django_request(request):
    return getattr(request, "_request", request)


def _django_session_user(request):
    django_request = _django_request(request)
    user = get_user(django_request)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


def _request_payload_too_large(request) -> bool:
    max_bytes = int(
        getattr(settings, "LOOMERA_API_BOOKING_DRAFT_MAX_BYTES", 4 * 1024) or 4 * 1024
    )

    content_length = request.META.get("CONTENT_LENGTH")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                return True
        except ValueError:
            return True

    raw_body = getattr(request, "body", b"") or b""
    return len(raw_body) > max_bytes


def _parse_api_time(value):
    raw_value = str(value or "").strip()
    if not raw_value:
        return None

    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return (
                datetime.strptime(raw_value, fmt)
                .time()
                .replace(second=0, microsecond=0)
            )
        except ValueError:
            continue

    return None


def _booking_validation_error(reason: str, message: str, *, status: int = 200):
    return api_success(
        {
            "valid": False,
            "reason": reason,
            "message": message,
        },
        status=status,
    )


def _get_visible_booking_stylist(*, salon, service, stylist_id):
    parsed_stylist_id = _clean_positive_int(stylist_id)
    if parsed_stylist_id is None:
        return None

    stylist = (
        salon.stylists.filter(
            pk=parsed_stylist_id,
            is_active=True,
            services_of_stylist=service,
        )
        .select_related("user")
        .distinct()
        .first()
    )

    if stylist is None:
        return None

    access = can_show_stylist_on_salon_profile(salon=salon, stylist=stylist)
    if not access.allowed:
        return None

    return stylist


def _serialize_booking_draft_payload(
    *, salon, service, stylist, date_value, start_time, end_time
):
    return {
        "valid": True,
        "reason": None,
        "salon": {
            "id": salon.pk,
            "slug": salon.slug,
            "name": salon.salon_name,
        },
        "service": {
            "id": service.pk,
            "slug": service.slug,
            "name": service.service_name,
            "duration_minutes": int(get_service_duration_minutes(service)),
            "buffer_minutes": int(get_service_buffer_minutes(service)),
        },
        "stylist": {
            "id": stylist.pk,
            "display_name": stylist.professional_display_name,
            "expert": stylist.expert or "",
            "price": int(get_price_for_stylist_service(stylist, service) or 0),
        },
        "slot": {
            "date": date_value.isoformat(),
            "start_time": start_time.strftime("%H:%M"),
            "end_time": end_time.strftime("%H:%M"),
        },
        "booking_mode": "pay_in_salon",
        "slot_step_minutes": DEFAULT_SLOT_STEP,
        "creates_order": False,
        "locks_slot": False,
    }


def _serialize_booking_draft_summary_payload(
    *,
    salon,
    service,
    stylist,
    date_value,
    start_time,
    end_time,
):
    service_price = int(get_price_for_stylist_service(stylist, service) or 0)
    discount_amount = 0
    total_price = max(service_price - discount_amount, 0)

    online_payment_enabled = bool(getattr(settings, "ONLINE_PAYMENT_ENABLED", False))

    return {
        "valid": True,
        "reason": None,
        "salon": {
            "id": salon.pk,
            "slug": salon.slug,
            "name": salon.salon_name,
        },
        "service": {
            "id": service.pk,
            "slug": service.slug,
            "name": service.service_name,
            "duration_minutes": int(get_service_duration_minutes(service)),
            "buffer_minutes": int(get_service_buffer_minutes(service)),
        },
        "stylist": {
            "id": stylist.pk,
            "display_name": stylist.professional_display_name,
            "expert": stylist.expert or "",
        },
        "slot": {
            "date": date_value.isoformat(),
            "start_time": start_time.strftime("%H:%M"),
            "end_time": end_time.strftime("%H:%M"),
        },
        "price": {
            "service_price": service_price,
            "discount_amount": discount_amount,
            "total_price": total_price,
            "currency": "IRR",
        },
        "payment": {
            "mode": "pay_in_salon",
            "online_payment_enabled": online_payment_enabled,
            "amount_due_now": 0,
            "amount_payable_at_salon": total_price,
        },
        "booking_mode": "pay_in_salon",
        "summary": {
            "title": service.service_name,
            "subtitle": f"{salon.salon_name} - {stylist.professional_display_name}",
            "duration_minutes": int(get_service_duration_minutes(service)),
            "buffer_minutes": int(get_service_buffer_minutes(service)),
        },
        "creates_order": False,
        "locks_slot": False,
    }


def _clean_booking_payment_method(payload) -> str:
    return (
        str(payload.get("payment_method") or "pay_in_salon").strip() or "pay_in_salon"
    )


def _occupied_until_for_slot(
    *, date_value, start_time, duration_minutes, buffer_minutes
):
    occupied_until_dt = datetime.combine(date_value, start_time) + timedelta(
        minutes=int(duration_minutes or 0) + int(buffer_minutes or 0)
    )
    return occupied_until_dt.time().replace(second=0, microsecond=0)


def _serialize_confirmed_booking_payload(
    *, order, appointment, salon, service, stylist
):
    return {
        "confirmed": True,
        "booking_mode": "pay_in_salon",
        "order": {
            "id": order.pk,
            "number": order.order_number,
            "status": order.status,
            "is_paid": bool(order.is_paid),
            "is_finally": bool(order.is_finally),
            "selected_payment_method": order.selected_payment_method,
            "total_amount": int(order.total_amount or 0),
        },
        "appointment": {
            "id": appointment.pk,
            "confirmation_status": appointment.confirmation_status,
            "lifecycle_status": appointment.lifecycle_status,
        },
        "salon": {
            "id": salon.pk,
            "slug": salon.slug,
            "name": salon.salon_name,
        },
        "service": {
            "id": service.pk,
            "slug": service.slug,
            "name": service.service_name,
            "duration_minutes": int(get_service_duration_minutes(service)),
            "buffer_minutes": int(get_service_buffer_minutes(service)),
        },
        "stylist": {
            "id": stylist.pk,
            "display_name": stylist.professional_display_name,
            "expert": stylist.expert or "",
        },
        "slot": {
            "date": appointment.date.isoformat(),
            "start_time": appointment.time.strftime("%H:%M"),
            "end_time": appointment.end_time.strftime("%H:%M"),
            "occupied_until": (
                appointment.occupied_until.strftime("%H:%M")
                if appointment.occupied_until
                else appointment.end_time.strftime("%H:%M")
            ),
            "status": "booked",
        },
        "price": {
            "service_price": int(appointment.price or 0),
            "discount_amount": 0,
            "total_price": int(order.total_amount or 0),
            "currency": "IRR",
        },
        "payment": {
            "mode": "pay_in_salon",
            "online_payment_enabled": bool(
                getattr(settings, "ONLINE_PAYMENT_ENABLED", False)
            ),
            "amount_due_now": 0,
            "amount_payable_at_salon": int(order.total_amount or 0),
            "payment_created": False,
        },
        "side_effects": {
            "payment_created": False,
            "wallet_changed": False,
            "notification_sent": False,
            "settlement_synced": False,
        },
    }


class ApiBookingDraftValidateAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        if _request_payload_too_large(request):
            return api_error(
                "payload_too_large",
                "حجم درخواست بیش از حد مجاز است.",
                status=413,
            )

        user = _django_session_user(request)
        if user is None:
            return api_error(
                "authentication_required",
                "برای اعتبارسنجی رزرو باید وارد حساب کاربری شوید.",
                status=401,
            )

        if not hasattr(user, "customer_profile"):
            return api_error(
                "customer_profile_required",
                "فقط کاربر مشتری می‌تواند رزرو ایجاد کند.",
                status=403,
            )

        payload = request.data
        if not isinstance(payload, dict):
            return api_error(
                "invalid_payload",
                "ساختار درخواست معتبر نیست.",
                status=400,
            )

        salon_slug = str(payload.get("salon_slug") or "").strip()
        if not salon_slug:
            return api_error(
                "missing_salon",
                "شناسه سالن الزامی است.",
                status=400,
            )

        salon = _get_public_salon_by_slug(salon_slug)
        if salon is None:
            return api_error(
                "salon_not_found",
                "سالن پیدا نشد.",
                status=404,
            )

        service = _public_service_for_salon(salon, payload.get("service_id"))
        if service is None:
            return api_error(
                "service_not_found",
                "خدمت پیدا نشد.",
                status=404,
            )

        stylist = _get_visible_booking_stylist(
            salon=salon,
            service=service,
            stylist_id=payload.get("stylist_id"),
        )
        if stylist is None:
            return api_error(
                "stylist_not_found",
                "متخصص پیدا نشد.",
                status=404,
            )

        date_value = _parse_api_date(payload.get("date"))
        if date_value is None:
            return api_error(
                "invalid_date",
                "تاریخ باید با فرمت YYYY-MM-DD ارسال شود.",
                status=400,
            )

        if not _date_allowed(date_value):
            return api_error(
                "date_out_of_range",
                "تاریخ انتخاب‌شده در بازه مجاز رزرو نیست.",
                status=400,
            )

        start_time = _parse_api_time(payload.get("start_time"))
        if start_time is None:
            return api_error(
                "invalid_start_time",
                "ساعت شروع باید با فرمت HH:MM ارسال شود.",
                status=400,
            )

        available_slots = get_available_slots_for_service(
            salon=salon,
            stylist=stylist,
            service=service,
            date_value=date_value,
        )

        matched_slot = None
        for slot_start, slot_end in available_slots:
            if slot_start == start_time:
                matched_slot = (slot_start, slot_end)
                break

        if matched_slot is None:
            return _booking_validation_error(
                "slot_unavailable",
                "این زمان دیگر قابل رزرو نیست.",
            )

        slot_start, slot_end = matched_slot
        return api_success(
            _serialize_booking_draft_payload(
                salon=salon,
                service=service,
                stylist=stylist,
                date_value=date_value,
                start_time=slot_start,
                end_time=slot_end,
            )
        )


class ApiBookingDraftSummaryAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        if _request_payload_too_large(request):
            return api_error(
                "payload_too_large",
                "حجم درخواست بیش از حد مجاز است.",
                status=413,
            )

        user = _django_session_user(request)
        if user is None:
            return api_error(
                "authentication_required",
                "برای دریافت خلاصه رزرو باید وارد حساب کاربری شوید.",
                status=401,
            )

        if not hasattr(user, "customer_profile"):
            return api_error(
                "customer_profile_required",
                "فقط کاربر مشتری می‌تواند رزرو ایجاد کند.",
                status=403,
            )

        payload = request.data
        if not isinstance(payload, dict):
            return api_error(
                "invalid_payload",
                "ساختار درخواست معتبر نیست.",
                status=400,
            )

        salon_slug = str(payload.get("salon_slug") or "").strip()
        if not salon_slug:
            return api_error(
                "missing_salon",
                "شناسه سالن الزامی است.",
                status=400,
            )

        salon = _get_public_salon_by_slug(salon_slug)
        if salon is None:
            return api_error(
                "salon_not_found",
                "سالن پیدا نشد.",
                status=404,
            )

        service = _public_service_for_salon(salon, payload.get("service_id"))
        if service is None:
            return api_error(
                "service_not_found",
                "خدمت پیدا نشد.",
                status=404,
            )

        stylist = _get_visible_booking_stylist(
            salon=salon,
            service=service,
            stylist_id=payload.get("stylist_id"),
        )
        if stylist is None:
            return api_error(
                "stylist_not_found",
                "متخصص پیدا نشد.",
                status=404,
            )

        date_value = _parse_api_date(payload.get("date"))
        if date_value is None:
            return api_error(
                "invalid_date",
                "تاریخ باید با فرمت YYYY-MM-DD ارسال شود.",
                status=400,
            )

        if not _date_allowed(date_value):
            return api_error(
                "date_out_of_range",
                "تاریخ انتخاب‌شده در بازه مجاز رزرو نیست.",
                status=400,
            )

        start_time = _parse_api_time(payload.get("start_time"))
        if start_time is None:
            return api_error(
                "invalid_start_time",
                "ساعت شروع باید با فرمت HH:MM ارسال شود.",
                status=400,
            )

        available_slots = get_available_slots_for_service(
            salon=salon,
            stylist=stylist,
            service=service,
            date_value=date_value,
        )

        matched_slot = None
        for slot_start, slot_end in available_slots:
            if slot_start == start_time:
                matched_slot = (slot_start, slot_end)
                break

        if matched_slot is None:
            return _booking_validation_error(
                "slot_unavailable",
                "این زمان دیگر قابل رزرو نیست.",
            )

        slot_start, slot_end = matched_slot
        return api_success(
            _serialize_booking_draft_summary_payload(
                salon=salon,
                service=service,
                stylist=stylist,
                date_value=date_value,
                start_time=slot_start,
                end_time=slot_end,
            )
        )


class ApiBookingConfirmAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        if _request_payload_too_large(request):
            return api_error(
                "payload_too_large",
                "حجم درخواست بیش از حد مجاز است.",
                status=413,
            )

        user = _django_session_user(request)
        if user is None:
            return api_error(
                "authentication_required",
                "برای ثبت رزرو باید وارد حساب کاربری شوید.",
                status=401,
            )

        customer = getattr(user, "customer_profile", None)
        if customer is None:
            return api_error(
                "customer_profile_required",
                "فقط کاربر مشتری می‌تواند رزرو ایجاد کند.",
                status=403,
            )

        payload = request.data
        if not isinstance(payload, dict):
            return api_error(
                "invalid_payload",
                "ساختار درخواست معتبر نیست.",
                status=400,
            )

        payment_method = _clean_booking_payment_method(payload)
        if payment_method != "pay_in_salon":
            return api_error(
                "unsupported_payment_method",
                "در این نسخه فقط پرداخت در سالن پشتیبانی می‌شود.",
                status=400,
            )

        salon_slug = str(payload.get("salon_slug") or "").strip()
        if not salon_slug:
            return api_error(
                "missing_salon",
                "شناسه سالن الزامی است.",
                status=400,
            )

        salon = _get_public_salon_by_slug(salon_slug)
        if salon is None:
            return api_error(
                "salon_not_found",
                "سالن پیدا نشد.",
                status=404,
            )

        service = _public_service_for_salon(salon, payload.get("service_id"))
        if service is None:
            return api_error(
                "service_not_found",
                "خدمت پیدا نشد.",
                status=404,
            )

        stylist = _get_visible_booking_stylist(
            salon=salon,
            service=service,
            stylist_id=payload.get("stylist_id"),
        )
        if stylist is None:
            return api_error(
                "stylist_not_found",
                "متخصص پیدا نشد.",
                status=404,
            )

        date_value = _parse_api_date(payload.get("date"))
        if date_value is None:
            return api_error(
                "invalid_date",
                "تاریخ باید با فرمت YYYY-MM-DD ارسال شود.",
                status=400,
            )

        if not _date_allowed(date_value):
            return api_error(
                "date_out_of_range",
                "تاریخ انتخاب‌شده در بازه مجاز رزرو نیست.",
                status=400,
            )

        start_time = _parse_api_time(payload.get("start_time"))
        if start_time is None:
            return api_error(
                "invalid_start_time",
                "ساعت شروع باید با فرمت HH:MM ارسال شود.",
                status=400,
            )

        try:
            with transaction.atomic():
                locked_stylist = (
                    Stylist.objects.select_for_update()
                    .select_related("user")
                    .get(pk=stylist.pk)
                )

                if not locked_stylist.is_active:
                    return api_error(
                        "stylist_not_found",
                        "متخصص پیدا نشد.",
                        status=404,
                    )

                still_visible = can_show_stylist_on_salon_profile(
                    salon=salon,
                    stylist=locked_stylist,
                )
                if not still_visible.allowed:
                    return api_error(
                        "stylist_not_found",
                        "متخصص پیدا نشد.",
                        status=404,
                    )

                still_linked = salon.stylists.filter(
                    pk=locked_stylist.pk,
                    services_of_stylist=service,
                    is_active=True,
                ).exists()
                if not still_linked:
                    return api_error(
                        "stylist_not_found",
                        "متخصص پیدا نشد.",
                        status=404,
                    )

                available_slots = get_available_slots_for_service(
                    salon=salon,
                    stylist=locked_stylist,
                    service=service,
                    date_value=date_value,
                )

                matched_slot = None
                for slot_start, slot_end in available_slots:
                    if slot_start == start_time:
                        matched_slot = (slot_start, slot_end)
                        break

                if matched_slot is None:
                    return api_error(
                        "slot_unavailable",
                        "این زمان دیگر قابل رزرو نیست.",
                        status=409,
                    )

                slot_start, slot_end = matched_slot
                duration_minutes = int(get_service_duration_minutes(service))
                buffer_minutes = int(get_service_buffer_minutes(service))
                occupied_until = _occupied_until_for_slot(
                    date_value=date_value,
                    start_time=slot_start,
                    duration_minutes=duration_minutes,
                    buffer_minutes=buffer_minutes,
                )
                price = int(get_price_for_stylist_service(locked_stylist, service) or 0)

                order = Order.objects.create(
                    customer=customer,
                    salon=salon,
                    status="pending",
                    is_finally=True,
                    is_paid=False,
                    selected_payment_method="pay_in_salon",
                    requires_online_payment=False,
                    subtotal_amount=price,
                    discount_amount=0,
                    basket_discount_amount=0,
                    coupon_discount_amount=0,
                    basket_discount_percent=0,
                    basket_discount_title="",
                    tax_amount=0,
                    total_amount=price,
                    coupon_code="",
                    discount=0,
                    platform_commission_applies=False,
                    platform_commission_percent=0,
                    platform_commission_amount=0,
                    salon_payout_amount=price,
                    checkout_locked_at=timezone.now(),
                    booking_source="customer",
                )

                appointment = OrderDetail.objects.create(
                    order=order,
                    service=service,
                    stylist=locked_stylist,
                    salon=salon,
                    price=price,
                    date=date_value,
                    time=slot_start,
                    end_time=slot_end,
                    scheduled_duration_minutes=duration_minutes,
                    buffer_minutes=buffer_minutes,
                    occupied_until=occupied_until,
                )

        except Stylist.DoesNotExist:
            return api_error(
                "stylist_not_found",
                "متخصص پیدا نشد.",
                status=404,
            )

        return api_success(
            _serialize_confirmed_booking_payload(
                order=order,
                appointment=appointment,
                salon=salon,
                service=service,
                stylist=locked_stylist,
            ),
            status=201,
        )
