from django.urls import path

from .views import (
    NotificationCenterView,
    mark_notification_read,
    mark_notifications_read_all,
    notifications_summary,
)

app_name = "notifications"

urlpatterns = [
    path("", NotificationCenterView.as_view(), name="center"),
    path("api/summary/", notifications_summary, name="summary"),
    path("api/<int:recipient_id>/read/", mark_notification_read, name="read"),
    path("api/read-all/", mark_notifications_read_all, name="read_all"),
]
