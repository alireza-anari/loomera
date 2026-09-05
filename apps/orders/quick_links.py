from __future__ import annotations

from datetime import datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent

from .models import BookingQuickLink, Order
from apps.dashboards.jalali_utils import (
    format_jalali_numeric,
    format_time_fa,
    to_persian_digits,
)

BOOKING_LINK_SALT = "loomera.booking.quick-links.v1"
LEGACY_BOOKING_LINK_SALTS = ("salonify.booking.quick-links.v1",)
MAX_AGE_SECONDS = 60 * 60 * 24 * 30

BOOKING_QUICK_LINK_OPENED_EVENT = "booking_quick_link_opened"
BOOKING_QUICK_LINK_STARTED_EVENT = "booking_quick_link_started"
BOOKING_QUICK_LINK_CONVERTED_EVENT = "booking_quick_link_converted"


def normalize_quick_link_token(token: str) -> str:
    """
    کاربر ممکن است لینک را با slash، query، fragment یا حتی full URL کپی کند.
    این تابع فقط بخش token را برای lookup نگه می‌دارد.

    مسیر جدید:
      /orders/quick-link/<token>/

    مسیر قدیمی/ fallback:
      /orders/quick-booking/<token>/
    """
    value = str(token or "").strip().strip("/")

    if "quick-link/" in value:
        value = value.rsplit("quick-link/", 1)[-1]

    if "quick-booking/" in value:
        value = value.rsplit("quick-booking/", 1)[-1]

    value = value.split("?", 1)[0].split("#", 1)[0]
    return value.strip().strip("/")


def sign_booking_payload(payload: dict) -> str:
    return signing.dumps(payload, salt=BOOKING_LINK_SALT)


def unsign_booking_payload(token: str, *, max_age: int = MAX_AGE_SECONDS) -> dict:
    expired_error = None
    signature_error = None

    for salt in (BOOKING_LINK_SALT, *LEGACY_BOOKING_LINK_SALTS):
        try:
            payload = signing.loads(token, salt=salt, max_age=max_age)
        except signing.SignatureExpired as exc:
            expired_error = exc
        except signing.BadSignature as exc:
            signature_error = exc
        else:
            return normalize_booking_payload(payload)

    if expired_error is not None:
        raise ValidationError(
            "اعتبار این لینک رزرو سریع به پایان رسیده است."
        ) from expired_error
    raise ValidationError(
        "لینک رزرو سریع معتبر نیست یا دست‌کاری شده است."
    ) from signature_error


def normalize_booking_payload(payload: dict) -> dict:
    mode = str(payload.get("mode") or "").strip()
    salon_id = int(payload.get("salon_id") or 0)
    service_ids = [int(item) for item in (payload.get("service_ids") or []) if item]
    stylist_user_id = int(payload.get("stylist_user_id") or 0) or None
    selected_date = str(payload.get("date") or "").strip()
    selected_time = str(payload.get("time") or "").strip()

    if mode not in {
        BookingQuickLink.Mode.SALON,
        BookingQuickLink.Mode.SERVICE,
        BookingQuickLink.Mode.STYLIST,
        BookingQuickLink.Mode.SERVICE_STYLIST,
        BookingQuickLink.Mode.SERVICE_STYLIST_TIME,
    }:
        raise ValidationError("حالت لینک رزرو سریع معتبر نیست.")
    if salon_id <= 0:
        raise ValidationError("سالن این لینک معتبر نیست.")
    if (
        mode in {"service", "service_stylist", "service_stylist_time"}
        and not service_ids
    ):
        raise ValidationError("خدمت انتخاب‌شده در لینک معتبر نیست.")
    if (
        mode in {"stylist", "service_stylist", "service_stylist_time"}
        and not stylist_user_id
    ):
        raise ValidationError("متخصص انتخاب‌شده در لینک معتبر نیست.")
    if mode == "service_stylist_time":
        if not (selected_date and selected_time):
            raise ValidationError("زمان لینک رزرو سریع ناقص است.")
        try:
            datetime.strptime(selected_date, "%Y-%m-%d")
            datetime.strptime(selected_time, "%H:%M")
        except ValueError as exc:
            raise ValidationError(
                "فرمت تاریخ یا ساعت لینک رزرو سریع معتبر نیست."
            ) from exc

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}

    return {
        "mode": mode,
        "salon_id": salon_id,
        "service_ids": service_ids,
        "stylist_user_id": stylist_user_id,
        "date": selected_date,
        "time": selected_time,
        "summary": summary,
    }


def build_quick_link_url(request, quick_link: BookingQuickLink) -> str:
    path = reverse(
        "orders:quick_booking_entry", kwargs={"token": str(quick_link.token)}
    )
    return request.build_absolute_uri(path)


def create_booking_quick_link(
    *,
    request,
    creator,
    salon,
    payload,
    service_obj=None,
    stylist_obj=None,
    title="",
    is_permanent=False,
    placement=BookingQuickLink.Placement.OTHER,
    campaign_name="",
    internal_note="",
):
    payload = normalize_booking_payload(payload)

    placement = str(
        placement
        or BookingQuickLink.Placement.OTHER
    ).strip()

    valid_placements = {
        value
        for value, _label
        in BookingQuickLink.Placement.choices
    }

    if placement not in valid_placements:
        raise ValidationError(
            "محل استفاده انتخاب‌شده برای لینک معتبر نیست."
        )

    campaign_name = str(
        campaign_name or ""
    ).strip()

    internal_note = str(
        internal_note or ""
    ).strip()

    campaign_field = (
        BookingQuickLink._meta.get_field(
            "campaign_name"
        )
    )

    note_field = (
        BookingQuickLink._meta.get_field(
            "internal_note"
        )
    )

    if (
        campaign_field.max_length
        and len(campaign_name)
        > campaign_field.max_length
    ):
        raise ValidationError(
            "نام کمپین از طول مجاز بیشتر است."
        )

    if (
        note_field.max_length
        and len(internal_note)
        > note_field.max_length
    ):
        raise ValidationError(
            "یادداشت داخلی از طول مجاز بیشتر است."
        )
    expires_at = (
        None if is_permanent else timezone.now() + timedelta(seconds=MAX_AGE_SECONDS)
    )

    quick_link = BookingQuickLink.objects.create(
        creator=creator,
        salon=salon,
        service=service_obj,
        stylist=stylist_obj,
        mode=payload["mode"],
        payload=payload,
        title=(title or "").strip(),
        placement=placement,
        campaign_name=campaign_name,
        internal_note=internal_note,
        is_permanent=bool(is_permanent),
        expires_at=expires_at,
    )

    return quick_link, build_quick_link_url(request, quick_link)


def _format_quick_link_datetime(value):
    if not value:
        return "—"

    try:
        local_value = timezone.localtime(value)
        return f"{format_jalali_numeric(local_value.date())}، {format_time_fa(local_value.time())}"
    except Exception:
        return to_persian_digits(str(value))


def _format_quick_link_date(value):
    if not value:
        return "—"

    try:
        if hasattr(value, "date") and callable(value.date):
            value = value.date()

        if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
            return format_jalali_numeric(value)

        parsed = datetime.strptime(str(value), "%Y-%m-%d").date()
        return format_jalali_numeric(parsed)
    except Exception:
        return to_persian_digits(str(value))


def _format_quick_link_time(value):
    if not value:
        return "—"

    try:
        return format_time_fa(value)
    except Exception:
        return to_persian_digits(str(value))


def _serialize_link_for_dashboard(request, quick_link: BookingQuickLink) -> dict:
    summary = quick_link.payload.get("summary") or {}

    # Surface the Production QR/print endpoints through the lightweight dashboard
    # serializer used by the refactored manager/stylist cards. Permission checks
    # remain in the dedicated Production views.
    manager_user_id = getattr(
        getattr(getattr(quick_link.salon, "salon_manager", None), "user", None),
        "id",
        None,
    )
    if manager_user_id == getattr(request.user, "id", None):
        qr_url = reverse(
            "dashboards:quick_link_qr_download", kwargs={"link_id": quick_link.pk}
        )
        print_url = reverse(
            "dashboards:quick_link_print_templates", kwargs={"link_id": quick_link.pk}
        )
    else:
        qr_url = reverse(
            "dashboards:stylist_quick_link_qr_download",
            kwargs={"link_id": quick_link.pk},
        )
        print_url = reverse(
            "dashboards:stylist_quick_link_print_templates",
            kwargs={"link_id": quick_link.pk},
        )
    payload_date = quick_link.payload.get("date") or ""
    payload_time = quick_link.payload.get("time") or ""

    date_label = summary.get("date") or _format_quick_link_date(payload_date)
    time_label = summary.get("time") or _format_quick_link_time(payload_time)

    return {
        "id": quick_link.id,
        "title": quick_link.title or quick_link.get_mode_display(),
        "mode": quick_link.mode,
        "mode_label": quick_link.get_mode_display(),
        "url": build_quick_link_url(request, quick_link),
        "qr_url": qr_url,
        "print_url": print_url,
        "status_label": quick_link.status_label,
        "status_tone": quick_link.status_tone,
        "is_active": quick_link.is_active,
        "is_permanent": quick_link.is_permanent,
        "bookings_count": quick_link.bookings_count,
        "service_name": summary.get("service")
        or getattr(quick_link.service, "service_name", "—"),
        "stylist_name": summary.get("stylist")
        or (quick_link.stylist.get_fullName() if quick_link.stylist else "—"),
        "date_label": date_label,
        "time_label": time_label,
        "created_at_label": _format_quick_link_datetime(quick_link.created_at),
        "expires_at_label": (
            _format_quick_link_datetime(quick_link.expires_at)
            if quick_link.expires_at
            else "دائمی"
        ),
        "last_opened_at_label": (
            _format_quick_link_datetime(quick_link.last_opened_at)
            if quick_link.last_opened_at
            else "هنوز باز نشده"
        ),
    }

def list_booking_quick_links_for_dashboard(
    *, request, salon, creator=None, stylist=None, limit=30
):
    qs = (
        BookingQuickLink.objects.select_related(
            "service", "stylist__user", "salon__salon_manager__user", "creator"
        )
        .filter(salon=salon)
        .order_by("-created_at")
    )

    if creator is not None:
        qs = qs.filter(creator=creator)

    if stylist is not None:
        qs = qs.filter(stylist=stylist)

    return [_serialize_link_for_dashboard(request, item) for item in qs[:limit]]


def update_booking_quick_link_status(
    *,
    salon,
    creator,
    link_id,
    action,
    stylist=None,
):
    queryset = BookingQuickLink.objects.filter(
        salon=salon,
        creator=creator,
    )

    if stylist is not None:
        queryset = queryset.filter(stylist=stylist)

    from .quick_link_management import (
        change_booking_quick_link_status,
    )

    _quick_link, message = change_booking_quick_link_status(
        links_queryset=queryset,
        link_id=link_id,
        action=action,
    )

    return message



def resolve_booking_quick_link_token(token: str):
    """
    خروجی:
      (quick_link, payload)

    برای لینک‌های جدید quick_link مقدار دارد.
    برای لینک‌های قدیمی signed، quick_link برابر None است.
    """
    token = normalize_quick_link_token(token)

    try:
        quick_link = BookingQuickLink.objects.select_related(
            "salon", "service", "stylist__user"
        ).get(token=token)
    except (BookingQuickLink.DoesNotExist, ValueError, ValidationError):
        return None, unsign_booking_payload(token)

    if not quick_link.can_open:
        raise ValidationError(
            f"این لینک رزرو سریع {quick_link.status_label} است و دیگر قابل استفاده نیست."
        )

    return quick_link, normalize_booking_payload(quick_link.payload)


def _ensure_request_session_key(request) -> str:
    """
    برای Attribution ناشناس باید پیش از ثبت رویداد Session واقعی وجود داشته باشد.
    """
    session = getattr(request, "session", None)

    if session is None:
        raise ValidationError(
            "نشست کاربر برای ثبت بازدید لینک در دسترس نیست."
        )

    session_key = str(session.session_key or "").strip()

    if not session_key:
        session.create()
        session_key = str(session.session_key or "").strip()

    if not session_key:
        raise ValidationError(
            "ایجاد نشست معتبر برای لینک رزرو ممکن نشد."
        )

    return session_key


@transaction.atomic
def record_booking_quick_link_opened(*, request, quick_link):
    """
    هر بازشدن معتبر را ثبت و opens_count را اتمیک افزایش می‌دهد.

    بازدید یکتا از تعداد session_keyهای متمایز همین رویداد محاسبه می‌شود.
    """
    if not quick_link or not getattr(quick_link, "pk", None):
        raise ValidationError("لینک رزرو برای ثبت بازدید معتبر نیست.")

    session_key = _ensure_request_session_key(request)

    locked_link = BookingQuickLink.objects.select_for_update().get(
        pk=quick_link.pk
    )

    if not locked_link.can_open:
        raise ValidationError(
            f"این لینک رزرو سریع {locked_link.status_label} است "
            "و دیگر قابل استفاده نیست."
        )

    opened_at = timezone.now()
    actor = getattr(request, "user", None)

    if not getattr(actor, "is_authenticated", False):
        actor = None

    forwarded_for = str(
        request.META.get("HTTP_X_FORWARDED_FOR", "")
    ).split(",", 1)[0].strip()

    remote_address = str(
        request.META.get("REMOTE_ADDR", "")
    ).strip()

    ip_address = forwarded_for or remote_address or None

    AnalyticsEvent.objects.create(
        category="appointment",
        event_type=BOOKING_QUICK_LINK_OPENED_EVENT,
        occurred_at=opened_at,
        actor=actor,
        salon=locked_link.salon,
        stylist=locked_link.stylist,
        target_content_type=ContentType.objects.get_for_model(
            BookingQuickLink,
            for_concrete_model=False,
        ),
        target_object_id=locked_link.pk,
        session_key=session_key,
        source=locked_link.placement or "",
        metadata={
            "quick_link_id": locked_link.pk,
            "mode": locked_link.mode,
            "placement": locked_link.placement or "",
            "campaign_name": locked_link.campaign_name or "",
            "is_permanent": bool(locked_link.is_permanent),
        },
        ip_address=ip_address,
        user_agent=str(
            request.META.get("HTTP_USER_AGENT", "")
        )[:1000],
    )

    BookingQuickLink.objects.filter(pk=locked_link.pk).update(
        opens_count=F("opens_count") + 1,
        last_opened_at=opened_at,
        updated_at=opened_at,
    )

    quick_link.opens_count = int(locked_link.opens_count or 0) + 1
    quick_link.last_opened_at = opened_at

    return opened_at


def count_booking_quick_link_unique_visitors(quick_link) -> int:
    """
    تعداد Sessionهای متمایزی که لینک را باز کرده‌اند.
    """
    if not quick_link or not getattr(quick_link, "pk", None):
        return 0

    content_type = ContentType.objects.get_for_model(
        BookingQuickLink,
        for_concrete_model=False,
    )

    return (
        AnalyticsEvent.objects.filter(
            event_type=BOOKING_QUICK_LINK_OPENED_EVENT,
            target_content_type=content_type,
            target_object_id=quick_link.pk,
        )
        .exclude(session_key="")
        .values("session_key")
        .distinct()
        .count()
    )


@transaction.atomic
def record_booking_quick_link_started(*, request):
    """
    اولین اقدام واقعی یک Session در مسیر یک لینک رزرو را ثبت می‌کند.

    قفل روی خود BookingQuickLink باعث می‌شود دو درخواست هم‌زمان
    برای یک لینک و Session رویداد تکراری نسازند.
    """
    session = getattr(request, "session", None)

    if session is None:
        return None

    link_id = session.get("booking_quick_link_id")

    if not link_id:
        return None

    session_key = _ensure_request_session_key(request)

    try:
        quick_link = BookingQuickLink.objects.select_for_update().get(
            pk=link_id
        )
    except (BookingQuickLink.DoesNotExist, TypeError, ValueError):
        session.pop("booking_quick_link_id", None)
        session.modified = True
        return None

    if not quick_link.can_open:
        session.pop("booking_quick_link_id", None)
        session.modified = True
        return None

    content_type = ContentType.objects.get_for_model(
        BookingQuickLink,
        for_concrete_model=False,
    )

    existing_event = AnalyticsEvent.objects.filter(
        event_type=BOOKING_QUICK_LINK_STARTED_EVENT,
        target_content_type=content_type,
        target_object_id=quick_link.pk,
        session_key=session_key,
    ).first()

    if existing_event:
        return existing_event

    actor = getattr(request, "user", None)

    if not getattr(actor, "is_authenticated", False):
        actor = None

    forwarded_for = str(
        request.META.get("HTTP_X_FORWARDED_FOR", "")
    ).split(",", 1)[0].strip()

    remote_address = str(
        request.META.get("REMOTE_ADDR", "")
    ).strip()

    event = AnalyticsEvent.objects.create(
        category="appointment",
        event_type=BOOKING_QUICK_LINK_STARTED_EVENT,
        occurred_at=timezone.now(),
        actor=actor,
        salon=quick_link.salon,
        stylist=quick_link.stylist,
        target_content_type=content_type,
        target_object_id=quick_link.pk,
        session_key=session_key,
        source=quick_link.placement or "",
        metadata={
            "quick_link_id": quick_link.pk,
            "mode": quick_link.mode,
            "placement": quick_link.placement or "",
            "campaign_name": quick_link.campaign_name or "",
            "is_permanent": bool(quick_link.is_permanent),
        },
        ip_address=forwarded_for or remote_address or None,
        user_agent=str(
            request.META.get("HTTP_USER_AGENT", "")
        )[:1000],
    )

    return event


def _booking_quick_link_matches_order(*, quick_link, order) -> bool:
    if not order or not getattr(order, "pk", None):
        return False

    if not order.salon_id or quick_link.salon_id != order.salon_id:
        return False

    try:
        payload = normalize_booking_payload(quick_link.payload or {})
    except (TypeError, ValueError, ValidationError):
        return False

    if int(payload["salon_id"]) != int(order.salon_id):
        return False

    required_service_ids = {
        int(service_id)
        for service_id in payload.get("service_ids") or []
        if service_id
    }
    required_stylist_id = payload.get("stylist_user_id")

    if (
        quick_link.service_id
        and required_service_ids
        and quick_link.service_id not in required_service_ids
    ):
        return False

    if (
        quick_link.stylist_id
        and required_stylist_id
        and int(quick_link.stylist_id) != int(required_stylist_id)
    ):
        return False

    details = list(
        order.order_details1.only(
            "service_id",
            "stylist_id",
            "date",
            "time",
        )
    )

    if not details:
        return False

    order_service_ids = {
        int(detail.service_id)
        for detail in details
        if detail.service_id
    }
    order_stylist_ids = {
        int(detail.stylist_id)
        for detail in details
        if detail.stylist_id
    }

    mode = payload["mode"]

    if mode == BookingQuickLink.Mode.SALON:
        return True

    if mode == BookingQuickLink.Mode.SERVICE:
        return bool(
            required_service_ids
            and required_service_ids.issubset(order_service_ids)
        )

    if mode == BookingQuickLink.Mode.STYLIST:
        return bool(
            required_stylist_id
            and int(required_stylist_id) in order_stylist_ids
        )

    matching_details = [
        detail
        for detail in details
        if detail.service_id in required_service_ids
        and detail.stylist_id == required_stylist_id
    ]

    if not matching_details:
        return False

    if mode == BookingQuickLink.Mode.SERVICE_STYLIST:
        return True

    if mode == BookingQuickLink.Mode.SERVICE_STYLIST_TIME:
        required_date = payload.get("date") or ""
        required_time = payload.get("time") or ""

        return any(
            detail.date
            and detail.time
            and detail.date.isoformat() == required_date
            and detail.time.strftime("%H:%M") == required_time
            for detail in matching_details
        )

    return False


@transaction.atomic
def consume_booking_quick_link_from_session(request, order):
    """
    لینک Session را فقط به Order منتسب می‌کند.

    ثبت Conversion در این تابع انجام نمی‌شود، چون در پرداخت آنلاین
    ساخت Order یا انتقال به درگاه به معنی رزرو موفق نیست.
    """
    link_id = request.session.pop("booking_quick_link_id", None)
    request.session.modified = True

    if not link_id or not order or not getattr(order, "pk", None):
        return None

    try:
        quick_link = BookingQuickLink.objects.select_related(
            "salon",
            "service",
            "stylist",
        ).get(pk=link_id)
    except (BookingQuickLink.DoesNotExist, TypeError, ValueError):
        return None

    # Only the Order row is locked. Joining the nullable
    # booking_quick_link relation here would make PostgreSQL reject
    # FOR UPDATE on the nullable side of an outer join.
    locked_order = Order.objects.select_for_update().get(pk=order.pk)

    if (
        locked_order.booking_quick_link_id
        and locked_order.booking_quick_link_id != quick_link.pk
    ):
        return None

    if not _booking_quick_link_matches_order(
        quick_link=quick_link,
        order=locked_order,
    ):
        return None

    if locked_order.booking_quick_link_id is None:
        locked_order.booking_quick_link = quick_link
        locked_order.save(update_fields=["booking_quick_link"])

    order.booking_quick_link_id = quick_link.pk
    order.booking_quick_link = quick_link

    return quick_link


@transaction.atomic
def mark_booking_quick_link_converted(order):
    """
    یک Conversion موفق را دقیقاً یک بار برای هر Order ثبت می‌کند.

    قفل Order باعث می‌شود Callback تکراری یا Workerهای هم‌زمان نتوانند
    شمارنده یک Order را بیش از یک بار افزایش دهند.
    """
    if not order or not getattr(order, "pk", None):
        return None

    # Lock only the Order row. Nullable related objects must not be
    # included in a FOR UPDATE outer join on PostgreSQL.
    locked_order = Order.objects.select_for_update().get(pk=order.pk)

    if not locked_order.booking_quick_link_id:
        return None

    if not locked_order.is_finally or locked_order.status == "cancelled":
        return None

    quick_link = BookingQuickLink.objects.select_for_update().get(
        pk=locked_order.booking_quick_link_id
    )

    if (
        not quick_link.is_permanent
        and quick_link.used_order_id
        and quick_link.used_order_id != locked_order.pk
    ):
        Order.objects.filter(
            pk=locked_order.pk,
            booking_quick_link_id=quick_link.pk,
        ).update(booking_quick_link=None)

        locked_order.booking_quick_link_id = None
        order.booking_quick_link_id = None
        return None

    content_type = ContentType.objects.get_for_model(
        BookingQuickLink,
        for_concrete_model=False,
    )

    existing_event = AnalyticsEvent.objects.filter(
        event_type=BOOKING_QUICK_LINK_CONVERTED_EVENT,
        order=locked_order,
        target_content_type=content_type,
        target_object_id=quick_link.pk,
    ).first()

    if existing_event:
        return quick_link

    converted_at = timezone.now()
    actor = getattr(
        getattr(locked_order.customer, "user", None),
        "pk",
        None,
    )

    AnalyticsEvent.objects.create(
        category="appointment",
        event_type=BOOKING_QUICK_LINK_CONVERTED_EVENT,
        occurred_at=converted_at,
        actor_id=actor,
        salon=locked_order.salon,
        order=locked_order,
        target_content_type=content_type,
        target_object_id=quick_link.pk,
        source=quick_link.placement or "",
        metadata={
            "quick_link_id": quick_link.pk,
            "mode": quick_link.mode,
            "placement": quick_link.placement or "",
            "campaign_name": quick_link.campaign_name or "",
            "is_permanent": bool(quick_link.is_permanent),
        },
    )

    update_values = {
        "bookings_count": F("bookings_count") + 1,
        "last_converted_at": converted_at,
        "used_order_id": locked_order.pk,
        "updated_at": converted_at,
    }

    if not quick_link.is_permanent:
        update_values.update(
            {
                "used_at": converted_at,
                "is_active": False,
                "disabled_at": converted_at,
            }
        )

    BookingQuickLink.objects.filter(pk=quick_link.pk).update(
        **update_values
    )

    quick_link.refresh_from_db()
    return quick_link
