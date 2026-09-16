from django.urls import path

from .views import (
    MessagingBaleQuickConnectView,
    MessagingDisconnectView,
    MessagingPreferencesView,
    MessagingPrivacyView,
    MessagingProviderQuickConnectView,
    MessagingStatusView,
)

app_name = "messaging"
urlpatterns = [
    path("", MessagingStatusView.as_view(), name="status"),
    # Keep the existing Bale URL/name behavior exact; the generic route handles Telegram.
    path("connect/bale/", MessagingBaleQuickConnectView.as_view(), name="bale_quick_connect"),
    path(
        "connect/<str:provider_key>/",
        MessagingProviderQuickConnectView.as_view(),
        name="provider_quick_connect",
    ),
    path("preferences/", MessagingPreferencesView.as_view(), name="preferences"),
    path("privacy/", MessagingPrivacyView.as_view(), name="privacy"),
    path("disconnect/<int:identity_id>/", MessagingDisconnectView.as_view(), name="disconnect"),
]
