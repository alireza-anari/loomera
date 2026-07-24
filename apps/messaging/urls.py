from django.urls import path

from .views import MessagingBaleQuickConnectView, MessagingDisconnectView, MessagingPreferencesView, MessagingPrivacyView, MessagingStatusView

app_name = "messaging"

urlpatterns = [
    path("", MessagingStatusView.as_view(), name="status"),
    path("connect/bale/", MessagingBaleQuickConnectView.as_view(), name="bale_quick_connect"),
    path("preferences/", MessagingPreferencesView.as_view(), name="preferences"),
    path("privacy/", MessagingPrivacyView.as_view(), name="privacy"),
    path("disconnect/<int:identity_id>/", MessagingDisconnectView.as_view(), name="disconnect"),
]
