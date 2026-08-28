from django.urls import path

from . import action_views, views

app_name = "help_center"
urlpatterns = [
    path("", views.help_home, name="home"),
    path("search/", views.help_search, name="search"),
    path("category/<slug:slug>/", views.help_category, name="category"),
    path("article/<slug:slug>/", views.help_article, name="article"),
    path("legal/", views.legal_index, name="legal_index"),
    path("legal/<slug:slug>/", views.legal_detail, name="legal_detail"),
    path("api/context/", views.context_api, name="context_api"),
    path("api/chat/", views.chat_api, name="chat_api"),
    path("api/conversation/", views.conversation_api, name="conversation_api"),
    path("api/feedback/", views.feedback_api, name="feedback_api"),
    path("api/support-handoff/", views.support_handoff_api, name="support_handoff_api"),
    path(
        "api/actions/customer-discovery/",
        action_views.customer_discovery_api,
        name="customer_discovery_api",
    ),
    path(
        "api/actions/customer-booking/",
        action_views.customer_booking_api,
        name="customer_booking_api",
    ),
]
