from django.urls import path

from .views import BaleWebhookView

app_name = "bale_bot"

urlpatterns = [
    path("", BaleWebhookView.as_view(), name="webhook"),
]
