from __future__ import annotations

from typing import Any

from django.conf import settings
from rest_framework.response import Response

from apps.main.ui_feedback import user_ui_message


def api_version() -> str:
    return str(getattr(settings, "LOOMERA_API_VERSION", "v1") or "v1")


def api_success(
    data: dict[str, Any] | list[Any] | None = None,
    *,
    status: int = 200,
    meta: dict[str, Any] | None = None,
) -> Response:
    response_meta = {
        "api_version": api_version(),
    }
    if meta:
        response_meta.update(meta)

    return Response(
        {
            "ok": True,
            "data": data if data is not None else {},
            "meta": response_meta,
        },
        status=status,
    )


def api_error(
    code: str,
    message: str,
    *,
    status: int = 400,
    details: dict[str, Any] | None = None,
) -> Response:
    payload: dict[str, Any] = {
        "ok": False,
        "error": {
            "code": code,
            "message": user_ui_message(message, "درخواست انجام نشد. لطفاً اطلاعات ارسالی را بررسی کنید."),
        },
        "meta": {
            "api_version": api_version(),
        },
    }
    if details:
        payload["error"]["details"] = details

    return Response(payload, status=status)
