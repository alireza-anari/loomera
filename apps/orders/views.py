import json
import logging
import hashlib
from datetime import date, datetime, timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Prefetch, Avg, Count
from django.forms import ValidationError
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_GET
from khayyam import JalaliDate
from apps.accounts.models import Customer, Stylist
from apps.salons.models import Salon
from apps.services.models import ServicePrice, Services
from apps.stylists.models import StaffLeaveRequest, StylistSchedule
from .booking_utils import (
    BLOCKING_STATUSES,
    build_cancellation_policy,
    get_service_buffer_minutes,
    get_blocking_order_details_queryset,
    get_upcoming_available_stylists_for_service,
    resolve_best_available_stylist_for_service,
    resolve_booking_sequence,
)
from .forms import OrderForm, AppointmentCheckoutForm
from .models import Order, OrderDetail
from .lifecycle import (
    build_notification_meta,
    cancel_order_reminder,
    build_customer_progress_context,
    create_notification,
    get_customer_notifications,
    mark_review_requested,
    notify_manager_and_stylists_for_booking,
    notify_operational_milestone,
    queue_customer_booking_cancelled_sms,
    queue_customer_booking_rescheduled_sms,
    schedule_order_reminder,
)
from apps.accounts.notifications import (
    notify_booking_cancelled,
    notify_booking_created,
    notify_payment_failed,
    notify_payment_success,
)
from .quick_links import (
    consume_booking_quick_link_from_session,
    record_booking_quick_link_opened,
    record_booking_quick_link_started,
    resolve_booking_quick_link_token,
)
from collections import defaultdict
from django.db import transaction
from django.db import IntegrityError
from apps.dashboards.jalali_utils import (
    format_jalali_numeric,
    format_jalali_with_weekday,
    format_time_fa,
)
from apps.comments_scores_favories.models import Comments, Scoring

logger = logging.getLogger(__name__)

PUBLIC_BOOKING_STYLIST_VISIBILITIES = (
    Stylist.PublicVisibility.PUBLIC,
    Stylist.PublicVisibility.SALON_ONLY,
)

APPOINTMENT_CHECKOUT_FORM_ACTIONS = {
    "",
    "apply_coupon",
    "clear_coupon",
    "confirm_checkout",
}


def _appointment_checkout_post_max_bytes():
    return max(
        int(getattr(settings, "APPOINTMENT_CHECKOUT_POST_MAX_BYTES", 8 * 1024) or 1),
        1,
    )


def _appointment_checkout_coupon_code_max_chars():
    return max(
        int(getattr(settings, "APPOINTMENT_CHECKOUT_COUPON_CODE_MAX_CHARS", 64) or 1),
        1,
    )


def _clean_appointment_checkout_coupon_code(raw_code):
    code = str(raw_code or "").strip()
    code = code.replace("\r", "").replace("\n", "").replace("\x00", "")

    if len(code) > _appointment_checkout_coupon_code_max_chars():
        raise ValidationError("کد تخفیف بیش از حد مجاز است.")

    return code


def _clean_appointment_checkout_form_action(request):
    if _request_body_too_large(
        request,
        _appointment_checkout_post_max_bytes(),
    ):
        raise ValidationError("حجم اطلاعات ارسالی بیش از حد مجاز است.")

    action = (request.POST.get("form_action") or "").strip()

    if action not in APPOINTMENT_CHECKOUT_FORM_ACTIONS:
        raise ValidationError("عملیات checkout معتبر نیست.")

    return action


def _parse_positive_int_param(value):
    text = str(value or "").strip()
    if not text.isdigit():
        return None

    parsed = int(text)
    return parsed if parsed > 0 else None


def _json_error(message, *, status=400):
    return JsonResponse(
        {"error": message},
        status=status,
        json_dumps_params={"ensure_ascii": False},
    )


def _public_booking_salon_or_response(salon_id):
    parsed_salon_id = _parse_positive_int_param(salon_id)
    if parsed_salon_id is None:
        return None, _json_error("مجموعه معتبر نیست", status=400)

    salon = (
        Salon.objects.filter(
            pk=parsed_salon_id,
            is_active=True,
        )
        .select_related("salon_manager__user")
        .first()
    )

    if salon is None:
        return None, _json_error("مجموعه معتبر نیست", status=404)

    return salon, None


def _public_booking_service_or_response(salon, service_id):
    parsed_service_id = _parse_positive_int_param(service_id)
    if parsed_service_id is None:
        return None, _json_error("خدمت معتبر نیست", status=400)

    service = (
        _public_booking_service_queryset(salon)
        .filter(pk=parsed_service_id)
        .prefetch_related("service_group")
        .first()
    )

    if service is None:
        return None, _json_error("خدمت معتبر نیست", status=404)

    return service, None


def _public_booking_stylist_queryset(salon):
    return salon.stylists.filter(
        is_active=True,
        public_visibility__in=PUBLIC_BOOKING_STYLIST_VISIBILITIES,
    ).distinct()


def _public_booking_service_queryset(salon):
    """Return services that may participate in public salon booking.

    A service is publicly bookable when it is active, attached to the active
    salon, and is either a platform-catalog record or a salon-owned version
    created from a platform-catalog source.

    Arbitrary private services without a catalog source remain excluded.
    """

    return (
        Services.objects.filter(
            services_of_salon=salon,
            is_active=True,
        )
        .filter(Q(is_platform_catalog=True) | Q(catalog_source__isnull=False))
        .distinct()
    )


def _quick_booking_parse_service_ids(raw_service_ids):
    parsed_ids = []

    for raw_id in raw_service_ids or []:
        parsed_id = _parse_positive_int_param(raw_id)
        if parsed_id is None:
            return None
        if parsed_id not in parsed_ids:
            parsed_ids.append(parsed_id)

    return parsed_ids


def _quick_booking_parse_iso_date(raw_date):
    raw_date = str(raw_date or "").strip()
    if not raw_date:
        return None

    try:
        return date.fromisoformat(raw_date)
    except ValueError:
        return None


def _quick_booking_parse_time(raw_time):
    raw_time = str(raw_time or "").strip()
    if not raw_time:
        return None

    try:
        return datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        return None


def _quick_booking_time_payload_is_valid(payload):
    selected_date = _quick_booking_parse_iso_date(payload.get("date"))
    selected_time = _quick_booking_parse_time(payload.get("time"))

    if selected_date is None or selected_time is None:
        return False

    return selected_date >= timezone.localdate()


def _booking_selected_service_ids_from_session(request):
    service_ids = []
    raw_selections = request.session.get("stylist_selections") or []

    if not isinstance(raw_selections, list):
        return service_ids

    for raw_selection in raw_selections:
        if not isinstance(raw_selection, dict):
            continue

        parsed_id = _parse_positive_int_param(
            raw_selection.get("serviceId") or raw_selection.get("service_id")
        )
        if parsed_id and parsed_id not in service_ids:
            service_ids.append(parsed_id)

    return service_ids


def _clear_public_booking_session_state(request):
    """
    Clear all untrusted public-booking selections from the session.

    This is the fail-closed reset for an invalid salon, service, stylist, or
    datetime payload. It removes ``salon_id``, ``stylist_selections``, and
    ``datetime_selections`` together so a partial selection cannot reach checkout.
    """
    for key in (
        "salon_id",
        "stylist_selections",
        "datetime_selections",
    ):
        request.session.pop(key, None)

    request.session.modified = True


def _public_booking_salon_or_none(salon_id):
    parsed_salon_id = _parse_positive_int_param(salon_id)

    if parsed_salon_id is None:
        return None

    return Salon.objects.filter(
        pk=parsed_salon_id,
        is_active=True,
    ).first()


def _public_booking_selection_stylist_ids(selection):
    requested_id = str(
        selection.get("requestedStylistId") or selection.get("stylistId") or ""
    ).strip()

    stylist_id = str(selection.get("stylistId") or requested_id).strip()

    resolved_id = str(selection.get("resolvedStylistId") or stylist_id).strip()

    if requested_id != "any" and _parse_positive_int_param(requested_id) is None:
        raise ValidationError("متخصص انتخاب‌شده معتبر نیست.")

    for candidate_id in (stylist_id, resolved_id):
        if candidate_id == "any":
            continue

        if _parse_positive_int_param(candidate_id) is None:
            raise ValidationError("متخصص انتخاب‌شده معتبر نیست.")

    explicit_effective_ids = {
        candidate_id
        for candidate_id in (stylist_id, resolved_id)
        if candidate_id and candidate_id != "any"
    }

    if len(explicit_effective_ids) > 1:
        raise ValidationError("متخصص انتخاب‌شده معتبر نیست.")

    effective_id = (
        next(iter(explicit_effective_ids)) if explicit_effective_ids else "any"
    )

    if requested_id != "any" and effective_id != requested_id:
        raise ValidationError("متخصص انتخاب‌شده معتبر نیست.")

    return requested_id, effective_id


def _validate_public_booking_stylist_selections(
    *,
    salon,
    stylist_selections,
):
    """
    Validate client-supplied service and stylist selections before persistence.

    Every service must be active, public, and attached to the active salon. An
    explicit stylist must be public, active, attached to that salon, and provide
    the selected service. Requested and resolved stylist identifiers must not
    contradict each other. The special ``any`` choice is preserved for later
    resolution. This function validates and normalizes data; it does not write the
    session and does not reserve availability.
    """
    if not isinstance(stylist_selections, list) or not stylist_selections:
        raise ValidationError("اطلاعات خدمات و متخصصان معتبر نیست.")

    parsed_selections = []
    service_ids = []

    for selection in stylist_selections:
        if not isinstance(selection, dict):
            raise ValidationError("اطلاعات خدمات و متخصصان معتبر نیست.")

        service_id = _parse_positive_int_param(
            selection.get("serviceId") or selection.get("service_id")
        )

        if service_id is None:
            raise ValidationError("خدمت انتخاب‌شده معتبر نیست.")

        requested_id, effective_id = _public_booking_selection_stylist_ids(selection)

        parsed_selections.append(
            {
                "selection": selection,
                "service_id": service_id,
                "requested_id": requested_id,
                "effective_id": effective_id,
            }
        )

        if service_id not in service_ids:
            service_ids.append(service_id)

    services_map = {
        service.pk: service
        for service in _public_booking_service_queryset(salon).filter(
            pk__in=service_ids
        )
    }

    if set(services_map) != set(service_ids):
        raise ValidationError("یک یا چند خدمت انتخاب‌شده معتبر نیست.")

    for item in parsed_selections:
        service = services_map[item["service_id"]]

        stylist_ids_to_validate = {
            stylist_id
            for stylist_id in (
                item["requested_id"],
                item["effective_id"],
            )
            if stylist_id != "any"
        }

        for stylist_id in stylist_ids_to_validate:
            is_valid_stylist = (
                _public_booking_stylist_queryset(salon)
                .filter(
                    user_id=int(stylist_id),
                    services_of_stylist=service,
                )
                .exists()
            )

            if not is_valid_stylist:
                raise ValidationError("متخصص انتخاب‌شده معتبر نیست.")

    return parsed_selections, services_map


def _validate_public_booking_datetime_selections(
    *,
    salon,
    stylist_selections,
    datetime_selections,
):
    """
    Validate the exact datetime mapping for the selected booking sequence.

    The service/stylist selections are revalidated first. Each selection must have
    exactly one matching datetime entry, dates cannot be in the past, stylist IDs
    must match the requested or resolved stylist, and extra datetime keys are
    rejected. This function does not persist the session and does not replace the
    final availability check performed inside checkout locking.
    """
    parsed_selections, _ = _validate_public_booking_stylist_selections(
        salon=salon,
        stylist_selections=stylist_selections,
    )

    if not isinstance(datetime_selections, dict) or not datetime_selections:
        raise ValidationError("تاریخ و زمان انتخاب‌شده معتبر نیست.")

    used_keys = set()

    for item in parsed_selections:
        service_id = item["service_id"]

        candidate_stylist_ids = [
            item["requested_id"],
        ]

        if item["effective_id"] not in candidate_stylist_ids:
            candidate_stylist_ids.append(item["effective_id"])

        candidate_keys = [
            f"{stylist_id}_{service_id}" for stylist_id in candidate_stylist_ids
        ]

        matching_keys = [key for key in candidate_keys if key in datetime_selections]

        if len(matching_keys) != 1:
            raise ValidationError("تاریخ و زمان انتخاب‌شده معتبر نیست.")

        selection_key = matching_keys[0]
        datetime_info = datetime_selections.get(selection_key)

        if not isinstance(datetime_info, dict):
            raise ValidationError("تاریخ و زمان انتخاب‌شده معتبر نیست.")

        selected_date = _quick_booking_parse_iso_date(datetime_info.get("date"))
        selected_time = _quick_booking_parse_time(datetime_info.get("time"))

        if (
            selected_date is None
            or selected_time is None
            or selected_date < timezone.localdate()
        ):
            raise ValidationError("تاریخ و زمان انتخاب‌شده معتبر نیست.")

        payload_stylist_id = str(
            datetime_info.get("stylistId") or datetime_info.get("stylist_id") or ""
        ).strip()

        allowed_payload_ids = {
            item["requested_id"],
            item["effective_id"],
        }

        if payload_stylist_id and payload_stylist_id not in allowed_payload_ids:
            raise ValidationError("متخصص انتخاب‌شده معتبر نیست.")

        used_keys.add(selection_key)

    if set(datetime_selections) != used_keys:
        raise ValidationError("اطلاعات تاریخ و زمان شامل داده نامعتبر است.")


def _validate_jalali_month_year(month, year):
    parsed_month = _parse_positive_int_param(month)
    parsed_year = _parse_positive_int_param(year)

    if parsed_month is None or parsed_year is None:
        return None, None

    if parsed_month < 1 or parsed_month > 12:
        return None, None

    # بازه محافظه‌کارانه برای جلوگیری از queryهای عجیب یا تاریخ‌های نامعتبر
    if parsed_year < 1300 or parsed_year > 1600:
        return None, None

    return parsed_month, parsed_year


def _notify_manager_and_stylists_for_customer_order_event(
    order,
    *,
    event_type,
    manager_title,
    stylist_title,
    body,
    detail_meta=None,
):
    """
    اعلان dashboard برای مدیر و متخصص‌ها در رخدادهای مشتری‌محور:
    لغو توسط مشتری، تغییر زمان توسط مشتری و موارد مشابه.
    """
    order = (
        Order.objects.select_related("customer__user", "salon__salon_manager__user")
        .prefetch_related("order_details1__stylist__user", "order_details1__service")
        .get(pk=order.pk)
    )

    meta_label = build_notification_meta(order)
    common_meta = {
        "order_id": order.pk,
        "date_label": meta_label,
        **(detail_meta or {}),
    }

    manager_user = (
        getattr(getattr(order.salon, "salon_manager", None), "user", None)
        if order.salon_id
        else None
    )

    if manager_user:
        create_notification(
            order=order,
            audience_role="manager",
            channel="dashboard",
            event_type=event_type,
            title=manager_title,
            body=body,
            target_user=manager_user,
            delivery_status="sent",
            meta={**common_meta, "panel": "manager"},
        )

    notified_stylist_ids = set()
    for item in order.order_details1.all():
        stylist = item.stylist
        if not stylist or stylist.pk in notified_stylist_ids:
            continue

        notified_stylist_ids.add(stylist.pk)

        create_notification(
            order=order,
            order_detail=item,
            audience_role="stylist",
            channel="dashboard",
            event_type=event_type,
            title=stylist_title,
            body=body,
            stylist=stylist,
            target_user=getattr(stylist, "user", None),
            delivery_status="sent",
            meta={
                **common_meta,
                "panel": "stylist",
                "detail_id": item.pk,
            },
        )


def _format_customer_datetime_fa(value):
    if not value:
        return ""

    try:
        local_value = timezone.localtime(value)
        return f"{format_jalali_with_weekday(local_value.date())} • ساعت {format_time_fa(local_value.time())}"
    except Exception:
        return ""


def _appointment_ics_text_max_chars():
    return max(
        int(getattr(settings, "APPOINTMENT_ICS_TEXT_MAX_CHARS", 300) or 1),
        1,
    )


def _clean_ics_text(raw_value, *, default="", max_chars=None):
    text = str(raw_value or default or "")

    # جلوگیری از CRLF injection و null byte
    text = text.replace("\r", " ").replace("\n", " ").replace("\x00", " ")

    # نرمال‌سازی فاصله‌ها
    text = " ".join(text.split()).strip()

    limit = max_chars or _appointment_ics_text_max_chars()
    if len(text) > limit:
        text = text[:limit].rstrip()

    return text


def _escape_ics_text(raw_value, *, default="", max_chars=None):
    text = _clean_ics_text(raw_value, default=default, max_chars=max_chars)

    # RFC5545 TEXT escaping
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")


def _clean_ics_token(raw_value, *, default="loomera.local", max_chars=120):
    text = _clean_ics_text(raw_value, default=default, max_chars=max_chars)
    safe = "".join(
        char
        for char in text
        if char.isalnum() or char in {".", "-", "_", "@", "/", ":"}
    )
    return safe or default


def _ics_line(name, value):
    return f"{name}:{value}\r\n"


def _appointment_review_post_max_bytes():
    return max(
        int(getattr(settings, "APPOINTMENT_REVIEW_POST_MAX_BYTES", 8 * 1024) or 1),
        1,
    )


def _appointment_review_comment_max_chars():
    return max(
        int(getattr(settings, "APPOINTMENT_REVIEW_COMMENT_MAX_CHARS", 1000) or 1),
        1,
    )


def _request_body_too_large(request, max_bytes):
    try:
        content_length = int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        content_length = 0

    return content_length > max_bytes


PAY_IN_SALON_SETTLEMENT_ACTIONS = {"cash", "online"}


def _pay_in_salon_settlement_post_max_bytes():
    return max(
        int(getattr(settings, "PAY_IN_SALON_SETTLEMENT_POST_MAX_BYTES", 2 * 1024) or 1),
        1,
    )


def _clean_pay_in_salon_settlement_action(request):
    if _request_body_too_large(
        request,
        _pay_in_salon_settlement_post_max_bytes(),
    ):
        raise ValidationError("حجم اطلاعات ارسالی بیش از حد مجاز است.")

    action = (request.POST.get("payment_action") or "").strip().lower()
    if action not in PAY_IN_SALON_SETTLEMENT_ACTIONS:
        raise ValidationError("نوع پرداخت انتخاب‌شده معتبر نیست.")

    return action


def _order_ready_for_pay_in_salon_settlement(order):
    return bool(order.service_completed_at or order.status == "completed")


def _order_has_valid_pay_in_salon_method(order):
    selected_method = (getattr(order, "selected_payment_method", "") or "").strip()
    if not selected_method:
        return True

    return selected_method == AppointmentCheckoutForm.PAYMENT_METHOD_SALON


def _has_pending_pay_in_salon_online_payment(order, Payment):
    return order.payment_order.filter(
        purpose=Payment.Purpose.APPOINTMENT,
        state__in=[Payment.State.INITIATED, Payment.State.PENDING],
        meta__source="pay_in_salon_online",
    ).exists()


def _clean_appointment_review_comment(raw_comment):
    comment = (raw_comment or "").strip()
    max_chars = _appointment_review_comment_max_chars()

    if len(comment) > max_chars:
        raise ValidationError("متن دیدگاه بیش از حد مجاز است.")

    return comment


# ------------------------------------------------------------------
# class OrderCartView(View):
#     def get(self, request, *args, **kw):
#         order_cart = OrderCart(request)

#         context = {
#             "order_cart": order_cart,
#         }
#         return render(request, "orders/order_cart.html", context)


# # ---------------------------------------------------------------------
# def show_order_cart(request):
#     order_cart = OrderCart(request)
#     for item in order_cart:
#         item["discount"] = item["stylist"].get_discount_for_service(item["service"])
#     context = {"order_cart": order_cart}
#     return render(request, "orders/partials/show_order_cart.html", context)


# # ---------------------------------------------------------------------------
# import json
import logging

# from django.http import JsonResponse
# from django.shortcuts import get_object_or_404
# from django.views.decorators.http import require_POST
# from django.contrib.auth.decorators import login_required

# # مدل‌های خود را اینجا import کنید
# # from apps.salons.models import Salon
# # from apps.accounts.models import Stylist
# # from apps.services.models import Services
# # from .order_cart import OrderCart # کلاس سبد خرید شما

# @login_required  # افزودن به سبد خرید نیازمند لاگین کاربر است
# @require_POST    # این View فقط درخواست‌های POST را می‌پذیرد
# def add_to_order_cart(request):
#     """
#     یک آیتم (خدمت، متخصص، تاریخ و زمان) را به سبد خرید کاربر اضافه می‌کند.
#     """
#     # ۱. خواندن اطلاعات از بدنه درخواست POST (که به صورت JSON ارسال شده)
#     try:
#         data = json.loads(request.body)
#         service_id = data.get("service")
#         stylist_id = data.get("stylist")
#         salon_id = data.get("salon")
#         date = data.get("date")
#         time = data.get("time")

#         if not all([service_id, stylist_id, salon_id, date, time]):
#             return JsonResponse({"error": "اطلاعات ارسالی ناقص است."}, status=400)

#     except (json.JSONDecodeError, TypeError):
#         return JsonResponse({"error": "فرمت درخواست نامعتبر است (باید JSON باشد)."}, status=400)

#     # ۲. اعتبارسنجی و واکشی بهینه آبجکت‌ها
#     try:
#         # ✅ بهینه‌سازی اصلی: واکشی متخصص و بررسی همزمان روابط او با مجموعه و خدمت
#         # این کوئری تضمین می‌کند که متخصص انتخاب شده، خدمت مورد نظر را در مجموعه مشخص شده ارائه می‌دهد.
#         stylist = get_object_or_404(
#             Stylist.objects.select_related('user'),
#             user_id=int(stylist_id),
#             stylists_of_salon__pk=int(salon_id), # آیا این متخصص در این مجموعه کار می‌کند؟
#             services_of_stylist__pk=int(service_id)  # آیا این متخصص این خدمت را ارائه می‌دهد؟
#         )

#         # حالا که روابط تایید شده، می‌توانیم بقیه آبجکت‌ها را با خیال راحت واکشی کنیم
#         service = get_object_or_404(Services, pk=int(service_id))
#         salon = get_object_or_404(Salon, pk=int(salon_id))

#     except (ValueError, TypeError):
#          return JsonResponse({"error": "شناسه‌های ارسال شده نامعتبر هستند."}, status=400)
#     except Stylist.DoesNotExist:
#         return JsonResponse({"error": "متخصص انتخاب شده این خدمت را در این مجموعه ارائه نمی‌دهد یا معتبر نیست."}, status=404)
#     except (Services.DoesNotExist, Salon.DoesNotExist):
#         return JsonResponse({"error": "خدمت یا مجموعه مورد نظر یافت نشد."}, status=404)

#     # ۳. افزودن به سبد خرید
#     try:
#         order_cart = OrderCart(request)
#         order_cart.add_to_order_cart(service, stylist, salon, date, time)
#         return JsonResponse({"message": "رزرو با موفقیت به سبد شما اضافه شد."}, status=200)

#     except Exception as e:
#         # می‌توانید خطاهای خاصی که ممکن است از کلاس سبد خرید شما بیاید را اینجا مدیریت کنید
#         print(f"خطا در افزودن به سبد خرید: {e}")
#         return JsonResponse({"error": "خطایی در پردازش سبد خرید رخ داد."}, status=500)


# # --------------------------------------------------------------------------------------------------------------------
# def delete_from_order_cart(request):
#     service_id = request.GET.get("service")
#     service = get_object_or_404(Services, id=service_id)
#     order_cart = OrderCart(request)
#     order_cart.delete_from_order_cart(service)
#     return redirect("orders:show_order_cart")


# # --------------------------------------------------------------------------------------------------------------------
# def show_update_order_cart(request):
#     """
#     سبد خرید را با اطلاعات کامل و به صورت بهینه برای نمایش در تمپلیت آماده می‌کند.
#     """
#     order_cart = request.session.get("order_cart", {})

#     # ۱. تمام ID های خدمات را از سبد خرید جمع‌آوری می‌کنیم
#     service_ids = [item.get("service_id") for item in order_cart.values() if item.get("service_id")]

#     if not service_ids:
#         return render(request, "orders/partials/show_update_order_cart.html", {"updated_items": []})

#     # ۲. ✅ بهینه‌سازی اصلی: تمام خدمات و روابط مورد نیاز را در چند کوئری محدود واکشی می‌کنیم
#     services_qs = Services.objects.filter(id__in=service_ids).prefetch_related(
#         'stylists__user',  # واکشی متخصصان و کاربران مرتبط با آنها
#         'services_of_salon' # واکشی مجموعه‌های مرتبط
#     )

#     # ۳. یک دیکشنری برای دسترسی سریع به آبجکت‌های خدمت می‌سازیم
#     services_map = {service.id: service for service in services_qs}

#     # ۴. ساختار نهایی را با استفاده از داده‌های از پیش واکشی شده، آماده می‌کنیم
#     updated_items = []
#     for item_key, item_data in order_cart.items():
#         service_id = item_data.get("service_id")
#         service = services_map.get(service_id)

#         if service:
#             updated_items.append({
#                 "key": item_key, # کلید منحصر به فرد هر آیتم در سبد خرید
#                 "service": service,
#                 "stylists": service.stylists.all(),
#                 "salons": service.services_of_salon.all(),
#                 "date": item_data.get("date"),
#                 "time": item_data.get("time"),
#                 "price": item_data.get("price"),
#                 "selected_stylist_id": item_data.get("stylist_id"),
#                 "selected_salon_id": item_data.get("salon_id"),
#             })

#     return render(
#         request,
#         "orders/partials/show_update_order_cart.html",
#         {"updated_items": updated_items},
#     )


# # ---------------------------------------------------------------------------------------------------------------------
# def show_update_salon_stylist_order(request):
#     return redirect("orders:show_update_order_cart")


# # --------------------------------------------------------------------------------------------------------------------
# def update_salon_stylist_order(request):
#     service_id_list = request.GET.getlist("service_id_list[]")
#     stylist_id_list = request.GET.getlist("stylist_id_list[]")
#     salon_id_list = request.GET.getlist("salon_id_list[]")
#     order_cart = OrderCart(request)
#     order_cart.update(service_id_list, stylist_id_list, salon_id_list, None, None)
#     return redirect("orders:show_update_callendar")


# # -----------------------------------------------------------------------------------------------------------------------
# def show_update_callendar(request):
#     order_cart = OrderCart(request)

#     return render(
#         request,
#         "orders/partials/show_update_callendar.html",
#         {"order_cart": order_cart},
#     )


# # ------------------------------------------------------------------------------------------------------------------------
# def update_callendar(request):
#     service_id_list = request.GET.getlist("service_id_list[]")
#     date_value_list = request.GET.getlist("date_value_list[]")
#     time_value_list = request.GET.getlist("time_value_list[]")
#     print(date_value_list)
#     print(100 * "-")
#     print(time_value_list)
#     order_cart = OrderCart(request)
#     order_cart.update(service_id_list, None, None, date_value_list, time_value_list)
#     return redirect("orders:show_order_cart")


# --------------------------------------------------------------------------------------------------------------------
# def status_of_order_cart(request):
#     order_cart = OrderCart(request)
#     return HttpResponse(order_cart.count)


# --------------------------------------------------------------------------------------------------------------------
# class CreateOrderView(LoginRequiredMixin, View):

#     def get(self, request):

#         user = request.user
#         customer = Customer.objects.get(user=user)
#         order = Order.objects.create(customer=customer)
#         try:
#             stylist = Stylist.objects.get(user=user)
#             # user_role = "stylist"
#         except Stylist.DoesNotExist:
#             stylist = None

#         try:
#             salon_manager = SalonManager.objects.get(user=user)
#             # user_role = "salon_manager"
#         except SalonManager.DoesNotExist:
#             salon_manager = None

#         if not stylist and not salon_manager:
#             # user_role = "customer"

#             customer = Customer.objects.get(user=user)

#             order = Order.objects.create(customer=customer)
#             order_cart = OrderCart(request)
#             for item in order_cart:
#                 service = get_object_or_404(Services, id=item["service_id"])
#                 stylist = get_object_or_404(Stylist, user_id=item["stylist_id"])
#                 salon = get_object_or_404(Salon, id=item["salon_id"])
#                 OrderDetail.objects.create(
#                     order=order,
#                     service=service,
#                     stylist=stylist,
#                     salon=salon,
#                     date=item["date"],
#                     time=item["time"],
#                     price=item["final_price"],
#                 )
#         elif stylist or salon_manager:
#             messages.warniمتخصصان
#                 request, "متخصصان و مدیران سایت قادر به رزرو وقت نیستند ", "warning"
#             )
#         return redirect("orders:check_out", order.id)  # type: ignore

# --------------------------------------------------------------------------------------------------------------------
# class CheckOutOrderView(LoginRequiredMixin, View):
#     def get(self, request, order_id):
#         order = get_object_or_404(Order, id=order_id, customer__user=request.user)
#         order_cart = OrderCart(request)
#         total_price = order_cart.calc_total_price()
#         tax = total_price * 0.09
#         order_final_price = total_price + tax

#         if order.discount:
#             order_final_price *= 1 - order.discount / 100

#         context = {
#             "order_cart": order_cart,
#             "total_price": total_price,
#             "tax": tax,
#             "order_final_price": order_final_price,
#             "form": OrderForm(),
#             "form_coupon": CouponForm(),
#             "order": order,
#         }
#         return render(request, "orders/check_out.html", context)

#     def post(self, request, order_id):
#         form = OrderForm(request.POST)
#         if not form.is_valid():
#             messages.error(request, "اطلاعات وارد شده نامعتبر است.")
#             return redirect("orders:check_out", order_id)

#         try:
#             payment_type = PaymentType.objects.get(id=form.cleaned_data["payment_type"])
#             order = get_object_or_404(Order, id=order_id, customer__user=request.user)
#             order.payment_type = payment_type
#             order.save()

#             messages.success(request, "اطلاعات شما با موفقیت به‌روزرسانی شد")
#             return redirect("payments:zarinpal", order_id)

#         except PaymentType.DoesNotExist:
#             messages.error(request, "نوع پرداخت یافت نشد.", "danger")
#             return redirect("orders:check_out", order_id)

# --------------------------------------------------------------------------------------------------------------------
# class ApplyCoupon(View):
#     def post(self, request, *args, **kwargs):
#         form = CouponForm(request.POST)
#         order_id = kwargs["order_id"]
#         if form.is_valid():
#             cd = form.cleaned_data
#             coupon_code = cd["coupon_code"]

#             coupon = Coupon.objects.filter(
#                 Q(coupon_code=coupon_code)
#                 & Q(is_active=True)
#                 & Q(start_date__lt=datetime.now())
#                 & Q(end_date__gt=datetime.now())
#             )
#             discount = 0
#             try:
#                 order = Order.objects.get(id=order_id)
#                 if coupon:
#                     discount = coupon[0].discount
#                     order.discount = discount
#                     order.save()
#                     messages.success(request, "اعمال کوپن با موفقیت انجام شد")
#                     return redirect("orders:check_out", order_id)
#                 else:
#                     order.discount = discount
#                     order.save()
#                     messages.error(request, "کد وارد شده معتبر نیست", "danger")

#             except ObjectDoesNotExist:
#                 messages.error(request, "سفارش موجود نیست")
#             return redirect("orders:check_out", order_id)


# ---------------------------------------------------------------------------------------------------------------
import json
import logging
from datetime import date, datetime
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Prefetch, Avg, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_GET
from khayyam import JalaliDate
from apps.accounts.models import Customer, Stylist
from apps.salons.models import Salon
from apps.services.models import ServicePrice, Services
from apps.stylists.models import StylistSchedule
from .forms import OrderForm, AppointmentCheckoutForm
from .models import Order, OrderDetail
from .lifecycle import (
    cancel_order_reminder,
    build_customer_progress_context,
    get_customer_notifications,
    mark_review_requested,
    notify_manager_and_stylists_for_booking,
    notify_operational_milestone,
    schedule_order_reminder,
)
from collections import defaultdict
from django.db import transaction


class BookingStylistSelectPerService(View):
    """
    صفحه انتخاب متخصص برای هر خدمت
    با فیلتر availability واقعی در روزهای آتی
    """

    template_name = "orders/select_stylists.html"
    availability_horizon_days = 30

    def _format_next_available_label(self, first_slot):
        if not first_slot:
            return "فعلاً زمان آزادی پیدا نشد"
        date_label = JalaliDate(first_slot["date"]).strftime("%Y/%m/%d")
        time_label = (
            first_slot["time"].strftime("%H:%M")
            if hasattr(first_slot["time"], "strftime")
            else str(first_slot["time"])
        )
        return f"نخستین زمان آزاد: {date_label} • {time_label}"

    def get(self, request):
        salon_id = request.GET.get("salon_id") or request.session.get("salon_id")
        selected_services = request.GET.get(
            "selected_services",
            "",
        )

        service_ids = _quick_booking_parse_service_ids(
            [item for item in selected_services.split(",") if item]
        )

        if service_ids is None:
            _clear_public_booking_session_state(request)
            messages.error(
                request,
                "خدمات انتخاب‌شده معتبر نیستند.",
            )
            return redirect("salons:show_salons")

        if not service_ids:
            service_ids = _booking_selected_service_ids_from_session(request)

        salon = _public_booking_salon_or_none(salon_id)

        if salon is None or not service_ids:
            _clear_public_booking_session_state(request)
            messages.error(
                request,
                "اطلاعات سالن و خدمات برای رزرو کامل نیست.",
            )
            return redirect("salons:show_salons")

        services_qs = (
            _public_booking_service_queryset(salon)
            .filter(id__in=service_ids)
            .prefetch_related(
                "service_prices",
                "stylists__user",
            )
        )

        services_map = {service.id: service for service in services_qs}

        if set(services_map) != set(service_ids):
            _clear_public_booking_session_state(request)
            messages.error(
                request,
                "یک یا چند خدمت انتخاب‌شده معتبر نیست.",
            )
            return redirect("salons:show_salons")

        service_cards = []

        for service_id in service_ids:
            service = services_map[service_id]

            available_stylists = [
                item
                for item in (
                    get_upcoming_available_stylists_for_service(
                        salon=salon,
                        service=service,
                        start_date=timezone.localdate(),
                        horizon_days=(self.availability_horizon_days),
                    )
                )
                if (
                    item["stylist"].public_visibility
                    in PUBLIC_BOOKING_STYLIST_VISIBILITIES
                )
            ]

            best_available = available_stylists[0] if available_stylists else None

            service_prices = [
                int(price.price)
                for price in service.service_prices.all()
                if price.price is not None
            ]

            service.min_price = (
                min(service_prices)
                if service_prices
                else int(
                    getattr(
                        service,
                        "base_price",
                        0,
                    )
                    or 0
                )
            )

            stylist_cards = []

            for item in available_stylists:
                stylist = item["stylist"]
                first_slot = item["first_slot"]

                stylist_cards.append(
                    {
                        "stylist": stylist,
                        "price": int(item["price"] or 0),
                        "first_slot": first_slot,
                        "availability_label": (
                            self._format_next_available_label(first_slot)
                        ),
                    }
                )

            service_cards.append(
                {
                    "service": service,
                    "stylists": stylist_cards,
                    "has_available_stylists": bool(stylist_cards),
                    "any_option": {
                        "enabled": bool(best_available),
                        "price": (
                            int(best_available["price"] or service.min_price or 0)
                            if best_available
                            else int(service.min_price or 0)
                        ),
                        "availability_label": (
                            self._format_next_available_label(
                                best_available["first_slot"]
                            )
                            if best_available
                            else ("فعلاً برای این خدمت متخصص " "آزادی پیدا نشد")
                        ),
                    },
                }
            )

        context = {
            "hide_navbar": True,
            "salon_id": str(salon.pk),
            "salon": salon,
            "service_cards": service_cards,
        }

        return render(
            request,
            self.template_name,
            context,
        )

    def post(self, request):
        """
        Persist the first validated public-booking session stage.

        The posted JSON is untrusted. The active salon and the complete service/stylist
        selection set are validated before storage. Any parse or domain validation
        failure clears all public-booking session state. On success, ``salon_id`` and
        ``stylist_selections`` are stored and any previous ``datetime_selections`` are
        invalidated.
        """
        salon_id = request.POST.get("salon_id")
        stylist_selections_json = request.POST.get("stylist_selections")

        try:
            stylist_selections = json.loads(stylist_selections_json)
            record_booking_quick_link_started(request=request)

            salon = _public_booking_salon_or_none(salon_id)

            if salon is None:
                raise ValidationError("مجموعه انتخاب‌شده معتبر نیست.")

            _validate_public_booking_stylist_selections(
                salon=salon,
                stylist_selections=stylist_selections,
            )

        except (
            json.JSONDecodeError,
            TypeError,
            ValidationError,
        ) as exc:
            _clear_public_booking_session_state(request)

            messages.error(
                request,
                (str(exc) or "خطا در پردازش اطلاعات."),
            )

            return redirect("orders:select_stylists")

        request.session["salon_id"] = str(salon.pk)
        request.session["stylist_selections"] = stylist_selections
        request.session.pop(
            "datetime_selections",
            None,
        )
        request.session.modified = True

        return redirect("orders:select_dateTime")


class BookingDateTimeSelectPersian(View):
    """
    صفحه انتخاب تاریخ و زمان با تقویم شمسی
    برای هر متخصص به صورت جداگانه
    """

    template_name = "orders/select_datetime.html"

    def get(self, request):
        salon_id = request.session.get("salon_id")
        stylist_selections = request.session.get(
            "stylist_selections",
            [],
        )
        salon = _public_booking_salon_or_none(salon_id)

        try:
            if salon is None:
                raise ValidationError("مجموعه انتخاب‌شده معتبر نیست.")

            _, services_map = _validate_public_booking_stylist_selections(
                salon=salon,
                stylist_selections=(stylist_selections),
            )

        except ValidationError as exc:
            _clear_public_booking_session_state(request)
            messages.error(request, str(exc))
            return redirect("salons:show_salons")

        enriched = []

        for raw_sel in stylist_selections:
            sel = dict(raw_sel)

            sel.setdefault(
                "requestedStylistId",
                sel.get("stylistId"),
            )
            sel.setdefault(
                "requestedStylistName",
                sel.get("stylistName"),
            )

            service_id = _parse_positive_int_param(sel.get("serviceId"))
            service = services_map[service_id]

            sel["serviceDuration"] = service.duration_minutes or 30
            sel["serviceBuffer"] = (
                getattr(
                    service,
                    "buffer_minutes",
                    0,
                )
                or 0
            )
            sel["serviceName"] = service.service_name

            enriched.append(sel)

        context = {
            "hide_navbar": True,
            "salon_id": str(salon.pk),
            "stylist_selections_json": json.dumps(
                enriched,
                ensure_ascii=False,
            ),
            "checkout_slot_lost_notice": (_pop_checkout_slot_lost_notice(request)),
        }

        return render(
            request,
            self.template_name,
            context,
        )

    def post(self, request):
        """
        Persist the second validated public-booking session stage.

        The posted JSON is untrusted. Salon, service/stylist selections, and the exact
        datetime mapping are revalidated together. Tampered, extra, malformed, or past
        selections clear all public-booking session state. Success stores all three
        booking session keys and redirects to preview; it does not create an Order and
        does not reserve a slot.
        """
        try:
            booking_data_json = request.POST.get("booking_data")

            if not booking_data_json:
                raise ValidationError("اطلاعات رزرو دریافت نشد.")

            booking_data = json.loads(booking_data_json)

            if not isinstance(booking_data, dict):
                raise ValidationError("اطلاعات رزرو معتبر نیست.")

            salon = _public_booking_salon_or_none(booking_data.get("salon_id"))

            if salon is None:
                raise ValidationError("مجموعه انتخاب‌شده معتبر نیست.")

            stylist_selections = booking_data.get(
                "stylist_selections",
                [],
            )
            datetime_selections = booking_data.get(
                "datetime_selections",
                {},
            )
            record_booking_quick_link_started(request=request)

            _validate_public_booking_datetime_selections(
                salon=salon,
                stylist_selections=(stylist_selections),
                datetime_selections=(datetime_selections),
            )

        except (
            json.JSONDecodeError,
            TypeError,
            ValidationError,
        ) as exc:
            _clear_public_booking_session_state(request)

            logger.warning(
                "Invalid booking selection rejected " "in select datetime flow"
            )

            messages.error(
                request,
                (str(exc) or "خطا در پردازش اطلاعات."),
            )

            return redirect("orders:select_dateTime")

        request.session["salon_id"] = str(salon.pk)
        request.session["stylist_selections"] = stylist_selections
        request.session["datetime_selections"] = datetime_selections
        request.session.modified = True

        return redirect("orders:reservation_preview")


class StylistAvailabilityAPI(View):
    """API ماهانه availability برای تقویم انتخاب زمان رزرو."""

    def get(self, request):
        salon_id = request.GET.get("salon_id")
        month = request.GET.get("month")
        year = request.GET.get("year")

        if not all([salon_id, month, year]):
            return _json_error("پارامترهای الزامی ارسال نشده است", status=400)

        salon, error_response = _public_booking_salon_or_response(salon_id)
        if error_response is not None:
            return error_response

        month_jalali, year_jalali = _validate_jalali_month_year(month, year)
        if month_jalali is None or year_jalali is None:
            return _json_error("پارامترهای تقویم معتبر نیست", status=400)

        try:
            from khayyam import JalaliDate as KhayyamJalaliDate

            start_jalali = KhayyamJalaliDate(year_jalali, month_jalali, 1)
            end_jalali = KhayyamJalaliDate(
                year_jalali,
                month_jalali,
                start_jalali.daysinmonth,
            )
            start_date = start_jalali.todate()
            end_date = end_jalali.todate()
        except ValueError:
            return _json_error("پارامترهای تقویم معتبر نیست", status=400)

        schedules = list(
            StylistSchedule.objects.filter(
                salon=salon,
                date__range=[start_date, end_date],
                stylist__is_active=True,
                stylist__public_visibility__in=PUBLIC_BOOKING_STYLIST_VISIBILITIES,
            )
            .filter(
                Q(service__isnull=True)
                | (
                    Q(
                        service__is_active=True,
                        service__services_of_salon=salon,
                    )
                    & (
                        Q(service__is_platform_catalog=True)
                        | Q(service__catalog_source__isnull=False)
                    )
                )
            )
            .select_related("stylist", "service")
            .order_by("date", "start_time")
        )

        # Keep this payload in lock-step with the final slot validator.
        # Any finalized/paid booking occupies the stylist's time regardless of
        # whether that historical service is still active/public/catalog-backed.
        booked_items = (
            get_blocking_order_details_queryset(
                salon=salon,
                start_date=start_date,
                end_date=end_date,
            )
            .filter(stylist__isnull=False)
            .select_related("stylist", "service")
            .order_by("date", "time")
        )

        approved_leave_requests = (
            StaffLeaveRequest.objects.filter(
                salon=salon,
                status=StaffLeaveRequest.Status.APPROVED,
                date__range=[start_date, end_date],
                stylist__is_active=True,
                stylist__public_visibility__in=PUBLIC_BOOKING_STYLIST_VISIBILITIES,
            )
            .select_related("stylist")
            .order_by("date", "start_time")
        )

        schedules_payload = defaultdict(lambda: defaultdict(list))
        booked_payload = defaultdict(lambda: defaultdict(list))
        time_off_payload = defaultdict(lambda: defaultdict(list))

        explicit_schedule_keys = set()
        for schedule in schedules:
            stylist_id = str(schedule.stylist.user_id)
            day_key = schedule.date.strftime("%Y-%m-%d")
            explicit_schedule_keys.add((schedule.stylist_id, schedule.date))
            schedules_payload[stylist_id][day_key].append(
                {
                    "start_time": (
                        schedule.start_time.strftime("%H:%M")
                        if schedule.start_time
                        else None
                    ),
                    "end_time": (
                        schedule.end_time.strftime("%H:%M")
                        if schedule.end_time
                        else None
                    ),
                    "service_id": schedule.service_id,
                }
            )

        for booking in booked_items:
            stylist_id = str(booking.stylist.user_id)
            day_key = booking.date.strftime("%Y-%m-%d")
            duration = 0
            if booking.time and booking.end_time:
                duration = int(
                    (
                        datetime.combine(booking.date, booking.end_time)
                        - datetime.combine(booking.date, booking.time)
                    ).total_seconds()
                    // 60
                )
            booking_end = booking.occupied_until or booking.end_time
            booked_payload[stylist_id][day_key].append(
                {
                    "time": booking.time.strftime("%H:%M") if booking.time else None,
                    "end_time": booking_end.strftime("%H:%M") if booking_end else None,
                    "service_end_time": (
                        booking.end_time.strftime("%H:%M") if booking.end_time else None
                    ),
                    "duration": duration,
                    "service_id": booking.service_id,
                }
            )

        for item in approved_leave_requests:
            stylist_id = str(item.stylist.user_id)
            day_key = item.date.strftime("%Y-%m-%d")
            time_off_payload[stylist_id][day_key].append(
                {
                    "start_time": (
                        item.start_time.strftime("%H:%M") if item.start_time else None
                    ),
                    "end_time": (
                        item.end_time.strftime("%H:%M") if item.end_time else None
                    ),
                    "reason": item.reason or "مرخصی تاییدشده",
                }
            )
        response = JsonResponse(
            {
                "schedules": schedules_payload,
                "booked_times": booked_payload,
                "time_offs": time_off_payload,
            },
            json_dumps_params={"ensure_ascii": False},
        )
        # Availability is volatile; a browser/proxy cache must not resurrect a
        # slot that has already been taken.
        response["Cache-Control"] = "no-store, private"
        return response


class StylistsForServiceAPI(View):
    """API برای دریافت متخصصان دارای availability واقعی برای یک خدمت."""

    availability_horizon_days = 30

    def get(self, request):
        salon_id = request.GET.get("salon_id")
        service_id = request.GET.get("service_id")

        if not all([salon_id, service_id]):
            return _json_error("پارامترهای الزامی ارسال نشده است", status=400)

        salon, error_response = _public_booking_salon_or_response(salon_id)
        if error_response is not None:
            return error_response

        service, error_response = _public_booking_service_or_response(salon, service_id)
        if error_response is not None:
            return error_response

        stylists = get_upcoming_available_stylists_for_service(
            salon=salon,
            service=service,
            start_date=timezone.localdate(),
            horizon_days=self.availability_horizon_days,
        )
        best = resolve_best_available_stylist_for_service(
            salon=salon,
            service=service,
            start_date=timezone.localdate(),
            horizon_days=self.availability_horizon_days,
        )

        eligible_stylist_ids = set(
            _public_booking_stylist_queryset(salon)
            .filter(services_of_stylist=service)
            .values_list("pk", flat=True)
        )

        stylists = [
            item
            for item in stylists
            if item.get("stylist") and item["stylist"].pk in eligible_stylist_ids
        ]

        if (
            best
            and best.get("stylist")
            and best["stylist"].pk not in eligible_stylist_ids
        ):
            best = None

        if best is None and stylists:
            best = stylists[0]

        result = []
        for item in stylists:
            stylist = item["stylist"]
            first_slot = item["first_slot"]
            result.append(
                {
                    "id": stylist.user.id,
                    "name": stylist.get_fullName(),
                    "profile_image": (
                        stylist.profile_image.url if stylist.profile_image else None
                    ),
                    "price": int(item["price"] or 0),
                    "next_date": first_slot["date"].strftime("%Y-%m-%d"),
                    "next_time": first_slot["time"].strftime("%H:%M"),
                    "next_end_time": first_slot["end_time"].strftime("%H:%M"),
                }
            )

        payload = {"stylists": result}
        if best:
            payload["best_available"] = {
                "id": best["stylist"].user.id,
                "name": best["stylist"].get_fullName(),
                "next_date": best["first_slot"]["date"].strftime("%Y-%m-%d"),
                "next_time": best["first_slot"]["time"].strftime("%H:%M"),
            }

        return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})


class BookingQuickLinkStylistServicesView(View):
    template_name = "orders/quick_link_stylist_services.html"

    def _get_context(self, salon, stylist, services, selected_service_ids=None):
        selected_service_ids = {int(item) for item in (selected_service_ids or [])}
        cards = []
        for service in services:
            price_obj = (
                service.service_prices.filter(stylist=stylist).order_by("price").first()
            )
            price_value = int(
                getattr(price_obj, "price", 0) or getattr(service, "base_price", 0) or 0
            )
            cards.append(
                {
                    "id": service.id,
                    "name": service.service_name,
                    "duration_label": f"{service.duration_minutes or 0} دقیقه",
                    "summary": service.summery_description
                    or "این خدمت توسط همین متخصص در این مجموعه ارائه می‌شود.",
                    "price_label": (
                        f"{price_value:,} تومان"
                        if price_value
                        else "قیمت در مرحله بعد نهایی می‌شود"
                    ),
                    "is_selected": service.id in selected_service_ids,
                }
            )
        return {
            "hide_navbar": True,
            "salon": salon,
            "stylist": stylist,
            "service_cards": cards,
        }

    def get(self, request):
        salon_id = request.GET.get("salon_id")
        stylist_user_id = request.GET.get("stylist_id")

        parsed_stylist_user_id = _parse_positive_int_param(stylist_user_id)
        if parsed_stylist_user_id is None:
            messages.error(request, "متخصص انتخاب‌شده معتبر نیست.")
            return redirect("salons:show_salons")

        salon, error_response = _public_booking_salon_or_response(salon_id)
        if error_response is not None:
            messages.error(
                request, "سالن مربوط به این لینک فعال نیست یا در دسترس نیست."
            )
            return redirect("salons:show_salons")

        stylist = get_object_or_404(
            _public_booking_stylist_queryset(salon).select_related("user"),
            user_id=parsed_stylist_user_id,
        )

        services = list(
            _public_booking_service_queryset(salon)
            .filter(stylists=stylist)
            .prefetch_related("service_prices")
            .order_by("service_name")
        )

        if not services:
            messages.error(request, "برای این متخصص در این مجموعه خدمت فعالی پیدا نشد.")
            return redirect("salons:detail_salon", pk=salon.id)

        return render(
            request,
            self.template_name,
            self._get_context(salon, stylist, services),
        )

    def post(self, request):
        salon_id = request.POST.get("salon_id")
        stylist_user_id = request.POST.get("stylist_id")

        parsed_stylist_user_id = _parse_positive_int_param(stylist_user_id)
        if parsed_stylist_user_id is None:
            messages.error(request, "متخصص انتخاب‌شده معتبر نیست.")
            return redirect("salons:show_salons")

        salon, error_response = _public_booking_salon_or_response(salon_id)
        if error_response is not None:
            messages.error(
                request, "سالن مربوط به این لینک فعال نیست یا در دسترس نیست."
            )
            return redirect("salons:show_salons")

        stylist = get_object_or_404(
            _public_booking_stylist_queryset(salon).select_related("user"),
            user_id=parsed_stylist_user_id,
        )

        services = list(
            _public_booking_service_queryset(salon)
            .filter(stylists=stylist)
            .prefetch_related("service_prices")
            .order_by("service_name")
        )

        available_service_ids = {service.id for service in services}
        selected_service_ids = _quick_booking_parse_service_ids(
            request.POST.getlist("selected_services")
        )

        if not selected_service_ids:
            messages.error(request, "حداقل یک خدمت را برای این متخصص انتخاب کنید.")
            return render(
                request,
                self.template_name,
                self._get_context(salon, stylist, services),
            )

        if selected_service_ids is None or not set(selected_service_ids).issubset(
            available_service_ids
        ):
            messages.error(request, "خدمت انتخاب‌شده برای این متخصص معتبر نیست.")
            return render(
                request,
                self.template_name,
                self._get_context(salon, stylist, services),
                status=400,
            )

        record_booking_quick_link_started(request=request)

        stylist_selections = []
        for service_id in selected_service_ids:
            stylist_selections.append(
                {
                    "serviceId": str(service_id),
                    "requestedStylistId": str(stylist.user_id),
                    "requestedStylistName": stylist.get_fullName(),
                    "stylistId": str(stylist.user_id),
                    "stylistName": stylist.get_fullName(),
                }
            )

        request.session["salon_id"] = str(salon.id)
        request.session["stylist_selections"] = stylist_selections
        request.session.pop("datetime_selections", None)
        request.session.modified = True

        return redirect("orders:select_dateTime")


class QuickBookingEntryView(View):

    def _redirect_with_error(self, request, message):
        return render(
            request,
            "orders/quick_link_invalid.html",
            {
                "message": message,
                "hide_navbar": False,
            },
            status=410,
        )

    def _get_active_salon(self, payload):
        return Salon.objects.filter(pk=payload["salon_id"], is_active=True).first()

    def _get_active_stylist(self, salon, stylist_user_id):
        parsed_stylist_user_id = _parse_positive_int_param(stylist_user_id)
        if parsed_stylist_user_id is None:
            return None

        return (
            _public_booking_stylist_queryset(salon)
            .select_related("user")
            .filter(user_id=parsed_stylist_user_id)
            .first()
        )

    def _get_active_services(self, salon, service_ids):
        parsed_service_ids = _quick_booking_parse_service_ids(service_ids)
        if not parsed_service_ids:
            return []

        services = list(
            _public_booking_service_queryset(salon)
            .filter(id__in=parsed_service_ids)
            .prefetch_related("service_prices", "stylists")
            .distinct()
        )
        found_ids = {service.id for service in services}

        if not set(parsed_service_ids).issubset(found_ids):
            return []

        services_by_id = {service.id: service for service in services}
        return [services_by_id[service_id] for service_id in parsed_service_ids]

    def get(self, request, token):
        try:
            quick_link, payload = resolve_booking_quick_link_token(token)

            if quick_link:
                record_booking_quick_link_opened(
                    request=request,
                    quick_link=quick_link,
                )
        except ValidationError as exc:
            return self._redirect_with_error(request, str(exc))

        if quick_link:
            request.session["booking_quick_link_id"] = quick_link.id
            request.session.modified = True

        salon = self._get_active_salon(payload)
        if not salon:
            return self._redirect_with_error(
                request,
                "سالن مربوط به این لینک رزرو سریع فعال نیست یا دیگر در دسترس نیست.",
            )

        mode = payload.get("mode")
        service_ids = payload.get("service_ids") or []
        stylist_user_id = payload.get("stylist_user_id")

        services = self._get_active_services(salon, service_ids)
        stylist = self._get_active_stylist(salon, stylist_user_id)

        if mode == "salon":
            return redirect(
                salon.get_absolute_url()
            )

        if mode == "service":
            if not services:
                return self._redirect_with_error(
                    request,
                    "خدمت مربوط به این لینک رزرو سریع فعال نیست یا از سالن حذف شده است.",
                )

        elif mode == "stylist":
            if not stylist:
                return self._redirect_with_error(
                    request,
                    "متخصص مربوط به این لینک رزرو سریع فعال نیست یا دیگر در این سالن فعالیت ندارد.",
                )

        elif mode in {"service_stylist", "service_stylist_time"}:
            if not services or not stylist:
                return self._redirect_with_error(
                    request,
                    "اطلاعات این لینک رزرو سریع کامل نیست.",
                )

            invalid_service = next(
                (
                    service
                    for service in services
                    if not service.stylists.filter(pk=stylist.pk).exists()
                ),
                None,
            )
            if invalid_service:
                return self._redirect_with_error(
                    request,
                    "خدمت انتخاب‌شده دیگر توسط این متخصص ارائه نمی‌شود.",
                )

            if (
                mode == "service_stylist_time"
                and not _quick_booking_time_payload_is_valid(payload)
            ):
                return self._redirect_with_error(
                    request,
                    "زمان ثبت‌شده در این لینک رزرو سریع معتبر نیست.",
                )

        else:
            return self._redirect_with_error(request, "این لینک رزرو سریع معتبر نیست.")

        if mode == "service":
            selected_services = ",".join(str(item) for item in service_ids)
            return redirect(
                f"{reverse('orders:select_stylists')}?salon_id={salon.id}&selected_services={selected_services}"
            )

        if mode == "stylist":
            return redirect(
                f"{reverse('orders:quick_link_stylist_services')}?salon_id={salon.id}&stylist_id={stylist.user_id}"
            )

        if mode in {"service_stylist", "service_stylist_time"}:
            if not services or not stylist:
                return self._redirect_with_error(
                    request,
                    "اطلاعات این لینک رزرو سریع کامل نیست.",
                )

            primary_service_id = int(service_ids[0])

            request.session["salon_id"] = str(salon.id)
            request.session["stylist_selections"] = [
                {
                    "serviceId": str(primary_service_id),
                    "requestedStylistId": str(stylist.user_id),
                    "requestedStylistName": stylist.get_fullName(),
                    "stylistId": str(stylist.user_id),
                    "stylistName": stylist.get_fullName(),
                }
            ]

            if mode == "service_stylist_time":
                selection_key = f"{stylist.user_id}_{primary_service_id}"
                request.session["datetime_selections"] = {
                    selection_key: {
                        "date": payload["date"],
                        "time": payload["time"],
                        "stylist_id": str(stylist.user_id),
                        "stylist_name": stylist.get_fullName(),
                    }
                }
                request.session.modified = True
                return redirect("orders:reservation_preview")

            request.session.pop("datetime_selections", None)
            request.session.modified = True
            return redirect("orders:select_dateTime")

        return self._redirect_with_error(request, "این لینک رزرو سریع معتبر نیست.")


# -----------------------------------------------------------------------------------------------------------------------
class ReservationPreview(LoginRequiredMixin, View):
    """
    پیش‌نمایش رزرو قبل از تایید نهایی
    با sequence واقعی برای رزرو چند خدمتی
    """

    template_name = "orders/reservation_preview.html"

    def get(self, request):
        salon_id = request.session.get("salon_id")
        stylist_selections = request.session.get("stylist_selections", [])
        datetime_selections = request.session.get("datetime_selections", {})

        if not all([salon_id, stylist_selections, datetime_selections]):
            messages.error(request, "اطلاعات رزرو ناقص است.")
            return redirect("salons:show_salons")

        salon = get_object_or_404(Salon, pk=salon_id)

        try:
            resolved_items = resolve_booking_sequence(
                salon=salon,
                stylist_selections=stylist_selections,
                datetime_selections=datetime_selections,
            )
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("orders:select_dateTime")

        service_details = []
        total_price = 0
        overall_start = None
        overall_end = None

        normalized_selections = []
        normalized_datetimes = {}
        for item in resolved_items:
            total_price += item.price
            formatted_date = JalaliDate(item.date_value).strftime("%Y/%m/%d")
            if overall_start is None or item.start_datetime < overall_start:
                overall_start = item.start_datetime
            if overall_end is None or item.end_datetime > overall_end:
                overall_end = item.end_datetime

            service_details.append(
                {
                    "sequence": item.index + 1,
                    "service": item.service,
                    "stylist": item.stylist,
                    "price": item.price,
                    "date": formatted_date,
                    "time": item.start_time.strftime("%H:%M"),
                    "end_time": item.end_time.strftime("%H:%M"),
                    "duration": item.duration_minutes,
                    "auto_resolved": item.auto_resolved,
                }
            )

            normalized_selection = dict(stylist_selections[item.index])
            normalized_selection["requestedStylistId"] = item.requested_stylist_id
            normalized_selection["stylistId"] = str(item.stylist.user_id)
            normalized_selection["resolvedStylistId"] = str(item.stylist.user_id)
            normalized_selection["stylistName"] = item.stylist.get_fullName()
            normalized_selection["resolvedStylistName"] = item.stylist.get_fullName()
            normalized_selection["stylistProfileImage"] = (
                item.stylist.profile_image.url
                if getattr(item.stylist, "profile_image", None)
                else None
            )
            normalized_selection["resolvedStylistPrice"] = item.price
            normalized_selections.append(normalized_selection)
            normalized_datetimes[item.key] = {
                "date": item.date_value.strftime("%Y-%m-%d"),
                "time": item.start_time.strftime("%H:%M"),
                "end_time": item.end_time.strftime("%H:%M"),
                "stylist_id": str(item.stylist.user_id),
                "stylist_name": item.stylist.get_fullName(),
            }

        request.session["stylist_selections"] = normalized_selections
        request.session["datetime_selections"] = normalized_datetimes
        request.session.modified = True

        try:
            coupon_code = _clean_appointment_checkout_coupon_code(
                request.GET.get("coupon")
            )
        except ValidationError as exc:
            messages.error(request, str(exc))
            coupon_code = ""
        payload = _build_checkout_payload(request=request, coupon_code=coupon_code)
        form = AppointmentCheckoutForm(
            initial={
                "coupon_code": coupon_code,
                "payment_method": AppointmentCheckoutForm.PAYMENT_METHOD_ONLINE,
            },
            requires_online_payment=payload["requires_online_payment"],
        )
        context = {
            "hide_navbar": True,
            "checkout": payload,
            "form": form,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        salon_id = request.session.get("salon_id")
        stylist_selections = request.session.get("stylist_selections", [])
        datetime_selections = request.session.get("datetime_selections", {})

        if not all([salon_id, stylist_selections, datetime_selections]):
            messages.error(request, "اطلاعات رزرو ناقص است.")
            return redirect("salons:show_salons")

        try:
            salon = get_object_or_404(Salon, pk=salon_id)
            resolve_booking_sequence(
                salon=salon,
                stylist_selections=stylist_selections,
                datetime_selections=datetime_selections,
            )
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("orders:reservation_preview")

        record_booking_quick_link_started(request=request)

        return redirect("orders:checkout")


class ReservationDetailView(LoginRequiredMixin, View):
    template_name = "orders/reservation_preview.html"

    def get(self, request, *args, **kwargs):
        # --- ۱. خواندن و اعتبارسنجی داده‌ها از Session ---
        try:
            stylists_data = json.loads(request.session.get("stylists_data", "[]"))
            service_selections = json.loads(
                request.session.get("service_selections", "[]")
            )
            salon_id = request.session.get("salon_id")

            if not salon_id or not stylists_data or not service_selections:
                messages.error(
                    request, "اطلاعات رزرو شما ناقص است. لطفاً دوباره تلاش کنید."
                )
                return redirect("orders:select_dateTime")  # یا هر صفحه مناسب دیگر

        except (json.JSONDecodeError, TypeError):
            messages.error(request, "خطا در پردازش اطلاعات رزرو.")
            return redirect("orders:select_dateTime")

        # --- ۲. جمع‌آوری تمام ID های مورد نیاز ---
        stylist_ids = {
            item.get("stylist_id") for item in stylists_data if item.get("stylist_id")
        }
        service_ids = {
            item.get("service_id")
            for item in service_selections
            if item.get("service_id")
        }

        # --- ۳. واکشی بهینه تمام داده‌ها در چند کوئری اصلی ---
        # ✅ بهینه‌سازی: واکشی مجموعه به همراه آمار امتیازات در یک کوئری
        salon = get_object_or_404(
            Salon.objects.annotate(
                avg_score=Avg(
                    "scoring_salon__score",
                    filter=Q(scoring_salon__comment__is_active=True),
                ),
                reviews_count=Count(
                    "scoring_salon", filter=Q(scoring_salon__comment__is_active=True)
                ),
            ),
            pk=salon_id,
        )

        # ✅ بهینه‌سازی: واکشی تمام متخصصان و سرویس‌های مورد نیاز
        stylists_map = {
            s.pk: s
            for s in Stylist.objects.filter(pk__in=stylist_ids).select_related("user")
        }
        services_map = {s.pk: s for s in Services.objects.filter(pk__in=service_ids)}

        # ✅ بهینه‌سازی: واکشی تمام قیمت‌های مورد نیاز در یک کوئری
        prices_qs = ServicePrice.objects.filter(
            service_id__in=service_ids, stylist_id__in=stylist_ids
        )
        prices_map = {
            (sp.service.pk, sp.stylist.user, id): sp.price for sp in prices_qs
        }

        # --- ۴. پردازش داده‌ها در پایتون (بدون کوئری اضافه) ---
        stylists_info = []
        for data in stylists_data:
            stylist = stylists_map.get(int(data.get("stylist_id")))
            if stylist:
                stylists_info.append(
                    {
                        "stylist": stylist,
                        "selected_date": data.get("selected_date"),
                        "selected_time": data.get("selected_time"),
                    }
                )

        services_info = []
        total_price = 0
        for item in service_selections:
            service = services_map.get(int(item.get("service_id")))
            stylist = stylists_map.get(int(item.get("stylist_id")))
            if service and stylist:
                price = prices_map.get((service.id, stylist.user.id), 0)
                if price is None:
                    price = 0
                services_info.append(
                    {"service": service, "stylist": stylist, "price": price}
                )
                total_price += price

        tax = 0
        final_price = total_price

        context = {
            "stylists_info": stylists_info,
            "services_info": services_info,
            "salon": salon,
            "total_price": total_price,
            "tax": tax,
            "final_price": final_price,
        }
        return render(request, self.template_name, context)

    @transaction.atomic
    def post(self, request):

        salon_id = request.session.get("salon_id")
        stylist_selections = request.session.get("stylist_selections", [])
        datetime_selections = request.session.get("datetime_selections", {})

        if not all([salon_id, stylist_selections, datetime_selections]):
            messages.error(request, "اطلاعات رزرو ناقص است.")
            return redirect("salons:show_salons")

        customer = get_object_or_404(Customer, user=request.user)
        salon = get_object_or_404(Salon, pk=salon_id)

        order = Order.objects.create(customer=customer, is_finally=False)

        for selection in stylist_selections:

            service_id = int(selection["serviceId"])
            stylist_id = (
                None if selection["stylistId"] == "any" else int(selection["stylistId"])
            )

            service = get_object_or_404(Services, pk=service_id)
            duration = service.duration_minutes or 60

            key = f"{selection['stylistId']}_{service_id}"
            datetime_info = datetime_selections.get(key, {})

            selected_date = datetime_info.get("date")
            selected_time = datetime_info.get("time")

            if not selected_date or not selected_time:
                raise ValidationError("تاریخ یا زمان نامعتبر است")

            start_dt = datetime.strptime(
                f"{selected_date} {selected_time}", "%Y-%m-%d %H:%M"
            )
            end_dt = start_dt + timedelta(minutes=duration)

            start_time = start_dt.time()
            end_time = end_dt.time()

            # 🔥 بررسی overlap واقعی
            conflict = (
                OrderDetail.objects.select_for_update()
                .filter(
                    stylist_id=stylist_id,
                    date=selected_date,
                    time__lt=end_time,
                    end_time__gt=start_time,
                    order__status__in=BLOCKING_STATUSES,
                )
                .filter(Q(order__is_finally=True) | Q(order__is_paid=True))
                .exists()
            )

            if conflict:
                transaction.set_rollback(True)
                messages.error(
                    request,
                    "این زمان همین حالا توسط کاربر دیگری نهایی شده است. لطفاً یک زمان آزاد دیگر انتخاب کنید.",
                )
                return redirect("orders:reservation_preview")

            # محاسبه قیمت
            if stylist_id:
                stylist = get_object_or_404(Stylist, user_id=stylist_id)
                price = stylist.get_price_for_service(service)
            else:
                service_price = ServicePrice.objects.filter(service=service).first()
                price = (
                    service_price.price
                    if service_price
                    else int(getattr(service, "base_price", 0) or 0)
                )

            OrderDetail.objects.create(
                order=order,
                service=service,
                stylist_id=stylist_id,
                salon=salon,
                price=price,
                date=selected_date,
                time=start_time,
                end_time=end_time,
            )

        messages.success(request, "رزرو شما با موفقیت ثبت شد.")
        return redirect("orders:appointments")


# ---------------------------------------------------------------------------------------------------------
# views.py - نسخه نهایی Production-Ready

from django.views import View
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import DateField
from persiantools.jdatetime import JalaliDate
from datetime import date, datetime


from django.shortcuts import render, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin

# مطمئن شو این‌ها در فایل هست:
# from django.utils import timezone
# from django.db.models import Q
# from datetime import date, datetime
# from persiantools.jdatetime import JalaliDate


def _build_rebook_stylist_selections(order):
    items = sorted(
        order.order_details1.select_related("service", "stylist__user", "salon").all(),
        key=lambda item: (
            item.date or date.min,
            item.time or datetime.min.time(),
            item.pk,
        ),
    )
    if not items:
        raise ValidationError("برای این رزرو خدمتی یافت نشد.")

    selections = []
    for item in items:
        if not item.service_id or item.service is None:
            raise ValidationError("یکی از خدمات رزرو قبلی دیگر در دسترس نیست.")

        service = item.service
        requested_stylist_id = None
        requested_stylist_name = ""
        stylist_id = "any"
        stylist_name = "هر متخصص"
        stylist_profile_image = None

        stylist = item.stylist
        stylist_is_valid = bool(
            stylist
            and getattr(stylist, "is_active", False)
            and item.salon_id
            and stylist.services_of_stylist.filter(pk=service.pk).exists()
            and stylist.stylists_of_salon.filter(pk=item.salon_id).exists()
        )
        if stylist and getattr(stylist, "user_id", None):
            requested_stylist_id = str(stylist.user_id)
            requested_stylist_name = stylist.get_fullName()

        if stylist_is_valid and stylist and getattr(stylist, "user_id", None):
            stylist_id = str(stylist.user_id)
            stylist_name = stylist.get_fullName()
            try:
                stylist_profile_image = (
                    stylist.profile_image.url
                    if getattr(stylist, "profile_image", None)
                    else None
                )
            except Exception:
                stylist_profile_image = None

        selections.append(
            {
                "serviceId": service.id,
                "serviceName": service.service_name,
                "serviceDuration": getattr(service, "duration_minutes", 60) or 60,
                "serviceBuffer": getattr(service, "buffer_minutes", 0) or 0,
                "stylistId": stylist_id,
                "requestedStylistId": requested_stylist_id or stylist_id,
                "stylistName": stylist_name,
                "requestedStylistName": requested_stylist_name or stylist_name,
                "stylistProfileImage": stylist_profile_image,
            }
        )

    return items, selections


class RebookPastOrderView(LoginRequiredMixin, View):
    def get(self, request, order_id):
        order = get_object_or_404(
            Order.objects.prefetch_related(
                Prefetch(
                    "order_details1",
                    queryset=OrderDetail.objects.select_related(
                        "service",
                        "stylist__user",
                        "salon",
                    ),
                )
            ).select_related("salon"),
            pk=order_id,
            customer__user=request.user,
        )

        if not order.salon_id:
            messages.error(request, "اطلاعات این رزرو برای رزرو مجدد کامل نیست.")
            return redirect("orders:appointments")

        try:
            items, stylist_selections = _build_rebook_stylist_selections(order)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("orders:appointments")

        if not items:
            messages.error(request, "برای این رزرو امکان رزرو مجدد وجود ندارد.")
            return redirect("orders:appointments")

        request.session["salon_id"] = str(order.salon_id)
        request.session["stylist_selections"] = stylist_selections
        request.session.pop("datetime_selections", None)
        request.session.pop("service_selections", None)
        request.session.pop("stylists_data", None)
        request.session.pop("reschedule_order_id", None)
        request.session.pop("reschedule_base_appointment_id", None)
        request.session.modified = True

        fallback_used = any(
            selection.get("stylistId") == "any" for selection in stylist_selections
        )
        if fallback_used:
            messages.info(
                request,
                "برای برخی خدمات، متخصص قبلی در دسترس نبود و می‌توانید زمان جدید را با متخصص آزاد انتخاب کنید.",
            )
        else:
            messages.success(
                request, "اطلاعات رزرو قبلی بازیابی شد. حالا زمان جدید را انتخاب کنید."
            )

        return redirect("orders:select_dateTime")


def _order_detail_date_field_kind():
    """
    نوع فیلد تاریخ جزئیات سفارش را از metadata مدل تشخیص می‌دهد.

    True:
        فیلد date از نوع DateField است.

    False:
        فیلد وجود دارد اما DateField نیست.

    None:
        فیلد در metadata مدل وجود ندارد و مسیر fallback باید استفاده شود.
    """
    from django.core.exceptions import FieldDoesNotExist
    from django.db.models import DateField

    try:
        date_field = OrderDetail._meta.get_field("date")
    except FieldDoesNotExist:
        return None

    return isinstance(date_field, DateField)


class AppointmentsView(LoginRequiredMixin, View):
    template_name = "orders/appointments.html"

    def get(self, request, *args, **kwargs):
        if hasattr(request.user, "salon_manager_profile") or hasattr(
            request.user, "stylist"
        ):
            return redirect("dashboards:salon_manager_dashboard")

        customer = get_object_or_404(
            Customer.objects.select_related("user"), user=request.user
        )

        base_qs = OrderDetail.objects.filter(order__customer=customer).select_related(
            "order", "service", "salon", "stylist__user"
        )

        from django.utils import timezone
        from khayyam import JalaliDate
        from django.db.models import Q

        is_date_field = _order_detail_date_field_kind()

        cancelled_qs = base_qs.filter(order__status="cancelled").order_by(
            "-date", "-time"
        )
        active_qs = base_qs.exclude(order__status="cancelled")

        if is_date_field is None:
            past_active, upcoming_appointments = self._filter_manually(active_qs)
            past_appointments = list(cancelled_qs) + list(past_active)

        elif is_date_field:
            today = timezone.localdate()
            now_time = timezone.localtime(timezone.now()).time()

            past_active = active_qs.filter(
                Q(date__lt=today) | (Q(date=today) & Q(time__lt=now_time))
            ).order_by("-date", "-time")

            upcoming_appointments = active_qs.filter(
                Q(date__gt=today) | (Q(date=today) & Q(time__gte=now_time))
            ).order_by("date", "time")

            past_appointments = list(cancelled_qs) + list(past_active)

        else:
            today_str = JalaliDate.today().strftime("%Y-%m-%d")
            now_time = timezone.localtime(timezone.now()).time()

            past_active = active_qs.filter(
                Q(date__lt=today_str) | (Q(date=today_str) & Q(time__lt=now_time))
            ).order_by("-date", "-time")

            upcoming_appointments = active_qs.filter(
                Q(date__gt=today_str) | (Q(date=today_str) & Q(time__gte=now_time))
            ).order_by("date", "time")

            past_appointments = list(cancelled_qs) + list(past_active)

        context = {
            "past_appointments": past_appointments,
            "upcoming_appointments": upcoming_appointments,
        }
        return render(request, self.template_name, context)

    def _filter_manually(self, queryset):
        from django.utils import timezone

        all_appointments = list(queryset.all())
        today = timezone.localdate()
        now_time = timezone.localtime(timezone.now()).time()

        past = []
        upcoming = []

        for app in all_appointments:
            app_date = self._parse_date(app.date)
            if app_date is None:
                continue

            if app_date < today:
                past.append(app)
            elif app_date > today:
                upcoming.append(app)
            else:
                app_time = app.time or now_time
                if app_time < now_time:
                    past.append(app)
                else:
                    upcoming.append(app)

        past.sort(key=lambda x: (x.date, x.time), reverse=True)
        upcoming.sort(key=lambda x: (x.date, x.time))
        return past, upcoming


# ---------------------------------------------------------------------------------------------------------
# orders/views.py - اضافه کردن AppointmentDetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView
from django.db.models import Prefetch
from .models import OrderDetail
from urllib.parse import quote
from datetime import timezone as dt_timezone


class AppointmentDetailView(LoginRequiredMixin, DetailView):
    """
    صفحه جزئیات نوبت

    Features:
    - نمایش اطلاعات کامل نوبت
    - تاریخ و زمان شمسی
    - جزئیات خدمات و قیمت‌ها
    - دکمه‌های عملیاتی
    """

    model = OrderDetail
    template_name = "orders/appointment_detail.html"
    context_object_name = "appointment"

    def get_queryset(self):
        """
        فقط نوبت‌های مربوط به کاربر جاری
        + بهینه‌سازی کوئری‌ها
        """
        return (
            OrderDetail.objects.filter(order__customer__user=self.request.user)
            .select_related(
                "order",
                "order__customer",
                "order__customer__user",
                "service",
                "salon",
                "stylist",
                "stylist__user",
            )
            .prefetch_related(
                Prefetch(
                    "order__order_details1",
                    queryset=OrderDetail.objects.select_related(
                        "service",
                        "stylist",
                        "stylist__user",
                    ),
                )
            )
        )

    def post(self, request, *args, **kwargs):
        if _request_body_too_large(
            request,
            _appointment_review_post_max_bytes(),
        ):
            messages.error(request, "حجم اطلاعات ارسالی بیش از حد مجاز است.")
            return redirect("orders:appointment_detail", pk=kwargs.get("pk"))

        appointment = self.get_object()
        order = appointment.order
        customer = getattr(request.user, "customer_profile", None)

        if customer is None:
            messages.error(request, "برای ثبت دیدگاه باید با حساب مشتری وارد شوید.")
            return redirect("orders:appointment_detail", pk=appointment.pk)

        if not (
            appointment.service_completed_at
            or order.service_completed_at
            or order.status == "completed"
        ):
            messages.error(request, "ثبت دیدگاه فقط بعد از پایان خدمت امکان‌پذیر است.")
            return redirect("orders:appointment_detail", pk=appointment.pk)

        if order.review_completed_at:
            messages.info(request, "دیدگاه شما برای این نوبت قبلاً ثبت شده است.")
            return redirect("orders:appointment_detail", pk=appointment.pk)

        try:
            score = int(request.POST.get("score") or 0)
        except (TypeError, ValueError):
            score = 0

        if score < 1 or score > 5:
            messages.error(request, "لطفاً ابتدا امتیاز ۱ تا ۵ را انتخاب کنید.")
            return redirect("orders:appointment_detail", pk=appointment.pk)

        try:
            comment_text = _clean_appointment_review_comment(
                request.POST.get("comment_text")
            )
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("orders:appointment_detail", pk=appointment.pk)

        comment = Comments.objects.create(
            comment_user=customer,
            salon=appointment.salon,
            stylist=appointment.stylist,
            service=appointment.service,
            comment_text=comment_text,
            is_active=False,
        )
        Scoring.objects.create(
            comment=comment,
            scoring_user=customer,
            salon=appointment.salon,
            stylist=appointment.stylist,
            service=appointment.service,
            score=score,
        )

        order.review_completed_at = timezone.now()
        order.save(update_fields=["review_completed_at", "update_date"])

        messages.success(
            request,
            "دیدگاه و امتیاز شما ثبت شد و بعد از بررسی نمایش داده می‌شود.",
        )
        return redirect("orders:appointment_detail", pk=appointment.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        appointment = self.object
        order = appointment.order

        order_items = sorted(
            order.order_details1.all(),
            key=lambda item: (
                item.date or date.min,
                item.time or datetime.min.time(),
                item.pk,
            ),
        )
        context["order_items"] = order_items

        context["total_price"] = int(
            order.total_amount or sum(int(item.price or 0) for item in order_items) or 0
        )
        context["total_duration"] = sum(
            int(getattr(item.service, "duration_minutes", 0) or 0)
            for item in order_items
            if item.service
        )
        context["service_count"] = len(order_items)

        is_upcoming = appointment.is_upcoming()
        can_cancel = appointment.can_cancel()
        context["is_upcoming"] = is_upcoming
        context["is_past"] = appointment.is_past()
        context["can_cancel"] = can_cancel
        payment_record = order.payment_order.order_by("-id").first()
        wallet_transactions = list(
            order.wallet_transactions.order_by("-created_at")[:5]
        )
        if order.selected_payment_method == "pay_in_salon":
            context["payment_status_label"] = "پرداخت در مجموعه"
            context["payment_status_class"] = (
                "bg-amber-50 text-amber-700 border-amber-200"
            )
        elif order.is_paid:
            context["payment_status_label"] = "پرداخت شده"
            context["payment_status_class"] = (
                "bg-green-50 text-green-700 border-green-200"
            )
        else:
            context["payment_status_label"] = "در انتظار پرداخت"
            context["payment_status_class"] = (
                "bg-orange-50 text-orange-700 border-orange-200"
            )
        context["show_manage_cta"] = can_cancel
        context["finance_summary"] = [
            {"label": "جمع خدمات", "value": int(order.subtotal_amount or 0)},
            {
                "label": "تخفیف خدمات",
                "value": int(order.basket_discount_amount or 0),
                "tone": "discount",
                "text": None,
            },
            {
                "label": "عنوان کمپین خدمات",
                "text": order.basket_discount_title or "بدون سبد تخفیف",
            },
            {"label": "کد تخفیف", "text": order.coupon_code or "بدون کد"},
            {
                "label": "تخفیف کد",
                "value": int(order.coupon_discount_amount or 0),
                "tone": "discount",
                "text": None,
            },
            {
                "label": "جمع کل تخفیف",
                "value": int(order.discount_amount or 0),
                "tone": "discount",
            },
            {
                "label": "روش پرداخت",
                "text": order.get_selected_payment_method_display(),
            },
            {
                "label": "مبلغ نهایی",
                "value": int(order.total_amount or 0),
                "tone": "total",
            },
            {
                "label": "بازگشت وجه",
                "value": int(order.refunded_to_wallet_amount or 0),
                "tone": "refund",
            },
            {
                "label": "زمان بازگشت وجه",
                "text": (
                    _format_customer_datetime_fa(order.refunded_to_wallet_at)
                    if order.refunded_to_wallet_at
                    else "بدون بازگشت وجه"
                ),
            },
        ]
        if (
            (order.status == "completed" or order.service_completed_at)
            and order.is_paid
            and not order.review_requested_at
        ):
            mark_review_requested(order)
            order.refresh_from_db()

        context["payment_record"] = payment_record
        context["financial_transactions"] = wallet_transactions
        context["cancellation_policy"] = build_cancellation_policy(
            appointment.salon,
            can_cancel=can_cancel,
            is_upcoming=is_upcoming,
        )
        progress_context = build_customer_progress_context(order)
        context["customer_progress"] = progress_context
        context["customer_notifications"] = get_customer_notifications(order)
        context["pay_in_salon_action_url"] = reverse(
            "orders:pay_in_salon_settlement", kwargs={"pk": appointment.id}
        )
        context["review_url"] = (
            f"{reverse('salons:detail_salon', kwargs={'salon_id': appointment.salon.id})}?review=1&appointment_id={appointment.id}#reviews"
        )

        context["ics_link"] = reverse(
            "orders:appointment_ics", kwargs={"pk": appointment.id}
        )

        first_item = order_items[0] if order_items else appointment
        last_item = order_items[-1] if order_items else appointment
        tz = timezone.get_current_timezone()
        start_naive = datetime.combine(first_item.date, first_item.time)
        end_naive = datetime.combine(
            last_item.date, last_item.end_time or last_item.time
        )
        start_dt = timezone.localtime(
            timezone.make_aware(start_naive, tz)
            if timezone.is_naive(start_naive)
            else start_naive
        )
        end_dt = timezone.localtime(
            timezone.make_aware(end_naive, tz)
            if timezone.is_naive(end_naive)
            else end_naive
        )

        grouped_day_map = defaultdict(
            lambda: {"service_count": 0, "start": None, "end": None, "date_label": ""}
        )
        for item in order_items:
            bucket = grouped_day_map[item.date]
            bucket["service_count"] += 1
            bucket["date_label"] = (
                format_jalali_with_weekday(item.date) if item.date else ""
            )
            item_start = item.time
            item_end = item.end_time or item.time
            if bucket["start"] is None or item_start < bucket["start"]:
                bucket["start"] = item_start
            if bucket["end"] is None or item_end > bucket["end"]:
                bucket["end"] = item_end

        grouped_visit_days = []
        for day_key in sorted(grouped_day_map.keys()):
            bucket = grouped_day_map[day_key]
            start_label = format_time_fa(bucket["start"]) if bucket["start"] else ""
            end_label = format_time_fa(bucket["end"]) if bucket["end"] else ""
            grouped_visit_days.append(
                {
                    "date": bucket["date_label"],
                    "service_count": bucket["service_count"],
                    "time_label": (
                        f"{start_label} تا {end_label}"
                        if start_label and end_label
                        else start_label or end_label
                    ),
                }
            )

        is_split_day_booking = len(grouped_visit_days) > 1
        if is_split_day_booking:
            context["visit_date_label"] = (
                f"{grouped_visit_days[0]['date']} تا {grouped_visit_days[-1]['date']}"
            )
            context["visit_time_label"] = "رزرو چندروزه"
        else:
            context["visit_date_label"] = (
                format_jalali_with_weekday(first_item.date) if first_item.date else ""
            )
            start_time_label = (
                format_time_fa(first_item.time) if first_item.time else ""
            )
            end_source = last_item.end_time or last_item.time
            end_time_label = format_time_fa(end_source) if end_source else ""
            context["visit_time_label"] = (
                f"{start_time_label} تا {end_time_label}"
                if start_time_label and end_time_label
                else ""
            )

        context["grouped_visit_days"] = grouped_visit_days
        context["is_split_day_booking"] = is_split_day_booking

        def gcal_fmt(dt):
            return (
                timezone.localtime(dt)
                .astimezone(dt_timezone.utc)
                .strftime("%Y%m%dT%H%M%SZ")
            )

        title = quote(f"{appointment.salon.salon_name} - نوبت")
        details = quote(
            f"رزرو شما در {getattr(settings, 'BRAND_DISPLAY_NAME', 'Loomera')}"
        )
        location_txt = quote((appointment.salon.address or "").strip())
        dates = f"{gcal_fmt(start_dt)}/{gcal_fmt(end_dt)}"
        context["google_calendar_link"] = (
            f"https://calendar.google.com/calendar/render"
            f"?action=TEMPLATE&text={title}&dates={dates}&details={details}&location={location_txt}"
        )

        salon = appointment.salon
        lat = None
        lng = None
        lat_candidates = ["latitude", "lat", "location_lat", "geo_lat"]
        lng_candidates = ["longitude", "lng", "location_lng", "geo_lng", "lon"]

        for name in lat_candidates:
            if hasattr(salon, name) and getattr(salon, name):
                lat = getattr(salon, name)
                break

        for name in lng_candidates:
            if hasattr(salon, name) and getattr(salon, name):
                lng = getattr(salon, name)
                break

        if lat is not None and lng is not None:
            dest = quote(f"{lat},{lng}")
            context["salon_lat"] = str(lat)
            context["salon_lng"] = str(lng)
            context["salon_address_encoded"] = quote((salon.address or "").strip())
            context["google_maps_link"] = (
                f"https://www.google.com/maps/dir/?api=1&destination={dest}"
            )
            context["waze_link"] = (
                f"https://waze.com/ul?ll={quote(str(lat))}%2C{quote(str(lng))}&navigate=yes"
            )
        else:
            context["salon_lat"] = ""
            context["salon_lng"] = ""
            address = (salon.address or "").strip()
            context["salon_address_encoded"] = quote(address)
            if address:
                dest = quote(address)
                context["google_maps_link"] = (
                    f"https://www.google.com/maps/dir/?api=1&destination={dest}"
                )
                context["waze_link"] = f"https://waze.com/ul?q={dest}&navigate=yes"

        return context


# --------------------------------------------------------------------------------------------
# orders/views.py - Cancel Appointment View

from django.views import View
from django.http import JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404
from .models import OrderDetail


@method_decorator(require_POST, name="dispatch")
class PayInSalonSettlementView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            action = _clean_pay_in_salon_settlement_action(request)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("orders:appointment_detail", pk=pk)

        appointment = get_object_or_404(
            OrderDetail.objects.select_related("order__customer__user", "salon"),
            pk=pk,
            order__customer__user=request.user,
        )

        from apps.payments.finance import (
            confirm_pay_in_salon_cash_payment,
            sync_settlement_for_order,
        )
        from apps.payments.gateways import initiate_payment
        from apps.payments.models import Payment
        import secrets
        import uuid

        if action == "cash":
            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=appointment.order_id)

                if order.status == "cancelled":
                    messages.error(request, "این رزرو لغو شده و دیگر قابل تسویه نیست.")
                    return redirect("orders:appointment_detail", pk=appointment.pk)

                if not _order_ready_for_pay_in_salon_settlement(order):
                    messages.error(
                        request,
                        "پرداخت در مجموعه فقط بعد از پایان خدمت فعال می‌شود.",
                    )
                    return redirect("orders:appointment_detail", pk=appointment.pk)

                if order.is_paid:
                    messages.info(request, "این رزرو قبلاً از نظر مالی نهایی شده است.")
                    return redirect("orders:appointment_detail", pk=appointment.pk)

                if not _order_has_valid_pay_in_salon_method(order):
                    messages.error(
                        request,
                        "تسویه در مجموعه فقط برای رزروهای پرداخت در مجموعه فعال است.",
                    )
                    return redirect("orders:appointment_detail", pk=appointment.pk)

                try:
                    result = confirm_pay_in_salon_cash_payment(
                        order,
                        actor=request.user,
                        role="customer",
                    )
                except ValidationError as exc:
                    messages.error(request, str(exc))
                    return redirect("orders:appointment_detail", pk=appointment.pk)

            if result.get("finalized"):
                messages.success(
                    request,
                    "پرداخت نقدی با تایید شما و متخصص نهایی شد و امکان ثبت دیدگاه فعال است.",
                )
                payment = result.get("payment")
                if payment:
                    transaction.on_commit(
                        lambda order=result[
                            "order"
                        ], payment=payment: notify_payment_success(
                            customer=order.customer,
                            payment=payment,
                            order=order,
                        )
                    )
            else:
                messages.success(
                    request,
                    "تایید پرداخت نقدی شما ثبت شد. بعد از تایید متخصص، پرداخت نهایی می‌شود.",
                )

            return redirect("orders:appointment_detail", pk=appointment.pk)

        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=appointment.order_id)

            if order.status == "cancelled":
                messages.error(request, "این رزرو لغو شده و دیگر قابل تسویه نیست.")
                return redirect("orders:appointment_detail", pk=appointment.pk)

            if not _order_ready_for_pay_in_salon_settlement(order):
                messages.error(
                    request,
                    "پرداخت در مجموعه فقط بعد از پایان خدمت فعال می‌شود.",
                )
                return redirect("orders:appointment_detail", pk=appointment.pk)

            if order.is_paid:
                messages.info(request, "این رزرو قبلاً از نظر مالی نهایی شده است.")
                return redirect("orders:appointment_detail", pk=appointment.pk)

            if not _order_has_valid_pay_in_salon_method(order):
                messages.error(
                    request,
                    "تسویه در مجموعه فقط برای رزروهای پرداخت در مجموعه فعال است.",
                )
                return redirect("orders:appointment_detail", pk=appointment.pk)

            if getattr(order.salon, "verification_status", "") != "verified":
                messages.error(
                    request,
                    "پرداخت آنلاین تکمیلی فقط برای مجموعه‌های احراز هویت‌شده فعال است. برای این مجموعه، پرداخت نقدی را تایید کنید.",
                )
                return redirect("orders:appointment_detail", pk=appointment.pk)

            if int(order.total_amount or 0) <= 0:
                messages.error(request, "مبلغ قابل پرداخت برای این رزرو معتبر نیست.")
                return redirect("orders:appointment_detail", pk=appointment.pk)

            if _has_pending_pay_in_salon_online_payment(order, Payment):
                messages.info(
                    request,
                    "یک پرداخت آنلاین تکمیلی برای این رزرو در حال پردازش است.",
                )
                return redirect("orders:appointment_detail", pk=appointment.pk)

            original_method = order.selected_payment_method
            order.selected_payment_method = (
                AppointmentCheckoutForm.PAYMENT_METHOD_ONLINE
            )
            order.save(update_fields=["selected_payment_method", "update_date"])

            gateway_mode = str(
                getattr(settings, "PAYMENT_MODE", "mock") or "mock"
            ).lower()
            payment = Payment.objects.create(
                order=order,
                customer=order.customer,
                amount=order.total_amount,
                description=f"پرداخت آنلاین تکمیلی رزرو مجموعه {order.salon.salon_name} - سفارش {order.order_number}",
                provider=(
                    Payment.Provider.MOCK
                    if gateway_mode == "mock"
                    else str(
                        getattr(settings, "PAYMENT_PROVIDER", "zibal") or "zibal"
                    ).lower()
                ),
                purpose=Payment.Purpose.APPOINTMENT,
                state=Payment.State.PENDING,
                sandbox_mode=(gateway_mode != "live"),
                callback_token=secrets.token_urlsafe(24),
                idempotency_key=uuid.uuid4().hex,
                meta={
                    "source": "pay_in_salon_online",
                    "customer_mobile": order.customer.user.mobile_number,
                },
            )

        gateway_result = initiate_payment(
            request=request,
            payment=payment,
            amount_toman=payment.amount,
            description=payment.description,
            mobile_number=payment.customer.user.mobile_number,
        )

        if not gateway_result.success or not gateway_result.payment_url:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=order.pk)
                payment.mark_failure(
                    status_code=gateway_result.code or -2,
                    meta={
                        "request": gateway_result.raw or {},
                        "message": gateway_result.message,
                    },
                )
                order.selected_payment_method = original_method
                order.save(update_fields=["selected_payment_method", "update_date"])

            messages.error(
                request,
                gateway_result.message or "شروع پرداخت آنلاین ناموفق بود.",
            )
            return redirect("orders:appointment_detail", pk=appointment.pk)

        logger.info(
            "Pay-in-salon online settlement initiated | order=%s | payment=%s | provider=%s | track_id=%s",
            order.pk,
            payment.pk,
            payment.provider,
            gateway_result.track_id or "",
        )

        payment.gateway_track_id = gateway_result.track_id
        payment.status_code = gateway_result.code or 100
        payment.meta = {**(payment.meta or {}), "request": gateway_result.raw or {}}
        payment.save(update_fields=["gateway_track_id", "status_code", "meta"])

        sync_settlement_for_order(order, payment=payment)

        return redirect(gateway_result.payment_url)


class CancelAppointmentView(LoginRequiredMixin, View):
    """
    لغو نوبت توسط مشتری

    نکته امنیتی:
    اگر کاربر لاگین‌شده Customer مالک این نوبت نباشد، باید 404 بگیرد.
    نباید Http404 داخل except عمومی تبدیل به 500 شود.
    """

    def post(self, request, pk):
        appointment = get_object_or_404(
            OrderDetail.objects.select_related("order", "order__customer"),
            pk=pk,
            order__customer__user=request.user,
        )

        try:
            if not appointment.can_cancel():
                return JsonResponse(
                    {
                        "success": False,
                        "error": "امکان لغو این نوبت وجود ندارد. لطفاً با مجموعه تماس بگیرید.",
                    },
                    status=400,
                )

            order = appointment.order
            refund_amount = 0

            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=order.pk)

                if order.status == "cancelled":
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "این نوبت قبلاً لغو شده است.",
                        },
                        status=400,
                    )

                from apps.payments.finance import cancel_order_with_financials

                cancellation = cancel_order_with_financials(
                    order=order,
                    reason="لغو توسط مشتری",
                    refund_reason="لغو توسط مشتری",
                    payment=order.payment_order.order_by("-id").first(),
                )

                refund_amount = cancellation.refund_amount
                cancel_order_reminder(order)

            notify_booking_cancelled(
                customer=order.customer,
                order=order,
                refund_amount=refund_amount,
            )
            queue_customer_booking_cancelled_sms(
                order,
                event_type="booking_cancelled",
                order_detail=appointment,
            )

            _notify_manager_and_stylists_for_customer_order_event(
                order,
                event_type="customer_cancelled_booking",
                manager_title="نوبت توسط مشتری لغو شد",
                stylist_title="نوبت شما توسط مشتری لغو شد",
                body="مشتری این نوبت را لغو کرد و وضعیت رزرو برای مجموعه به‌روزرسانی شد.",
                detail_meta={"refund_amount": int(refund_amount or 0)},
            )

            message = "نوبت شما با موفقیت لغو شد."
            if refund_amount:
                message += (
                    f" مبلغ {refund_amount:,} تومان به کیف پول شما برگشت داده شد."
                )

            return JsonResponse(
                {
                    "success": True,
                    "message": message,
                    "refund_amount": refund_amount,
                }
            )

        except Http404:
            raise

        except Exception as e:
            logger.exception(
                "Cancel appointment failed | appointment=%s | user=%s",
                pk,
                request.user.pk,
            )
            return JsonResponse(
                {
                    "success": False,
                    "error": "لغو نوبت در حال حاضر ممکن نیست. لطفاً دوباره تلاش کنید.",
                },
                status=500,
            )


# ---------------------------------------------------------------------
from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify
from urllib.parse import quote


class AppointmentICSView(LoginRequiredMixin, View):
    """
    دانلود فایل ICS برای اضافه شدن به تقویم (Mobile Calendar / Outlook / Apple)
    """

    def get(self, request, pk):
        appointment = get_object_or_404(
            OrderDetail.objects.select_related(
                "order", "service", "salon", "stylist__user"
            ),
            pk=pk,
            order__customer__user=request.user,
        )

        # ----- datetime start/end (timezone-aware) -----
        order_items = sorted(
            appointment.order.order_details1.select_related(
                "service", "stylist__user"
            ).all(),
            key=lambda item: (
                item.date or date.min,
                item.time or datetime.min.time(),
                item.pk,
            ),
        )
        first_item = order_items[0] if order_items else appointment
        last_item = order_items[-1] if order_items else appointment

        start_naive = datetime.combine(first_item.date, first_item.time)
        tz = timezone.get_current_timezone()
        start_dt = (
            timezone.make_aware(start_naive, tz)
            if timezone.is_naive(start_naive)
            else start_naive
        )
        start_dt = timezone.localtime(start_dt)

        end_naive = datetime.combine(
            last_item.date, last_item.end_time or last_item.time
        )
        end_dt = (
            timezone.make_aware(end_naive, tz)
            if timezone.is_naive(end_naive)
            else end_naive
        )
        end_dt = timezone.localtime(end_dt)

        # ----- ICS fields -----
        salon_name = _clean_ics_text(
            appointment.salon.salon_name if appointment.salon else "Salon",
            default="Salon",
        )

        service_names = [
            _clean_ics_text(item.service.service_name, default="Service")
            for item in order_items
            if item.service
        ]
        service_name = (
            " + ".join(service_names[:3])
            if service_names
            else _clean_ics_text(
                appointment.service.service_name if appointment.service else "Service",
                default="Service",
            )
        )
        if len(service_names) > 3:
            service_name += " ..."

        stylist_names = []
        for item in order_items:
            if item.stylist and item.stylist.user:
                raw_stylist_name = (
                    item.stylist.user.get_fullName()
                    if hasattr(item.stylist.user, "get_fullName")
                    else str(item.stylist.user)
                )
                stylist_names.append(
                    _clean_ics_text(raw_stylist_name, default="Stylist")
                )

        stylist_name = "، ".join(stylist_names[:3])

        summary = _escape_ics_text(f"{service_name} - {salon_name}")
        description = _escape_ics_text(
            f"Services: {service_name} | Stylist: {stylist_name} | Salon: {salon_name}"
        )
        location = _escape_ics_text(
            appointment.salon.address
            if appointment.salon and appointment.salon.address
            else ""
        )

        # DTSTART/DTEND with TZID
        tzid = _clean_ics_token(
            getattr(tz, "zone", "Asia/Tehran"), default="Asia/Tehran"
        )
        dtstart = start_dt.strftime("%Y%m%dT%H%M%S")
        dtend = end_dt.strftime("%Y%m%dT%H%M%S")
        dtstamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")

        uid_domain = _clean_ics_token(
            getattr(settings, "BRAND_DOMAIN", "loomera.local"),
            default="loomera.local",
        )
        uid = _clean_ics_token(
            f"loomera-appointment-{appointment.pk}-{appointment.order_id}@{uid_domain}",
            default=f"loomera-appointment-{appointment.pk}@loomera.local",
        )

        prodid = _escape_ics_text(
            getattr(settings, "LOOMERA_CALENDAR_PRODID", "-//Loomera//Appointment//FA"),
            default="-//Loomera//Appointment//FA",
        )
        calendar_name = _escape_ics_text(
            getattr(settings, "LOOMERA_CALENDAR_NAME", "Loomera Appointment"),
            default="Loomera Appointment",
        )

        ics = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            + _ics_line("PRODID", prodid)
            + _ics_line("X-WR-CALNAME", calendar_name)
            + "CALSCALE:GREGORIAN\r\n"
            "METHOD:PUBLISH\r\n"
            "BEGIN:VEVENT\r\n"
            + _ics_line("UID", uid)
            + _ics_line("DTSTAMP", dtstamp)
            + _ics_line(f"DTSTART;TZID={tzid}", dtstart)
            + _ics_line(f"DTEND;TZID={tzid}", dtend)
            + _ics_line("SUMMARY", summary)
            + _ics_line("DESCRIPTION", description)
            + _ics_line("LOCATION", location)
            + "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )

        filename = f"loomera-appointment-{appointment.pk}.ics"
        resp = HttpResponse(ics, content_type="text/calendar; charset=utf-8")
        # ✅ inline به جای attachment → Android app chooser نشان می‌دهد
        resp["Content-Disposition"] = f'inline; filename="{filename}"'
        return resp


# -----------------------------------------------------------------------
class RescheduleDateTimeView(LoginRequiredMixin, View):
    """
    باز کردن صفحه انتخاب تاریخ/زمان (همان UI فاز 1) برای تغییر زمان
    """

    template_name = "orders/select_datetime.html"

    def get(self, request, pk):
        appointment = get_object_or_404(
            OrderDetail.objects.select_related("order", "salon"),
            pk=pk,
            order__customer__user=request.user,
        )

        order = appointment.order
        salon_id = appointment.salon_id  # ✅ Order.salon نداریم (علت ارور شما همین بود)

        # همه آیتم‌های سفارش (برای reschedule گروهی)
        items = sorted(
            order.order_details1.select_related("service", "stylist__user").all(),
            key=lambda item: (
                item.date or date.min,
                item.time or datetime.min.time(),
                item.pk,
            ),
        )

        stylist_selections = []
        for it in items:
            stylist_id = (
                str(it.stylist.user.id) if it.stylist and it.stylist.user else "any"
            )
            stylist_name = (
                it.stylist.user.get_fullName()
                if (
                    it.stylist
                    and it.stylist.user
                    and hasattr(it.stylist.user, "get_fullName")
                )
                else ""
            )
            stylist_selections.append(
                {
                    "serviceId": it.service_id,
                    "serviceName": it.service.service_name if it.service else "خدمت",
                    "serviceDuration": getattr(it.service, "duration_minutes", 60)
                    or 60,
                    "serviceBuffer": getattr(it.service, "buffer_minutes", 0) or 0,
                    "stylistId": stylist_id,
                    "requestedStylistId": stylist_id,
                    "stylistName": stylist_name,
                    "requestedStylistName": stylist_name,
                    "stylistProfileImage": (
                        it.stylist.profile_image.url
                        if (it.stylist and getattr(it.stylist, "profile_image", None))
                        else None
                    ),
                }
            )

        # ✅ ذخیره context reschedule در session تا ConfirmView بداند چه چیزی را آپدیت کند
        request.session["reschedule_order_id"] = order.id
        request.session["reschedule_base_appointment_id"] = appointment.id
        request.session["salon_id"] = str(salon_id)
        request.session["stylist_selections"] = stylist_selections

        context = {
            "hide_navbar": True,
            "salon_id": str(salon_id),
            "stylist_selections_json": json.dumps(
                stylist_selections, ensure_ascii=False
            ),
            # ✅ فرم باید به reschedule_confirm برود
            "form_action": reverse("orders:reschedule_confirm"),
        }
        return render(request, self.template_name, context)


# -----------------------------------------------------------------------
class RescheduleConfirmView(LoginRequiredMixin, View):
    """
    تایید و ثبت تغییر زمان با validate ترتیبی برای چند خدمت
    """

    @transaction.atomic
    def post(self, request):
        booking_data_json = request.POST.get("booking_data")
        if not booking_data_json:
            messages.error(request, "اطلاعات انتخاب زمان دریافت نشد.")
            return redirect("orders:appointments")

        try:
            booking_data = json.loads(booking_data_json)
        except (json.JSONDecodeError, TypeError):
            messages.error(request, "فرمت اطلاعات انتخاب زمان نامعتبر است.")
            return redirect("orders:appointments")

        order_id = request.session.get("reschedule_order_id")
        if not order_id:
            messages.error(
                request, "کانتکست تغییر زمان منقضی شده است. دوباره تلاش کنید."
            )
            return redirect("orders:appointments")

        order = get_object_or_404(Order, id=order_id, customer__user=request.user)
        items = list(
            order.order_details1.select_related(
                "service", "stylist__user", "salon"
            ).all()
        )
        if not items:
            messages.error(request, "آیتمی برای تغییر زمان یافت نشد.")
            return redirect("orders:appointments")

        datetime_selections = booking_data.get("datetime_selections", {}) or {}
        stylist_selections = booking_data.get("stylist_selections", []) or []
        exclude_ids = [item.id for item in items]
        base_id = request.session.get("reschedule_base_appointment_id") or items[0].id
        salon = items[0].salon

        try:
            resolved_items = resolve_booking_sequence(
                salon=salon,
                stylist_selections=stylist_selections,
                datetime_selections=datetime_selections,
                exclude_order_detail_ids=exclude_ids,
            )

            by_service_stylist = {
                (
                    item.service_id,
                    (
                        item.stylist.user_id
                        if item.stylist and item.stylist.user
                        else None
                    ),
                ): item
                for item in items
            }

            for stylist_id in sorted(
                {int(item.stylist.user_id) for item in resolved_items}
            ):
                Stylist.objects.select_for_update().get(user_id=stylist_id)

            for resolved in resolved_items:
                requested = resolved.requested_stylist_id
                existing = None
                if requested not in (None, "", "any"):
                    existing = by_service_stylist.get(
                        (resolved.service.id, int(requested))
                    )
                if existing is None:
                    existing = by_service_stylist.get(
                        (resolved.service.id, resolved.stylist.user_id)
                    )
                if existing is None:
                    continue

                existing.stylist = resolved.stylist
                existing.price = resolved.price
                existing.date = resolved.date_value
                existing.time = resolved.start_time
                existing.end_time = resolved.end_time
                existing.scheduled_duration_minutes = int(
                    getattr(resolved.service, "duration_minutes", 0) or 30
                )
                existing.buffer_minutes = int(
                    getattr(resolved.service, "buffer_minutes", 0) or 0
                )
                existing.save(
                    update_fields=[
                        "stylist",
                        "price",
                        "date",
                        "time",
                        "end_time",
                        "scheduled_duration_minutes",
                        "buffer_minutes",
                        "occupied_until",
                    ]
                )

            order.refresh_from_db()

            _notify_manager_and_stylists_for_customer_order_event(
                order,
                event_type="booking_rescheduled",
                manager_title="زمان نوبت توسط مشتری تغییر کرد",
                stylist_title="زمان نوبت شما تغییر کرد",
                body="مشتری زمان نوبت را تغییر داد. لطفاً زمان جدید را در تقویم بررسی کنید.",
                detail_meta={"base_appointment_id": base_id},
            )
            queue_customer_booking_rescheduled_sms(order)

            messages.success(request, "زمان نوبت با موفقیت تغییر کرد.")
            return redirect("orders:appointment_detail", pk=base_id)

        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("orders:appointment_detail", pk=base_id)

        except Exception:
            messages.error(request, "خطا در تغییر زمان. دوباره تلاش کنید.")
            return redirect("orders:appointment_detail", pk=base_id)


# ---------------------------------------------------------------------------------------------------------
# Checkout flow for reservation payments
from django.conf import settings
from apps.orders.forms import AppointmentCheckoutForm


def _get_session_booking_context(request):
    """
    Load and resolve the booking session for checkout.

    All three booking session keys are required. Session data is input, not an
    authoritative reservation: sequence resolution is delegated to
    ``resolve_booking_sequence`` and callers must still revalidate availability
    under database locks before creating an order. This helper does not write the
    database or reserve a slot.
    """
    salon_id = request.session.get("salon_id")
    stylist_selections = request.session.get("stylist_selections", [])
    datetime_selections = request.session.get("datetime_selections", {})

    if not all([salon_id, stylist_selections, datetime_selections]):
        raise ValidationError("اطلاعات رزرو ناقص است.")

    salon = get_object_or_404(Salon, pk=salon_id)
    resolved_items = resolve_booking_sequence(
        salon=salon,
        stylist_selections=stylist_selections,
        datetime_selections=datetime_selections,
    )
    return salon, resolved_items, stylist_selections, datetime_selections


def _get_active_coupon(coupon_code, salon=None):
    from apps.discounts.services import DiscountEligibilityService

    return DiscountEligibilityService.get_coupon(coupon_code, salon=salon)


def _customer_has_commissioned_salon_order(customer, salon):
    return (
        Order.objects.filter(
            customer=customer,
            salon=salon,
            platform_commission_applies=True,
        )
        .exclude(status="cancelled")
        .exists()
    )


def _build_checkout_payload(*, request, coupon_code=""):
    """
    Build the read-only checkout preview and pricing snapshot.

    The payload is derived from the current customer, resolved booking sequence,
    active discounts, coupon eligibility, commission settings, and current wallet
    balance. An invalid coupon is treated as absent. This function does not create
    an Order or Payment, charge a wallet, consume a quick link, or reserve a slot.
    """
    from apps.discounts.services import (
        DiscountEligibilityService,
        build_basket_snapshot,
        persist_order_discount_records,
    )
    from apps.discounts.utils import calculate_best_service_discount_for_items

    customer = get_object_or_404(Customer, user=request.user)
    salon, resolved_items, stylist_selections, datetime_selections = (
        _get_session_booking_context(request)
    )
    coupon = _get_active_coupon(coupon_code, salon=salon)
    subtotal = sum(int(item.price or 0) for item in resolved_items)
    online_payment_enabled = bool(getattr(settings, "ONLINE_PAYMENT_ENABLED", False))
    first_visit = not _customer_has_commissioned_salon_order(customer, salon)
    requires_online_payment = bool(first_visit and online_payment_enabled)

    basket_discount = calculate_best_service_discount_for_items(
        salon=salon, resolved_items=resolved_items
    )
    basket_discount_amount = int(basket_discount.amount or 0)
    basket_discount_percent = int(basket_discount.percent or 0)
    basket_discount_cap_amount = int(basket_discount.cap_amount or 0)
    subtotal_after_service_discount = max(subtotal - basket_discount_amount, 0)

    coupon_validation = (
        DiscountEligibilityService.validate_coupon(
            coupon=coupon,
            customer=customer,
            salon=salon,
            subtotal_after_service_discount=subtotal_after_service_discount,
            subtotal=subtotal,
            payment_method="",
        )
        if coupon
        else None
    )
    if coupon and coupon_validation and not coupon_validation.is_valid:
        coupon = None
    discount_percent = (
        int(coupon.effective_discount_value)
        if coupon and coupon.effective_discount_type == "percentage"
        else 0
    )
    coupon_discount_amount = (
        int(coupon_validation.amount or 0) if coupon_validation else 0
    )
    coupon_cap_amount = (
        int(getattr(coupon, "max_discount_amount", 0) or 0) if coupon else 0
    )
    coupon_discount_snapshot = coupon_validation.snapshot if coupon_validation else {}
    basket_discount_snapshot = build_basket_snapshot(
        basket_discount.basket,
        amount=basket_discount_amount,
        raw_amount=basket_discount_amount,
        base_amount=basket_discount.eligible_subtotal,
        service_ids=basket_discount.discounted_service_ids,
    )
    discount_amount = basket_discount_amount + coupon_discount_amount
    taxable_subtotal = max(subtotal - discount_amount, 0)
    tax_amount = 0
    commission_percent = (
        int(getattr(settings, "PLATFORM_FIRST_VISIT_COMMISSION_PERCENT", 0) or 0)
        if requires_online_payment
        else 0
    )
    commission_amount = (
        int((taxable_subtotal * commission_percent) / 100) if commission_percent else 0
    )
    total_amount = taxable_subtotal
    salon_payout_amount = max(total_amount - commission_amount, 0)

    service_details = []
    overall_start = None
    overall_end = None
    grouped_day_map = {}
    discounted_service_ids = set(basket_discount.discounted_service_ids or ())
    for item in resolved_items:
        if overall_start is None or item.start_datetime < overall_start:
            overall_start = item.start_datetime
        if overall_end is None or item.end_datetime > overall_end:
            overall_end = item.end_datetime
        day_label = format_jalali_numeric(item.date_value)
        start_raw = item.start_time.strftime("%H:%M")
        end_raw = item.end_time.strftime("%H:%M")
        start_label = format_time_fa(item.start_time)
        end_label = format_time_fa(item.end_time)

        service_details.append(
            {
                "sequence": item.index + 1,
                "service": item.service,
                "stylist": item.stylist,
                "price": int(item.price or 0),
                "date": day_label,
                "date_value": item.date_value,
                "time": start_label,
                "end_time": end_label,
                "duration": item.duration_minutes,
                "auto_resolved": item.auto_resolved,
                "has_service_discount": item.service.id in discounted_service_ids,
            }
        )

        day_bucket = grouped_day_map.setdefault(
            item.date_value,
            {
                "date": day_label,
                "service_count": 0,
                "start": start_raw,
                "end": end_raw,
            },
        )
        day_bucket["service_count"] += 1

        if start_raw < day_bucket["start"]:
            day_bucket["start"] = start_raw

        if end_raw > day_bucket["end"]:
            day_bucket["end"] = end_raw

    for bucket in grouped_day_map.values():
        bucket["start"] = format_time_fa(bucket["start"])
        bucket["end"] = format_time_fa(bucket["end"])

    grouped_days = [grouped_day_map[key] for key in sorted(grouped_day_map.keys())]
    is_split_day_booking = len(grouped_days) > 1
    overall_date_label = (
        f"{grouped_days[0]['date']} تا {grouped_days[-1]['date']}"
        if is_split_day_booking
        else (grouped_days[0]["date"] if grouped_days else "")
    )
    overall_time_label = (
        f"{format_time_fa(overall_start)} تا {format_time_fa(overall_end)}"
        if overall_start and overall_end and not is_split_day_booking
        else "رزرو چندروزه"
    )

    return {
        "customer": customer,
        "salon": salon,
        "resolved_items": resolved_items,
        "stylist_selections": stylist_selections,
        "datetime_selections": datetime_selections,
        "coupon": coupon,
        "coupon_code": coupon_code,
        "service_details": service_details,
        "subtotal": subtotal,
        "discount_percent": discount_percent,
        "discount_amount": discount_amount,
        "basket_discount_amount": basket_discount_amount,
        "basket_discount_percent": basket_discount_percent,
        "basket_discount_cap_amount": basket_discount_cap_amount,
        "basket_discount_title": basket_discount.title,
        "basket_discount_service_count": len(
            basket_discount.discounted_service_ids or ()
        ),
        "basket_discount_basket": basket_discount.basket,
        "basket_discount_snapshot": basket_discount_snapshot,
        "coupon_discount_amount": coupon_discount_amount,
        "coupon_discount_snapshot": coupon_discount_snapshot,
        "discount_cap_amount": coupon_cap_amount,
        "tax_amount": tax_amount,
        "total_amount": total_amount,
        "discount_rules_snapshot": {
            "version": 1,
            "basket": basket_discount_snapshot,
            "coupon": coupon_discount_snapshot,
            "total_discount_amount": discount_amount,
        },
        "commission_percent": commission_percent,
        "commission_amount": commission_amount,
        "salon_payout_amount": salon_payout_amount,
        "requires_online_payment": requires_online_payment,
        "online_payment_enabled": online_payment_enabled,
        "wallet_balance": int(
            getattr(getattr(customer.user, "wallet", None), "balance", 0) or 0
        ),
        "payout_profile_complete": salon.payout_profile_complete,
        "overall_date_label": overall_date_label,
        "overall_time_label": overall_time_label,
        "grouped_days": grouped_days,
        "is_split_day_booking": is_split_day_booking,
        "booking_policy": build_cancellation_policy(
            salon, can_cancel=True, is_upcoming=True
        ),
    }


_CHECKOUT_SESSION_KEY = "finance_checkout_submission"

_CHECKOUT_SLOT_LOST_SESSION_KEY = "checkout_slot_lost_notice"


def _validation_error_message(exc):
    exc_messages = getattr(exc, "messages", None)
    if exc_messages:
        return " ".join(str(item) for item in exc_messages)
    return str(exc)


def _store_checkout_slot_lost_notice(request, *, message: str):
    request.session[_CHECKOUT_SLOT_LOST_SESSION_KEY] = {
        "title": "این زمان همین الان پر شد",
        "message": message,
        "hint": "انتخاب‌های خدمت و متخصص حفظ شده‌اند؛ فقط یک زمان آزاد جدید انتخاب کن.",
        "action_label": "انتخاب زمان جدید",
    }
    request.session.modified = True


def _pop_checkout_slot_lost_notice(request):
    notice = request.session.pop(_CHECKOUT_SLOT_LOST_SESSION_KEY, None)
    if notice:
        request.session.modified = True
    return notice


def _build_checkout_submission_fingerprint(
    *, request, payload, payment_method: str, coupon_code: str
):
    """
    Build the deterministic duplicate-submission fingerprint for checkout.

    The SHA-256 input binds the user, salon, payment method, coupon, total amount,
    and ordered service/stylist/date/time sequence. It is an idempotency hint for
    redirecting repeated submissions; it is not authorization, not a payment
    proof, and not a slot lock. Callers must still validate the session and availability.
    """
    signature = {
        "user_id": request.user.id,
        "salon_id": payload["salon"].id if payload.get("salon") else None,
        "payment_method": payment_method,
        "coupon_code": coupon_code or "",
        "total_amount": int(payload.get("total_amount") or 0),
        "services": [
            {
                "service_id": int(item.service.id),
                "stylist_id": int(item.stylist.user_id),
                "date": item.date_value.strftime("%Y-%m-%d"),
                "time": item.start_time.strftime("%H:%M"),
                "end_time": item.end_time.strftime("%H:%M"),
            }
            for item in payload.get("resolved_items") or []
        ],
    }
    raw = json.dumps(signature, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _get_checkout_submission_redirect(request, fingerprint: str):
    record = request.session.get(_CHECKOUT_SESSION_KEY) or {}
    if record.get("fingerprint") != fingerprint:
        return None

    created_at = record.get("created_at") or 0
    now_ts = timezone.now().timestamp()
    if now_ts - float(created_at or 0) > 1800:
        request.session.pop(_CHECKOUT_SESSION_KEY, None)
        request.session.modified = True
        return None

    return record.get("redirect_url") or None


def _store_checkout_submission_result(
    request, *, fingerprint: str, redirect_url: str, order_id: int | None = None
):
    request.session[_CHECKOUT_SESSION_KEY] = {
        "fingerprint": fingerprint,
        "redirect_url": redirect_url,
        "order_id": order_id,
        "created_at": timezone.now().timestamp(),
    }
    request.session.modified = True


def _cancel_previous_pending_checkout_hold(request, *, current_fingerprint: str):
    record = request.session.get(_CHECKOUT_SESSION_KEY) or {}
    if not record or record.get("fingerprint") == current_fingerprint:
        return
    order_id = record.get("order_id")
    if not order_id:
        return
    try:
        order = Order.objects.select_for_update().get(
            pk=order_id,
            customer__user=request.user,
            selected_payment_method=AppointmentCheckoutForm.PAYMENT_METHOD_ONLINE,
            is_paid=False,
            is_finally=False,
        )
    except Order.DoesNotExist:
        return
    if order.status == "cancelled":
        return
    order.status = "cancelled"
    order.cancellation_reason = (
        "انصراف از پرداخت آنلاین و تغییر روش پرداخت قبل از نهایی‌سازی"
    )
    order.save(update_fields=["status", "cancellation_reason", "update_date"])
    try:
        from apps.payments.models import Payment

        order.payment_order.filter(
            state__in=[Payment.State.INITIATED, Payment.State.PENDING]
        ).update(state=Payment.State.CANCELLED)
    except Exception:
        logger.exception(
            "Failed to cancel stale checkout payment hold | order=%s", order.pk
        )


CHECKOUT_SLOT_BLOCKING_STATUSES = (
    "pending",
    "confirmed",
    "paid",
    "completed",
)


def _assert_checkout_slots_still_available(*, salon, resolved_items):
    """
    Recheck slot conflicts at the final checkout boundary.

    Call this inside ``transaction.atomic`` after locking every participating
    stylist with ``select_for_update``. Pending, confirmed, paid, and completed
    orders block overlapping slots, while explicitly rejected details do not.
    Conflicts raise ValidationError. This helper does not create, cancel, or
    settle an order.
    """
    for item in resolved_items:
        conflict_qs = (
            OrderDetail.objects.select_related(
                "order", "service", "stylist", "stylist__user"
            )
            .filter(
                salon=salon,
                stylist=item.stylist,
                date=item.date_value,
                order__status__in=CHECKOUT_SLOT_BLOCKING_STATUSES,
            )
            .filter(
                Q(time__lt=item.end_time, end_time__gt=item.start_time)
                | Q(end_time__isnull=True, time=item.start_time)
            )
        )

        if hasattr(OrderDetail, "ConfirmationStatus"):
            conflict_qs = conflict_qs.exclude(
                confirmation_status=OrderDetail.ConfirmationStatus.REJECTED
            )

        conflict = conflict_qs.order_by("time", "id").first()

        if conflict:
            service_name = item.service.service_name if item.service else "این خدمت"

            try:
                stylist_name = item.stylist.get_fullName()
            except Exception:
                stylist_name = "متخصص انتخاب‌شده"

            date_label = format_jalali_numeric(item.date_value)
            time_label = (
                f"{format_time_fa(item.start_time)} تا {format_time_fa(item.end_time)}"
            )

            raise ValidationError(
                f"زمان {time_label} در تاریخ {date_label} برای «{service_name}» نزد {stylist_name} "
                "دیگر آزاد نیست و احتمالاً همین الان توسط کاربر دیگری گرفته شده است. "
                "لطفاً از همین صفحه زمان آزاد دیگری انتخاب کنید."
            )


class AppointmentCheckoutView(LoginRequiredMixin, View):
    template_name = "orders/reservation_preview.html"

    def _render(self, request, form=None, coupon_code=""):
        payload = _build_checkout_payload(request=request, coupon_code=coupon_code)
        form = form or AppointmentCheckoutForm(
            initial={
                "coupon_code": coupon_code,
                "payment_method": (
                    AppointmentCheckoutForm.PAYMENT_METHOD_ONLINE
                    if payload["requires_online_payment"]
                    else AppointmentCheckoutForm.PAYMENT_METHOD_SALON
                ),
            },
            requires_online_payment=payload["requires_online_payment"],
        )
        context = {
            "hide_navbar": True,
            "checkout": payload,
            "form": form,
        }
        return render(request, self.template_name, context)

    def get(self, request, *args, **kwargs):
        try:
            coupon_code = _clean_appointment_checkout_coupon_code(
                request.GET.get("coupon")
            )
        except ValidationError as exc:
            messages.error(request, str(exc))
            coupon_code = ""

        if coupon_code:
            from urllib.parse import urlencode

            return redirect(
                f"{reverse('orders:reservation_preview')}?{urlencode({'coupon': coupon_code})}"
            )

        return redirect("orders:reservation_preview")

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        """Own the transactional finalization boundary for appointment checkout.

        The method rebuilds and validates the preview, enforces payment policy and
        coupon eligibility, applies the duplicate-submission guard, locks participating
        stylists, resolves the sequence again, and rechecks slot conflicts before
        creating Order and OrderDetail records. Each OrderDetail stores the resolved
        duration, service buffer, and occupied-until snapshot used by later conflict
        checks. Payment-method-specific branches own their Payment, wallet,
        notification, settlement, session-cleanup, and redirect side effects. A gateway
        initiation success is only a handoff to the provider; it is not payment
        settlement.
        """
        try:
            form_action = _clean_appointment_checkout_form_action(request)
            coupon_code = _clean_appointment_checkout_coupon_code(
                request.POST.get("coupon_code")
            )
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("orders:reservation_preview")

        checkout_action = form_action or "confirm_checkout"

        post_data = request.POST.copy()
        post_data["coupon_code"] = coupon_code

        try:
            preview_payload = _build_checkout_payload(
                request=request,
                coupon_code=coupon_code,
            )
        except ValidationError as exc:
            error_message = _validation_error_message(exc)
            _store_checkout_slot_lost_notice(request, message=error_message)
            messages.warning(
                request,
                "زمان انتخاب‌شده دیگر آزاد نیست. لطفاً زمان جدیدی انتخاب کنید.",
            )
            return redirect("orders:select_dateTime")

        form = AppointmentCheckoutForm(
            post_data,
            requires_online_payment=preview_payload["requires_online_payment"],
        )
        if not form.is_valid():
            return self._render(
                request,
                form=form,
                coupon_code=coupon_code,
            )

        payment_method = form.cleaned_data["payment_method"]

        if (
            not getattr(settings, "ONLINE_PAYMENT_ENABLED", False)
            and payment_method != AppointmentCheckoutForm.PAYMENT_METHOD_SALON
        ):
            form.add_error(
                "payment_method",
                "در نسخه بتا فقط پرداخت در مجموعه فعال است.",
            )
            return self._render(
                request,
                form=form,
                coupon_code=coupon_code,
            )

        coupon_code = form.cleaned_data.get("coupon_code", "")
        try:
            coupon_code = _clean_appointment_checkout_coupon_code(coupon_code)
        except ValidationError as exc:
            form.add_error("coupon_code", str(exc))
            return self._render(request, form=form, coupon_code="")

        payload = _build_checkout_payload(request=request, coupon_code=coupon_code)

        if checkout_action == "clear_coupon":
            messages.info(request, "کد تخفیف از این رزرو حذف شد.")
            return self._render(request, form=form, coupon_code="")

        if checkout_action == "apply_coupon":
            if coupon_code and not payload["coupon"]:
                form.add_error("coupon_code", "کد تخفیف واردشده معتبر یا فعال نیست.")
                return self._render(request, form=form, coupon_code=coupon_code)

            if coupon_code and payload["coupon"]:
                eligible_methods = (
                    getattr(payload["coupon"], "eligible_payment_methods", []) or []
                )
                if eligible_methods and payment_method not in eligible_methods:
                    form.add_error(
                        "coupon_code",
                        "این کد برای روش پرداخت انتخابی معتبر نیست.",
                    )
                    return self._render(request, form=form, coupon_code=coupon_code)

                messages.success(request, "کد تخفیف روی مبلغ نهایی اعمال شد.")

            return self._render(request, form=form, coupon_code=coupon_code)

        if coupon_code and payload.get("coupon"):
            eligible_methods = (
                getattr(payload["coupon"], "eligible_payment_methods", []) or []
            )
            if eligible_methods and payment_method not in eligible_methods:
                form.add_error(
                    "coupon_code",
                    "این کد برای روش پرداخت انتخابی معتبر نیست.",
                )
                return self._render(request, form=form, coupon_code=coupon_code)

        if coupon_code and not payload["coupon"]:
            messages.warning(
                request,
                "کد تخفیف نامعتبر بود و بدون تخفیف، رزرو ادامه پیدا کرد.",
            )
            coupon_code = ""
            payload = _build_checkout_payload(request=request, coupon_code="")

        checkout_fingerprint = _build_checkout_submission_fingerprint(
            request=request,
            payload=payload,
            payment_method=payment_method,
            coupon_code=coupon_code,
        )

        existing_redirect = _get_checkout_submission_redirect(
            request,
            checkout_fingerprint,
        )

        if checkout_action == "confirm_checkout" and existing_redirect:
            messages.info(
                request,
                "این رزرو قبلاً در حال ثبت بود و به همان نتیجه هدایت شدید.",
            )
            return redirect(existing_redirect)

        if checkout_action == "confirm_checkout":
            _cancel_previous_pending_checkout_hold(
                request,
                current_fingerprint=checkout_fingerprint,
            )

        customer = payload["customer"]
        salon = payload["salon"]

        logger.info(
            "Checkout started | customer=%s | salon=%s | payment_method=%s | total=%s | items=%s",
            customer.pk,
            salon.pk if salon else None,
            payment_method,
            int(payload.get("total_amount") or 0),
            len(payload.get("resolved_items") or []),
        )

        if payment_method in {
            AppointmentCheckoutForm.PAYMENT_METHOD_ONLINE,
            AppointmentCheckoutForm.PAYMENT_METHOD_WALLET,
        }:
            gateway_mode = str(
                getattr(settings, "PAYMENT_MODE", "mock") or "mock"
            ).lower()
            if gateway_mode == "live" and not salon.payout_profile_complete:
                messages.error(
                    request,
                    "اطلاعات تسویه این مجموعه هنوز کامل نشده و پرداخت آنلاین در حالت live فعلاً مجاز نیست.",
                )
                return self._render(request, form=form, coupon_code=coupon_code)

        locked_ids = sorted(
            {int(item.stylist.user_id) for item in payload["resolved_items"]}
        )

        for stylist_id in locked_ids:
            Stylist.objects.select_for_update().get(user_id=stylist_id)

        try:
            payload["resolved_items"] = resolve_booking_sequence(
                salon=salon,
                stylist_selections=payload.get("stylist_selections") or [],
                datetime_selections=payload.get("datetime_selections") or {},
            )

            _assert_checkout_slots_still_available(
                salon=salon,
                resolved_items=payload["resolved_items"],
            )

        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("orders:select_dateTime")

        order = Order.objects.create(
            customer=customer,
            salon=salon,
            status="pending",
            is_finally=(payment_method == AppointmentCheckoutForm.PAYMENT_METHOD_SALON),
            is_paid=False,
            selected_payment_method=payment_method,
            requires_online_payment=payload["requires_online_payment"],
            subtotal_amount=payload["subtotal"],
            discount_amount=payload["discount_amount"],
            basket_discount_amount=payload["basket_discount_amount"],
            coupon_discount_amount=payload["coupon_discount_amount"],
            basket_discount_percent=payload["basket_discount_percent"],
            basket_discount_title=payload["basket_discount_title"],
            tax_amount=payload["tax_amount"],
            total_amount=payload["total_amount"],
            coupon_code=coupon_code,
            discount=payload["discount_percent"],
            platform_commission_applies=payload["requires_online_payment"],
            platform_commission_percent=payload["commission_percent"],
            platform_commission_amount=payload["commission_amount"],
            salon_payout_amount=payload["salon_payout_amount"],
            checkout_locked_at=timezone.now(),
            discount_rules_snapshot=payload.get("discount_rules_snapshot", {}),
        )

        try:
            from apps.discounts.services import persist_order_discount_records

            persist_order_discount_records(order=order, payload=payload)
        except Exception:
            logger.exception("Failed to persist discount records | order=%s", order.pk)

        for item in payload["resolved_items"]:
            duration_minutes = int(item.duration_minutes or 0)
            buffer_minutes = int(get_service_buffer_minutes(item.service))

            occupied_until = (
                datetime.combine(
                    item.date_value,
                    item.end_time,
                )
                + timedelta(minutes=buffer_minutes)
            ).time()

            OrderDetail.objects.create(
                order=order,
                service=item.service,
                stylist=item.stylist,
                salon=salon,
                price=int(item.price or 0),
                date=item.date_value,
                time=item.start_time,
                end_time=item.end_time,
                scheduled_duration_minutes=duration_minutes,
                buffer_minutes=buffer_minutes,
                occupied_until=occupied_until,
            )

        if payment_method == AppointmentCheckoutForm.PAYMENT_METHOD_WALLET:
            from apps.payments.models import Payment, Wallet, WalletTransaction
            import secrets
            import uuid

            wallet, _ = Wallet.objects.select_for_update().get_or_create(
                user=request.user
            )
            wallet_balance = int(wallet.balance or 0)

            if wallet_balance < int(payload["total_amount"] or 0):
                logger.warning(
                    "Checkout wallet failed بسبب insufficient balance | customer=%s | order=%s | balance=%s | total=%s",
                    request.user.pk,
                    order.pk,
                    wallet_balance,
                    int(payload.get("total_amount") or 0),
                )
                form.add_error(
                    "payment_method",
                    "موجودی کیف پول برای این رزرو کافی نیست. ابتدا کیف پول را شارژ کنید.",
                )
                order.delete()
                return self._render(request, form=form, coupon_code=coupon_code)

            wallet.withdraw(
                amount=int(payload["total_amount"] or 0),
                description=f"پرداخت رزرو {order.order_number} از کیف پول",
                transaction_type=WalletTransaction.TransactionType.PURCHASE,
                order=order,
            )

            payment = Payment.objects.create(
                order=order,
                customer=customer,
                amount=payload["total_amount"],
                description=f"پرداخت رزرو از کیف پول - سفارش {order.order_number}",
                provider=Payment.Provider.WALLET,
                purpose=Payment.Purpose.APPOINTMENT,
                state=Payment.State.PENDING,
                sandbox_mode=True,
                callback_token=secrets.token_urlsafe(24),
                idempotency_key=uuid.uuid4().hex,
                meta={
                    "source": "wallet",
                    "coupon_code": coupon_code,
                    "commission_percent": payload["commission_percent"],
                    "salon_id": salon.id,
                    "customer_mobile": customer.user.mobile_number,
                },
            )

            payment.mark_success(
                ref_id=f"WALLET-{payment.id}",
                track_id=f"wallet-{payment.id}",
                status_code=100,
                meta={"source": "wallet"},
            )

            order.is_paid = True
            order.is_finally = True
            order.status = "paid"
            order.checkout_locked_at = timezone.now()
            order.save(
                update_fields=["is_paid", "is_finally", "status", "checkout_locked_at"]
            )

            consume_booking_quick_link_from_session(request, order)
            schedule_order_reminder(order)
            notify_manager_and_stylists_for_booking(order, event_type="booking_paid")

            from apps.payments.finance import sync_settlement_for_order

            sync_settlement_for_order(order, payment=payment)

            transaction.on_commit(
                lambda order=order: notify_booking_created(
                    customer=order.customer,
                    order=order,
                )
            )
            transaction.on_commit(
                lambda order=order, payment=payment: notify_payment_success(
                    customer=order.customer,
                    payment=payment,
                    order=order,
                )
            )

            request.session.pop("datetime_selections", None)
            request.session.pop("stylist_selections", None)
            request.session.pop("salon_id", None)
            request.session.modified = True

            logger.info(
                "Checkout wallet success | order=%s | payment=%s | customer=%s | amount=%s",
                order.pk,
                payment.pk,
                customer.pk,
                int(payload.get("total_amount") or 0),
            )

            messages.success(
                request,
                "مبلغ رزرو از کیف پول شما کسر شد و نوبت با موفقیت ثبت شد.",
            )

            redirect_url = reverse(
                "payments:appointment_result",
                kwargs={"payment_id": payment.id, "token": payment.callback_token},
            )
            _store_checkout_submission_result(
                request,
                fingerprint=checkout_fingerprint,
                redirect_url=redirect_url,
            )
            return redirect(redirect_url)

        if payment_method == AppointmentCheckoutForm.PAYMENT_METHOD_SALON:
            request.session.pop("datetime_selections", None)
            request.session.pop("stylist_selections", None)
            request.session.pop("salon_id", None)
            request.session.modified = True

            order.status = "pending"
            order.is_finally = True
            order.save(update_fields=["status", "is_finally"])

            consume_booking_quick_link_from_session(request, order)
            schedule_order_reminder(order)
            notify_manager_and_stylists_for_booking(order, event_type="booking_created")

            from apps.payments.finance import sync_settlement_for_order

            sync_settlement_for_order(order)

            transaction.on_commit(
                lambda order=order: notify_booking_created(
                    customer=order.customer,
                    order=order,
                )
            )

            logger.info(
                "Checkout pay-in-salon success | order=%s | customer=%s | salon=%s",
                order.pk,
                customer.pk,
                salon.pk if salon else None,
            )

            messages.success(
                request,
                "نوبت شما ثبت شد و در انتظار تایید متخصص قرار گرفت. پرداخت این سفارش در مجموعه انجام می‌شود.",
            )

            redirect_url = reverse("orders:appointments")
            _store_checkout_submission_result(
                request,
                fingerprint=checkout_fingerprint,
                redirect_url=redirect_url,
            )
            return redirect(redirect_url)

        from apps.payments.models import Payment
        from apps.payments.gateways import initiate_payment
        import secrets
        import uuid

        gateway_mode = str(getattr(settings, "PAYMENT_MODE", "mock") or "mock").lower()
        gateway_provider = (
            getattr(settings, "PAYMENT_PROVIDER", "zibal") or "zibal"
        ).lower()

        payment = Payment.objects.create(
            order=order,
            customer=customer,
            amount=payload["total_amount"],
            description=f"پرداخت رزرو مجموعه {salon.salon_name} - سفارش {order.order_number}",
            provider=(
                Payment.Provider.MOCK if gateway_mode == "mock" else gateway_provider
            ),
            purpose=Payment.Purpose.APPOINTMENT,
            state=Payment.State.PENDING,
            sandbox_mode=(gateway_mode != "live"),
            callback_token=secrets.token_urlsafe(24),
            idempotency_key=uuid.uuid4().hex,
            meta={
                "coupon_code": coupon_code,
                "commission_percent": payload["commission_percent"],
                "salon_id": salon.id,
                "customer_mobile": customer.user.mobile_number,
            },
        )

        gateway_result = initiate_payment(
            request=request,
            payment=payment,
            amount_toman=payload["total_amount"],
            description=payment.description,
            mobile_number=customer.user.mobile_number,
        )

        if not gateway_result.success or not gateway_result.payment_url:
            payment.mark_failure(
                status_code=gateway_result.code or -2,
                meta={
                    "request": gateway_result.raw or {},
                    "message": gateway_result.message,
                },
            )

            from apps.payments.finance import cancel_order_with_financials

            cancel_order_with_financials(
                order=order,
                reason="شروع پرداخت ناموفق بود",
                refund_reason="شروع ناموفق پرداخت",
                payment=payment,
            )

            cancel_order_reminder(order)

            transaction.on_commit(
                lambda order=order, payment=payment: notify_payment_failed(
                    customer=order.customer,
                    payment=payment,
                    order=order,
                    action_url=reverse(
                        "payments:appointment_result",
                        kwargs={
                            "payment_id": payment.id,
                            "token": payment.callback_token,
                        },
                    ),
                    title="شروع پرداخت ناموفق بود",
                )
            )

            logger.warning(
                "Checkout gateway initiation failed | order=%s | payment=%s | provider=%s | code=%s | message=%s",
                order.pk,
                payment.pk,
                payment.provider,
                gateway_result.code,
                gateway_result.message or "",
            )

            messages.error(request, gateway_result.message or "شروع پرداخت ناموفق بود.")

            redirect_url = reverse(
                "payments:appointment_result",
                kwargs={"payment_id": payment.id, "token": payment.callback_token},
            )

            _store_checkout_submission_result(
                request,
                fingerprint=checkout_fingerprint,
                redirect_url=redirect_url,
            )
            return redirect(redirect_url)

        logger.info(
            "Checkout gateway initiated | order=%s | payment=%s | provider=%s | track_id=%s",
            order.pk,
            payment.pk,
            payment.provider,
            gateway_result.track_id or "",
        )

        payment.gateway_track_id = gateway_result.track_id
        payment.status_code = gateway_result.code or 100
        payment.meta = {**(payment.meta or {}), "request": gateway_result.raw or {}}
        payment.save(update_fields=["gateway_track_id", "status_code", "meta"])

        from apps.payments.finance import sync_settlement_for_order

        sync_settlement_for_order(order, payment=payment)
        consume_booking_quick_link_from_session(request, order)

        _store_checkout_submission_result(
            request,
            fingerprint=checkout_fingerprint,
            redirect_url=gateway_result.payment_url,
            order_id=order.id,
        )
        return redirect(gateway_result.payment_url)
