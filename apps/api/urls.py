from django.urls import include, path

app_name = "api"

urlpatterns = [
    path("v1/", include(("apps.api.v1.urls", "v1"), namespace="v1")),
]
