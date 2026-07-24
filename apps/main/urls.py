from django.urls import path
from .views import HealthCheckView, RobotsTxtView, SupportTicketCloseView, SupportTicketDetailView, SupportTicketListView, SupportTicketReplyView, SupportView, success_view

# ------------------------------------------------------------------------------
app_name = "main"
urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health"),
    path("robots.txt", RobotsTxtView.as_view(), name="robots_txt"),
    # path("", IndexPage.as_view(), name="index"),
    path("contact/", SupportView.as_view(), name="contact"),
    path("support/tickets/", SupportTicketListView.as_view(), name="support_ticket_list"),
    path("support/tickets/<int:pk>/", SupportTicketDetailView.as_view(), name="support_ticket_detail"),
    path("support/tickets/<int:pk>/reply/", SupportTicketReplyView.as_view(), name="support_ticket_reply"),
    path("support/tickets/<int:pk>/close/", SupportTicketCloseView.as_view(), name="support_ticket_close"),
    path("success/", success_view, name="success"),
]
