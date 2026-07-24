from __future__ import annotations

from django.conf import settings
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from .responses import api_success


class ApiV1HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        return api_success(
            {
                "status": "ok",
                "service": "loomera-api",
            }
        )


class ApiV1MetaView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        build_id = str(getattr(settings, "LOOMERA_PUBLIC_BUILD_ID", "") or "").strip()

        data = {
            "application": {
                "name": str(getattr(settings, "BRAND_DISPLAY_NAME", "Loomera")),
                "brand": str(getattr(settings, "BRAND_NAME", "Loomera")),
                "version": str(getattr(settings, "LOOMERA_PUBLIC_APP_VERSION", "beta")),
            },
            "api": {
                "version": str(getattr(settings, "LOOMERA_API_VERSION", "v1")),
                "base_path": "/api/v1/",
            },
            "localization": {
                "default_language": str(getattr(settings, "LANGUAGE_CODE", "fa")),
                "rtl": True,
            },
            "server": {
                "time_utc": timezone.now().isoformat(),
            },
        }

        if build_id:
            data["application"]["build"] = build_id

        return api_success(data)
