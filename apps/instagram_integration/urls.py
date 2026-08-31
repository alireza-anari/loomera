from django.urls import path

from . import views


app_name = "instagram_integration"

urlpatterns = [
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
