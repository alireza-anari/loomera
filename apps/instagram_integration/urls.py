from django.urls import path

from . import views
from .webhook import instagram_webhook


app_name = "instagram_integration"

urlpatterns = [
    path("webhook/", instagram_webhook, name="webhook"),
    path(
        "oauth/start/<str:context_kind>/<int:salon_id>/",
        views.oauth_start,
        name="oauth_start",
    ),
    path(
        "oauth/callback/",
        views.oauth_callback,
        name="oauth_callback",
    ),
    path(
        "disconnect/<str:context_kind>/<int:salon_id>/",
        views.disconnect,
        name="disconnect",
    ),
]
