from django.urls import path
from .views import (
    # OrderCartView,
    # add_to_order_cart,
    # delete_from_order_cart,
    # show_order_cart,
    # show_update_order_cart,
    # show_update_salon_stylist_order,
    # update_salon_stylist_order,
    # show_update_callendar,
    # update_callendar,
    # status_of_order_cart,
    # CreateOrderView,
    # CheckOutOrderView,
    # ApplyCoupon,
    BookingDateTimeSelectPersian,
    BookingStylistSelectPerService,
    BookingQuickLinkStylistServicesView,
    QuickBookingEntryView,
    ReservationDetailView,
    RebookPastOrderView,
    AppointmentsView,
    AppointmentDetailView,
    ReservationPreview,
    StylistAvailabilityAPI,
    StylistsForServiceAPI,
    CancelAppointmentView,
    AppointmentICSView,
    RescheduleDateTimeView,
    RescheduleConfirmView,
    AppointmentCheckoutView,
    PayInSalonSettlementView,
)

# ------------------------------------------------------------------------------------
app_name = "orders"
urlpatterns = [
    # مسیرهای ثابت باید قبل از مسیر token عمومی باشند؛
    # وگرنه "stylist-services" به عنوان token خوانده می‌شود.
    path(
        "quick-link/stylist-services/",
        BookingQuickLinkStylistServicesView.as_view(),
        name="quick_link_stylist_services",
    ),
    path(
        "quick-link/<str:token>/",
        QuickBookingEntryView.as_view(),
        name="quick_booking_entry",
    ),

    # سازگاری با لینک‌های قدیمی/ fallback که در بعضی بخش‌های ربات ساخته می‌شوند.
    path(
        "quick-booking/<str:token>/",
        QuickBookingEntryView.as_view(),
        name="quick_booking_entry_legacy",
    ),
    # path("order_cart/", OrderCartView.as_view(), name="order_cart"),
    # path("add_to_order_cart/", add_to_order_cart, name="add_to_order_cart"),
    # path("delete_from_order_cart/", delete_from_order_cart, name="delete_from_order_cart"),
    # path("show_order_cart/", show_order_cart, name="show_order_cart"),
    # path("show_update_order_cart/", show_update_order_cart, name="show_update_order_cart"),
    # path(
    #     "show_update_salon_stylist_order/",
    #     show_update_salon_stylist_order,
    #     name="show_update_salon_stylist_order",
    # ),
    # path(
    #     "update_salon_stylist_order/",
    #     update_salon_stylist_order,
    #     name="update_salon_stylist_order",
    # ),
    # path("show_update_callendar/", show_update_callendar, name="show_update_callendar"),
    # path("update_callendar/", update_callendar, name="update_callendar"),
    # path("status_of_order_cart/", status_of_order_cart, name="status_of_order_cart"),
    # path("create_order/", CreateOrderView.as_view(), name="create_order"),
    # path("check_out/<int:order_id>/", CheckOutOrderView.as_view(), name="check_out"),
    # path("apply_coupon/<int:order_id>", ApplyCoupon.as_view(), name="apply_coupon"),
    path(
        "select_stylists/",
        BookingStylistSelectPerService.as_view(),
        name="select_stylists",
    ),
    path(
        "select_dateTime/",
        BookingDateTimeSelectPersian.as_view(),
        name="select_dateTime",
    ),
    path(
        "api/availability/", StylistAvailabilityAPI.as_view(), name="api_availability"
    ),
    path(
        "api/stylists-for-service/",
        StylistsForServiceAPI.as_view(),
        name="api_stylists_for_service",
    ),
    path(
        "rebook/<int:order_id>/",
        RebookPastOrderView.as_view(),
        name="rebook",
    ),
    path(
        "reservation_detail/<int:order_id>/",
        ReservationDetailView.as_view(),
        name="reservation_detail",
    ),
    path(
        "reservation_preview/",
        ReservationPreview.as_view(),
        name="reservation_preview",
    ),
    path("checkout/", AppointmentCheckoutView.as_view(), name="checkout"),
    path(
        "appointments/",
        AppointmentsView.as_view(),
        name="appointments",
    ),
    path(
        "appointments/<int:pk>/",
        AppointmentDetailView.as_view(),
        name="appointment_detail_legacy",
    ),
    path(
        "appointment_detail/<int:pk>/",
        AppointmentDetailView.as_view(),
        name="appointment_detail",
    ),
    path(
        "cancel_appointment/<int:pk>/",
        CancelAppointmentView.as_view(),
        name="cancel_appointment",
    ),
    path(
        "appointment_detail/<int:pk>/pay-in-salon/",
        PayInSalonSettlementView.as_view(),
        name="pay_in_salon_settlement",
    ),
    path(
        "appointment_ics/<int:pk>/",
        AppointmentICSView.as_view(),
        name="appointment_ics",
    ),
    path("reschedule/<int:pk>/", RescheduleDateTimeView.as_view(), name="reschedule"),
    path(
        "reschedule_confirm/",
        RescheduleConfirmView.as_view(),
        name="reschedule_confirm",
    ),
]
