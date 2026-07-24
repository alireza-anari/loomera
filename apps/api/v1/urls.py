from django.urls import path

from .availability_views import (
    PublicSalonAvailabilityAPIView,
    PublicSalonNextAvailableAPIView,
)
from .public_views import (
    PublicSalonDetailAPIView,
    PublicSalonListAPIView,
    PublicSalonServicesAPIView,
    PublicSalonStylistsAPIView,
    PublicServiceCatalogAPIView,
)
from .views import ApiV1HealthView, ApiV1MetaView
from .auth_views import (
    ApiAuthLogoutAPIView,
    ApiAuthMeAPIView,
    ApiAuthPolicyAPIView,
    ApiAuthStatusAPIView,
    ApiOtpRequestAPIView,
    ApiOtpVerifyAPIView,
)
from .booking_views import (
    ApiBookingConfirmAPIView,
    ApiBookingDraftSummaryAPIView,
    ApiBookingDraftValidateAPIView,
)
from .my_appointments_views import (
    ApiMyAppointmentDetailAPIView,
    ApiMyAppointmentsListAPIView,
)

app_name = "v1"

urlpatterns = [
    path("health/", ApiV1HealthView.as_view(), name="health"),
    path("meta/", ApiV1MetaView.as_view(), name="meta"),
    path("auth/status/", ApiAuthStatusAPIView.as_view(), name="auth_status"),
    path("auth/me/", ApiAuthMeAPIView.as_view(), name="auth_me"),
    path("auth/policy/", ApiAuthPolicyAPIView.as_view(), name="auth_policy"),
    path("auth/otp/request/", ApiOtpRequestAPIView.as_view(), name="auth_otp_request"),
    path("auth/otp/verify/", ApiOtpVerifyAPIView.as_view(), name="auth_otp_verify"),
    path("auth/logout/", ApiAuthLogoutAPIView.as_view(), name="auth_logout"),
    path(
        "bookings/draft/validate/",
        ApiBookingDraftValidateAPIView.as_view(),
        name="booking_draft_validate",
    ),
    path(
        "bookings/draft/summary/",
        ApiBookingDraftSummaryAPIView.as_view(),
        name="booking_draft_summary",
    ),
    path(
        "bookings/confirm/",
        ApiBookingConfirmAPIView.as_view(),
        name="booking_confirm",
    ),
    path(
        "me/appointments/",
        ApiMyAppointmentsListAPIView.as_view(),
        name="my_appointments",
    ),
    path(
        "me/appointments/<int:appointment_id>/",
        ApiMyAppointmentDetailAPIView.as_view(),
        name="my_appointment_detail",
    ),
    path(
        "salons/<str:salon_slug>/availability/",
        PublicSalonAvailabilityAPIView.as_view(),
        name="public_salon_availability",
    ),
    path("salons/", PublicSalonListAPIView.as_view(), name="public_salon_list"),
    path(
        "salons/<str:salon_slug>/next-available/",
        PublicSalonNextAvailableAPIView.as_view(),
        name="public_salon_next_available",
    ),
    path(
        "salons/<str:salon_slug>/",
        PublicSalonDetailAPIView.as_view(),
        name="public_salon_detail",
    ),
    path(
        "salons/<str:salon_slug>/services/",
        PublicSalonServicesAPIView.as_view(),
        name="public_salon_services",
    ),
    path(
        "salons/<str:salon_slug>/stylists/",
        PublicSalonStylistsAPIView.as_view(),
        name="public_salon_stylists",
    ),
    path(
        "services/", PublicServiceCatalogAPIView.as_view(), name="public_service_list"
    ),
]
