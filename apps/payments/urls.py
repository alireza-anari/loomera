from django.urls import path

from .views import (
    WalletDetailView,
    WalletChargeView,
    WalletChargeVerifyView,
    WalletTransactionsView,
    WalletWithdrawView,
    WalletWithdrawalCancelView,
    MockGatewayView,
    MockGatewayCompleteView,
    AppointmentPaymentVerifyView,
    AppointmentPaymentResultView,
)
# ---------------------------------------------------------------------------------
app_name = "payments"
urlpatterns = [
    # نمایش کیف پول
    path("", WalletDetailView.as_view(), name="detail"),
    # شارژ کیف پول
    path("charge/", WalletChargeView.as_view(), name="charge"),
    # تایید پرداخت شارژ
    path(
        "charge/verify/<int:payment_id>/<str:token>/",
        WalletChargeVerifyView.as_view(),
        name="charge_verify",
    ),
    # تاریخچه کامل تراکنش‌ها
    path("transactions/", WalletTransactionsView.as_view(), name="transactions"),
    path("withdraw/", WalletWithdrawView.as_view(), name="withdraw"),
    path(
        "withdraw/<int:request_id>/cancel/",
        WalletWithdrawalCancelView.as_view(),
        name="withdraw_cancel",
    ),
    path(
        "appointment/mock/<int:payment_id>/<str:token>/",
        MockGatewayView.as_view(),
        name="mock_gateway",
    ),
    path(
        "appointment/mock/<int:payment_id>/<str:token>/complete/",
        MockGatewayCompleteView.as_view(),
        name="mock_gateway_complete",
    ),
    path(
        "appointment/verify/<int:payment_id>/<str:token>/",
        AppointmentPaymentVerifyView.as_view(),
        name="appointment_verify",
    ),
    path(
        "appointment/result/<int:payment_id>/<str:token>/",
        AppointmentPaymentResultView.as_view(),
        name="appointment_result",
    ),
]
