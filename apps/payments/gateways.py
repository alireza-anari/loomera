from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import requests
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)


@dataclass
class GatewayInitResult:
    """Result returned after asking the provider to create a payment session.
    
    ``success=True`` means the initiation request was accepted and a start URL
    can be offered to the customer. It does not mean the payment is settled.
    This value object does not mutate Payment, Order, wallet, or ledger state.
    ``raw`` is diagnostic provider data and is never the source of truth.
    """
    success: bool
    payment_url: str | None = None
    track_id: str | None = None
    code: int | None = None
    message: str = ""
    raw: dict[str, Any] | None = None


@dataclass
class GatewayVerifyResult:
    """Provider verification classification without persistence side effects.
    
    ``success`` is true only after provider success and local integrity checks.
    ``retryable`` means the outcome is inconclusive because of a temporary or
    provider-side failure. ``requires_review`` means identity or integrity data
    conflicts with the locally stored payment. Callers own all Payment, Order,
    wallet, ledger, and notification state transitions.
    """
    success: bool
    retryable: bool = False
    requires_review: bool = False
    ref_id: str | None = None
    track_id: str | None = None
    code: int | None = None
    message: str = ""
    card_number: str | None = None
    integrity_errors: tuple[str, ...] = ()
    raw: dict[str, Any] | None = None


def get_gateway_mode() -> str:
    return str(getattr(settings, "PAYMENT_MODE", "mock") or "mock").strip().lower()


def get_gateway_provider() -> str:
    provider = str(getattr(settings, "PAYMENT_PROVIDER", "zibal") or "zibal").strip().lower()
    return provider or "zibal"


def _is_mock_mode() -> bool:
    return get_gateway_mode() == "mock"


def _is_sandbox_mode() -> bool:
    return get_gateway_mode() == "sandbox"


def _get_zibal_merchant() -> str:
    if _is_sandbox_mode():
        return str(getattr(settings, "ZIBAL_SANDBOX_MERCHANT", "zibal") or "zibal").strip()
    return str(getattr(settings, "ZIBAL_MERCHANT", "") or "").strip()


def _get_timeout() -> int:
    return max(int(getattr(settings, "PAYMENT_TIMEOUT_SECONDS", 15) or 15), 5)

def _safe_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None

    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None

def build_public_url(request, path: str) -> str:
    raw = str(path or "").strip()

    if raw.startswith("http://") or raw.startswith("https://"):
        return raw

    if not raw.startswith("/"):
        raw = f"/{raw}"

    base_url = (
        str(getattr(settings, "PAYMENT_PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    )
    if base_url:
        return f"{base_url}{raw}"

    return request.build_absolute_uri(raw)


def build_wallet_charge_callback_url(request) -> str:
    configured = str(getattr(settings, "PAYMENT_CALLBACK_URL", "") or "").strip()
    if configured:
        return build_public_url(request, configured)
    return build_public_url(request, reverse("payments:charge_verify"))


def build_callback_url(request, payment) -> str:
    if payment.purpose == payment.Purpose.WALLET:
        return build_public_url(
            request,
            reverse(
                "payments:charge_verify",
                kwargs={"payment_id": payment.id, "token": payment.callback_token},
            ),
        )

    return build_public_url(
        request,
        reverse(
            "payments:appointment_verify",
            kwargs={"payment_id": payment.id, "token": payment.callback_token},
        ),
    )


def build_result_url(request, payment) -> str:
    if payment.purpose == payment.Purpose.WALLET:
        return build_public_url(request, reverse("payments:detail"))

    return build_public_url(
        request,
        reverse(
            "payments:appointment_result",
            kwargs={"payment_id": payment.id, "token": payment.callback_token},
        ),
    )


def initiate_payment(*, request, payment, amount_toman: int, description: str, mobile_number: str = "") -> GatewayInitResult:
    """Create a gateway session and return routing metadata.
    
    The amount is received in tomans and sent to Zibal in rials. A successful
    result only authorizes redirecting the customer to the provider; it never
    marks the payment paid or changes Order, wallet, or ledger state. Unsupported
    configuration and transport or response failures return ``success=False``.
    """
    provider = get_gateway_provider()
    if provider != "zibal":
        return GatewayInitResult(success=False, message="ارائه‌دهنده پرداخت پشتیبانی نمی‌شود.")

    if _is_mock_mode():
        payment_url = build_public_url(
            request,
            reverse(
                "payments:mock_gateway",
                kwargs={"payment_id": payment.id, "token": payment.callback_token},
            ),
        )
        return GatewayInitResult(
            success=True,
            payment_url=payment_url,
            track_id=f"mock-{payment.id}",
            code=100,
            message="mock gateway ready",
            raw={"mode": "mock"},
        )

    merchant = _get_zibal_merchant()
    if not merchant:
        return GatewayInitResult(success=False, message="merchant زیبال تنظیم نشده است.")

    amount_rial = int(amount_toman) * 10
    payload = {
        "merchant": merchant,
        "amount": amount_rial,
        "callbackUrl": build_callback_url(request, payment),
        "description": description[:255],
        "orderId": str(payment.order_id or payment.id),
    }
    if mobile_number:
        payload["mobile"] = mobile_number

    try:
        response = requests.post(
            getattr(settings, "ZIBAL_REQUEST_URL", "https://gateway.zibal.ir/v1/request"),
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=_get_timeout(),
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.warning("zibal request failed: %s", exc)
        return GatewayInitResult(success=False, message="اتصال به درگاه پرداخت برقرار نشد.")
    except ValueError:
        return GatewayInitResult(success=False, message="پاسخ درگاه قابل پردازش نبود.")

    if not isinstance(data, dict):
        logger.warning(
            "zibal request returned invalid response structure"
        )
        return GatewayInitResult(
            success=False,
            message="ساختار پاسخ درگاه معتبر نبود.",
        )

    result_code = _safe_int(data.get("result"))

    if result_code is None:
        logger.warning(
            "zibal request returned invalid result code"
        )
        return GatewayInitResult(
            success=False,
            message="کد نتیجه درگاه معتبر نبود.",
            raw=data,
        )

    track_id = data.get("trackId")
    if result_code == 100 and track_id:
        base = str(getattr(settings, "ZIBAL_STARTPAY_BASE_URL", "https://gateway.zibal.ir") or "https://gateway.zibal.ir").rstrip("/")
        return GatewayInitResult(
            success=True,
            payment_url=f"{base}/start/{track_id}",
            track_id=str(track_id),
            code=result_code,
            message=str(data.get("message") or "success"),
            raw=data,
        )

    return GatewayInitResult(
        success=False,
        track_id=str(track_id) if track_id else None,
        code=result_code,
        message=str(data.get("message") or "request failed"),
        raw=data,
    )


def verify_payment(*, payment, track_id: str) -> GatewayVerifyResult:
    """Classify provider verification for an existing Payment without mutating it.
    
    The stored ``gateway_track_id`` is authoritative and the callback track must
    match it before a remote request is made. Provider success is accepted only
    when result code, status, amount, orderId, and refNumber pass local integrity
    checks. ``retryable=True`` means there is no conclusive outcome and callers
    must keep the payment pending. ``requires_review=True`` means an identity or
    integrity mismatch must be preserved for manual review. A definitive decline
    is non-retryable. Callers own transitions, idempotency, wallet and ledger work.
    """
    provider = get_gateway_provider()

    normalized_track_id = str(track_id or "").strip()
    stored_track_id = str(
        getattr(payment, "gateway_track_id", "") or ""
    ).strip()

    payment_id = (
        getattr(payment, "pk", None)
        or getattr(payment, "id", None)
    )

    if provider != "zibal":
        return GatewayVerifyResult(
            success=False,
            retryable=True,
            track_id=normalized_track_id,
            message="ارائه‌دهنده پرداخت پشتیبانی نمی‌شود.",
        )

    if not stored_track_id:
        logger.error(
            "Payment verify blocked: stored track id is missing | "
            "payment=%s",
            payment_id,
        )

        return GatewayVerifyResult(
            success=False,
            requires_review=True,
            track_id=normalized_track_id or None,
            message="شناسه تراکنش ذخیره‌شده معتبر نیست.",
            integrity_errors=("missing_stored_track_id",),
        )

    if normalized_track_id != stored_track_id:
        logger.error(
            "Payment verify blocked: track id mismatch | "
            "payment=%s | stored_track_id=%s | "
            "callback_track_id=%s",
            payment_id,
            stored_track_id,
            normalized_track_id,
        )

        return GatewayVerifyResult(
            success=False,
            requires_review=True,
            track_id=normalized_track_id or None,
            message="اطلاعات تراکنش با پرداخت ثبت‌شده تطبیق ندارد.",
            integrity_errors=("track_id_mismatch",),
            raw={
                "stored_track_id": stored_track_id,
                "callback_track_id": normalized_track_id,
            },
        )

    expected_order_id = str(
        getattr(payment, "order_id", None)
        or getattr(payment, "id", "")
    )

    expected_amount_rial = (
        int(getattr(payment, "amount", 0) or 0) * 10
    )

    if _is_mock_mode():
        mock_action = str(
            ((getattr(payment, "meta", {}) or {}).get(
                "mock_gateway_action",
                "success",
            ))
        ).strip().lower()

        if mock_action == "fail":
            return GatewayVerifyResult(
                success=False,
                retryable=False,
                requires_review=False,
                ref_id=None,
                track_id=stored_track_id,
                code=202,
                message="mock payment failed",
                raw={
                    "mode": "mock",
                    "result": 202,
                    "status": 0,
                    "amount": expected_amount_rial,
                    "orderId": expected_order_id,
                    "mock_action": "fail",
                },
            )

        ref_id = f"MOCK-{payment_id}"

        return GatewayVerifyResult(
            success=True,
            retryable=False,
            requires_review=False,
            ref_id=ref_id,
            track_id=stored_track_id,
            code=100,
            message="mock payment verified",
            raw={
                "mode": "mock",
                "result": 100,
                "status": 1,
                "amount": expected_amount_rial,
                "orderId": expected_order_id,
                "refNumber": ref_id,
                "mock_action": mock_action,
            },
        )
    merchant = _get_zibal_merchant()

    if not merchant:
        return GatewayVerifyResult(
            success=False,
            retryable=True,
            track_id=stored_track_id,
            message="merchant زیبال تنظیم نشده است.",
        )

    payload = {
        "merchant": merchant,
        "trackId": stored_track_id,
    }

    try:
        response = requests.post(
            getattr(
                settings,
                "ZIBAL_VERIFY_URL",
                "https://gateway.zibal.ir/v1/verify",
            ),
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=_get_timeout(),
        )
        response.raise_for_status()
        data = response.json()

    except requests.RequestException as exc:
        logger.warning(
            "zibal verify failed | payment=%s | error=%s",
            payment_id,
            exc,
        )

        return GatewayVerifyResult(
            success=False,
            retryable=True,
            track_id=stored_track_id,
            message="نتیجه قطعی پرداخت از درگاه دریافت نشد.",
        )

    except ValueError:
        logger.warning(
            "zibal verify returned invalid json | payment=%s",
            payment_id,
        )

        return GatewayVerifyResult(
            success=False,
            retryable=True,
            track_id=stored_track_id,
            message="پاسخ تایید درگاه قابل پردازش نبود.",
        )

    if not isinstance(data, dict):
        return GatewayVerifyResult(
            success=False,
            retryable=True,
            track_id=stored_track_id,
            message="ساختار پاسخ تایید درگاه معتبر نبود.",
        )

    result_code = _safe_int(data.get("result"))

    if result_code is None:
        return GatewayVerifyResult(
            success=False,
            retryable=True,
            track_id=stored_track_id,
            message="کد نتیجه تایید درگاه معتبر نبود.",
            raw=data,
        )

    ref_id = (
        data.get("refNumber")
        or data.get("refID")
        or data.get("refId")
    )

    payment_status = _safe_int(data.get("status"))
    verified_amount_rial = _safe_int(data.get("amount"))

    raw_order_id = data.get("orderId")
    verified_order_id = (
        str(raw_order_id).strip()
        if raw_order_id is not None
        else ""
    )

    if result_code not in {100, 201}:
        return GatewayVerifyResult(
            success=False,
            retryable=False,
            ref_id=str(ref_id) if ref_id else None,
            track_id=stored_track_id,
            code=result_code,
            message=str(data.get("message") or ""),
            card_number=data.get("cardNumber"),
            raw=data,
        )

    integrity_errors: list[str] = []

    if payment_status != 1:
        integrity_errors.append(
            "payment_status_not_verified"
        )

    if verified_amount_rial is None:
        integrity_errors.append(
            "missing_verified_amount"
        )
    elif verified_amount_rial != expected_amount_rial:
        integrity_errors.append(
            "amount_mismatch"
        )

    if not verified_order_id:
        integrity_errors.append(
            "missing_order_id"
        )
    elif verified_order_id != expected_order_id:
        integrity_errors.append(
            "order_id_mismatch"
        )

    if not ref_id:
        integrity_errors.append(
            "missing_ref_number"
        )

    if integrity_errors:
        logger.error(
            "zibal verify integrity check failed | "
            "payment=%s | errors=%s",
            payment_id,
            ",".join(integrity_errors),
        )

        return GatewayVerifyResult(
            success=False,
            retryable=False,
            requires_review=True,
            ref_id=str(ref_id) if ref_id else None,
            track_id=stored_track_id,
            code=result_code,
            message=(
                "اطلاعات تاییدشده درگاه با پرداخت "
                "ثبت‌شده تطبیق ندارد."
            ),
            card_number=data.get("cardNumber"),
            integrity_errors=tuple(integrity_errors),
            raw=data,
        )

    return GatewayVerifyResult(
        success=True,
        retryable=False,
        requires_review=False,
        ref_id=str(ref_id),
        track_id=stored_track_id,
        code=result_code,
        message=str(data.get("message") or ""),
        card_number=data.get("cardNumber"),
        raw=data,
    )