from django.urls import path

from . import views

app_name = "platform_admin"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("salons/", views.SalonListView.as_view(), name="salons"),
    path("salons/<int:pk>/", views.SalonDetailView.as_view(), name="salon_detail"),
    path("salons/<int:pk>/verification/", views.SalonVerificationActionView.as_view(), name="salon_verification_action"),
    path("users/", views.UserListView.as_view(), name="users"),
    path("users/<int:pk>/", views.UserDetailView.as_view(), name="user_detail"),
    path("users/<int:pk>/suspend/", views.UserSuspendActionView.as_view(), name="user_suspend"),
    path("appointments/", views.AppointmentListView.as_view(), name="appointments"),
    path("content/reports/", views.ContentReportListView.as_view(), name="content_reports"),
    path("content/reports/<int:pk>/action/", views.ContentReportActionView.as_view(), name="content_report_action"),
    path("finance/", views.FinanceOverviewView.as_view(), name="finance"),
    path("notifications/", views.NotificationMonitorView.as_view(), name="notifications"),
    path("support/", views.SupportQueueView.as_view(), name="support"),
    path("support/<int:pk>/", views.SupportDetailView.as_view(), name="support_detail"),
    path("support/<int:pk>/status/", views.SupportStatusActionView.as_view(), name="support_status_action"),
    path("disputes/", views.DisputeListView.as_view(), name="disputes"),
    path("disputes/<int:pk>/", views.DisputeDetailView.as_view(), name="dispute_detail"),
    path("disputes/<int:pk>/action/", views.DisputeActionView.as_view(), name="dispute_action"),
    path("analytics/", views.AnalyticsOverviewView.as_view(), name="analytics"),
    path("analytics/export/", views.AnalyticsExportCreateView.as_view(), name="analytics_export"),
    path("infrastructure/", views.InfrastructureOverviewView.as_view(), name="infrastructure"),
    path("settings/", views.PlatformSettingListView.as_view(), name="settings"),
    path("settings/<int:pk>/edit/", views.PlatformSettingUpdateView.as_view(), name="setting_edit"),
    path("audit/", views.AuditLogListView.as_view(), name="audit"),
]
