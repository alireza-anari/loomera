from __future__ import annotations

from django.contrib.auth import get_user
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.orders.models import OrderDetail

from .public_views import _clean_limit, _clean_offset, _query_string_too_large
from .responses import api_error, api_success


def _django_request(request):
    return getattr(request, "_request", request)


def _django_session_user(request):
    django_request = _django_request(request)
    user = get_user(django_request)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


def _customer_from_request(request):
    user = _django_session_user(request)
    if user is None:
        return None, api_error(
            "authentication_required",
            "برای مشاهده رزروها باید وارد حساب کاربری شوید.",
            status=401,
        )

    customer = getattr(user, "customer_profile", None)
    if customer is None:
        return None, api_error(
            "customer_profile_required",
            "فقط کاربر مشتری می‌تواند رزروهای خودش را مشاهده کند.",
            status=403,
        )

    return customer, None


def _safe_time_value(value):
    if not value:
        return None
    return value.strftime("%H:%M")


def _safe_date_value(value):
    if not value:
        return None
    return value.isoformat()


def _serialize_my_appointment(appointment, *, detail: bool = False):
    order = appointment.order
    salon = appointment.salon
    service = appointment.service
    stylist = appointment.stylist

    payload = {
        "id": appointment.pk,
        "order": {
            "id": order.pk,
            "number": getattr(order, "order_number", "") or "",
            "status": order.status,
            "is_paid": bool(order.is_paid),
            "selected_payment_method": order.selected_payment_method,
            "total_amount": int(order.total_amount or 0),
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
        },
        "stylist": {
            "id": stylist.pk,
            "display_name": stylist.professional_display_name,
            "expert": stylist.expert or "",
        },
        "slot": {
            "date": _safe_date_value(appointment.date),
            "start_time": _safe_time_value(appointment.time),
            "end_time": _safe_time_value(appointment.end_time),
            "occupied_until": _safe_time_value(
                appointment.occupied_until or appointment.end_time
            ),
        },
        "status": {
            "confirmation_status": appointment.confirmation_status,
            "lifecycle_status": appointment.lifecycle_status,
            "order_status": order.status,
        },
        "price": {
            "amount": int(appointment.price or 0),
            "currency": "IRR",
        },
        "payment": {
            "mode": order.selected_payment_method,
            "amount_due_now": 0,
            "amount_payable_at_salon": int(order.total_amount or 0),
            "is_paid": bool(order.is_paid),
        },
    }

    if detail:
        payload["meta"] = {
            "can_cancel": False,
            "can_reschedule": False,
            "cancel_endpoint": None,
            "reschedule_endpoint": None,
        }

    return payload


def _my_appointments_queryset(customer):
    return (
        OrderDetail.objects.filter(order__customer=customer)
        .select_related(
            "order",
            "salon",
            "service",
            "stylist",
            "stylist__user",
        )
        .order_by("-date", "-time", "-pk")
    )


class ApiMyAppointmentsListAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        if _query_string_too_large(request):
            return api_error(
                "query_too_large",
                "حجم فیلترهای API بیش از حد مجاز است.",
                status=400,
            )

        customer, error_response = _customer_from_request(request)
        if error_response is not None:
            return error_response

        limit = _clean_limit(request, default=20)
        offset = _clean_offset(request)

        queryset = _my_appointments_queryset(customer)
        total_count = queryset.count()
        appointments = list(queryset[offset : offset + limit])

        return api_success(
            {
                "results": [
                    _serialize_my_appointment(appointment)
                    for appointment in appointments
                ],
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "count": len(appointments),
                    "total_count": total_count,
                    "has_next": offset + limit < total_count,
                },
            }
        )


class ApiMyAppointmentDetailAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, appointment_id: int, *args, **kwargs):
        customer, error_response = _customer_from_request(request)
        if error_response is not None:
            return error_response

        appointment = (
            _my_appointments_queryset(customer).filter(pk=appointment_id).first()
        )
        if appointment is None:
            return api_error(
                "appointment_not_found",
                "رزرو پیدا نشد.",
                status=404,
            )

        return api_success(
            {
                "appointment": _serialize_my_appointment(appointment, detail=True),
            }
        )
