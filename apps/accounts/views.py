from django.urls import reverse
import os
from PIL import Image, UnidentifiedImageError
from django.core.exceptions import PermissionDenied, ValidationError
import utils
import json
import logging
import math
import time
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Avg, Sum, F, Q, Value, Case, When, IntegerField
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.comments_scores_favories.models import Comments, Scoring
from apps.orders.models import Order, OrderDetail
from apps.salons.models import CustomerNote, Salon

from .forms import (
    AddCustomerForm,
    ChangePasswordForm,
    CustomerAddressForm,
    CustomerSignupForm,
    SpecialistSignupForm,
    CustomerUpdateProfileForm,
    DeleteAccountReasonForm,
    LoginUserForm,
    RegisterUserForm,
    RememberPasswordForm,
    StylistSignupForm,
    VerifyRegisterForm,
    validate_customer_profile_image_upload,
)
from .models import (
    AccountDeletionRequest,
    Customer,
    Stylist,
    CustomerAddress,
    CustomerNotification,
    CustomUser,
    SalonManager,
    UserConsent,
)
from urllib.parse import urlencode
from PIL import Image, UnidentifiedImageError

AUTH_PAGE_SHARED_CONTEXT = {"hide_navbar": True}
OTP_PURPOSE_SIGNUP = "signup"
OTP_PURPOSE_PASSWORD_RESET = "password_reset"
USER_SESSION_KEY = "user_session"


class NotificationSettingsPayloadTooLarge(Exception):
    """Raised when notification settings payload exceeds the configured limit."""


class NotificationSettingsPayloadInvalid(Exception):
    """Raised when notification settings payload is not a JSON object."""


class NotificationSettingsValueInvalid(Exception):
    """Raised when notification settings contains an invalid boolean value."""


def _profile_image_is_animated(image):
    if getattr(image, "is_animated", False):
        return True

    try:
        return sum(1 for _frame in ImageSequence.Iterator(image)) > 1
    except Exception:
        return False


def _notification_settings_max_bytes():
    return max(
        int(
            getattr(
                settings,
                "CUSTOMER_NOTIFICATION_SETTINGS_MAX_BYTES",
                4 * 1024,
            )
            or 1
        ),
        1,
    )


def _load_notification_settings_payload(request):
    max_bytes = _notification_settings_max_bytes()

    content_length = request.META.get("CONTENT_LENGTH")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise NotificationSettingsPayloadTooLarge
        except ValueError:
            raise NotificationSettingsPayloadInvalid

    raw_body = request.body or b"{}"
    if len(raw_body) > max_bytes:
        raise NotificationSettingsPayloadTooLarge

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise NotificationSettingsPayloadInvalid

    if not isinstance(payload, dict):
        raise NotificationSettingsPayloadInvalid

    return payload


def _customer_notification_action_post_max_bytes():
    return max(
        int(
            getattr(
                settings,
                "CUSTOMER_NOTIFICATION_ACTION_POST_MAX_BYTES",
                2 * 1024,
            )
            or 1
        ),
        1,
    )


def _customer_notification_action_payload_too_large(request):
    max_bytes = _customer_notification_action_post_max_bytes()

    content_length = request.META.get("CONTENT_LENGTH")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                return True
        except ValueError:
            return True

    raw_body = request.body or b""
    return len(raw_body) > max_bytes


def _coerce_notification_boolean(value):
    if isinstance(value, bool):
        return value

    if isinstance(value, int) and value in {0, 1}:
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False

    raise NotificationSettingsValueInvalid


logger = logging.getLogger("accounts")


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


LEGAL_DOCUMENT_VERSION = "1.1-beta"


def _record_signup_consents(request, *, user, source):
    common = {
        "user": user,
        "version": LEGAL_DOCUMENT_VERSION,
        "is_granted": True,
        "source": source,
        "ip_address": _client_ip(request),
        "user_agent": request.META.get("HTTP_USER_AGENT", ""),
    }
    UserConsent.objects.bulk_create(
        [
            UserConsent(consent_type=UserConsent.CONSENT_TERMS, **common),
            UserConsent(consent_type=UserConsent.CONSENT_PRIVACY, **common),
        ]
    )


def _make_deleted_mobile(user):
    """
    شماره موبایل کاربر حذف‌شده باید از شماره واقعی جدا شود تا همان شماره
    بتواند دوباره ثبت‌نام کند. مقدار جدید عمداً با 09 شروع نمی‌شود.
    """
    user_id = int(user.pk or 0)

    candidates = [
        f"98{user_id % 1_000_000_000:09d}",
        f"97{user_id % 1_000_000_000:09d}",
        f"96{user_id % 1_000_000_000:09d}",
    ]

    for candidate in candidates:
        if (
            not CustomUser.objects.exclude(pk=user.pk)
            .filter(mobile_number=candidate)
            .exists()
        ):
            return candidate

    for offset in range(1, 1000):
        candidate = f"95{(user_id + offset) % 1_000_000_000:09d}"
        if (
            not CustomUser.objects.exclude(pk=user.pk)
            .filter(mobile_number=candidate)
            .exists()
        ):
            return candidate

    return f"94{int(time.time()) % 1_000_000_000:09d}"


def _anonymize_account_for_deletion(request, *, user, reason):
    now = timezone.now()
    deletion_request = AccountDeletionRequest.objects.create(
        user=user,
        original_user_id=user.pk,
        original_mobile_number=user.mobile_number or "",
        original_email=user.email or "",
        reason=reason or "",
        status=AccountDeletionRequest.STATUS_REQUESTED,
        metadata={
            "ip_address": _client_ip(request),
            "user_agent": request.META.get("HTTP_USER_AGENT", ""),
        },
    )

    try:
        customer = Customer.objects.filter(user=user).first()
        if customer:
            customer.address = ""
            customer.profile_image = None
            customer.birth_date = None
            customer.gender = None
            customer.save(
                update_fields=["address", "profile_image", "birth_date", "gender"]
            )
            CustomerAddress.objects.filter(customer=customer).delete()
    except Exception:
        pass

    deleted_mobile = _make_deleted_mobile(user)
    user.mobile_number = deleted_mobile
    user.email = ""
    user.name = "کاربر"
    user.family = "حذف‌شده"
    user.active_code = ""
    user.is_active = False
    user.set_unusable_password()
    user.save(
        update_fields=[
            "mobile_number",
            "email",
            "name",
            "family",
            "active_code",
            "is_active",
            "password",
        ]
    )

    CustomUser.objects.filter(pk=user.pk).update(
        mobile_number=deleted_mobile,
        email="",
        name="کاربر",
        family="حذف‌شده",
        active_code="",
        is_active=False,
    )

    deletion_request.status = AccountDeletionRequest.STATUS_ANONYMIZED
    deletion_request.anonymized_at = now
    deletion_request.completed_at = timezone.now()
    deletion_request.status = AccountDeletionRequest.STATUS_COMPLETED
    deletion_request.save(update_fields=["status", "anonymized_at", "completed_at"])
    return deletion_request


def _has_positive_amount(value):
    try:
        return int(value or 0) > 0
    except (TypeError, ValueError):
        return False


def _get_account_deletion_blockers(user):
    """
    حذف حساب در حالت‌هایی که نوبت، سالن فعال یا مانده مالی وجود دارد
    متوقف می‌شود تا داده عملیاتی/مالی خراب نشود.
    """
    blockers = []
    today = timezone.localdate()

    customer = Customer.objects.filter(user=user).first()
    if customer:
        has_future_customer_booking = (
            OrderDetail.objects.filter(
                order__customer=customer,
                date__gte=today,
            )
            .exclude(order__status="cancelled")
            .exists()
        )

        if has_future_customer_booking:
            blockers.append(
                "شما نوبت فعال یا آینده دارید. ابتدا نوبت را لغو یا تکلیف آن را مشخص کنید."
            )

    wallet = getattr(user, "wallet", None)
    if wallet and _has_positive_amount(getattr(wallet, "balance", 0)):
        blockers.append(
            "کیف پول شما موجودی دارد. قبل از حذف حساب باید موجودی کیف پول تسویه یا تعیین تکلیف شود."
        )

    manager = SalonManager.objects.filter(user=user).first()
    if manager:
        manager_salons = Salon.objects.filter(salon_manager=manager)
        if manager_salons.exists():
            blockers.append(
                "این حساب مدیر سالن است. حذف حساب مدیر فقط بعد از انتقال مالکیت یا غیرفعال‌سازی سالن توسط پشتیبانی انجام می‌شود."
            )

        has_future_salon_booking = (
            OrderDetail.objects.filter(
                salon__in=manager_salons,
                date__gte=today,
            )
            .exclude(order__status="cancelled")
            .exists()
        )

        if has_future_salon_booking:
            blockers.append(
                "برای یکی از سالن‌های شما نوبت فعال یا آینده وجود دارد. قبل از حذف حساب باید نوبت‌ها تعیین تکلیف شوند."
            )

    stylist = Stylist.objects.filter(user=user).first()
    if stylist:
        try:
            from apps.salons.models import SalonMembership, SalonMembershipStatus

            has_active_membership = SalonMembership.objects.filter(
                stylist=stylist,
                status=SalonMembershipStatus.ACTIVE,
            ).exists()
        except Exception:
            has_active_membership = False

        if has_active_membership:
            blockers.append(
                "این حساب متخصص هنوز همکاری فعال با مجموعه دارد. ابتدا همکاری‌ها را پایان دهید یا از مدیر مجموعه بخواهید همکاری را تعیین تکلیف کند."
            )

        has_future_stylist_booking = (
            OrderDetail.objects.filter(
                stylist=stylist,
                date__gte=today,
            )
            .exclude(order__status="cancelled")
            .exists()
        )

        if has_future_stylist_booking:
            blockers.append(
                "برای این متخصص نوبت فعال یا آینده وجود دارد. قبل از حذف حساب باید نوبت‌ها جابه‌جا، لغو یا تکمیل شوند."
            )

        stylist_wallet = getattr(stylist, "finance_wallet", None)
        if stylist_wallet and (
            _has_positive_amount(getattr(stylist_wallet, "available_balance", 0))
            or _has_positive_amount(getattr(stylist_wallet, "pending_balance", 0))
        ):
            blockers.append(
                "حساب مالی متخصص دارای مانده قابل دریافت یا در انتظار تسویه است."
            )

        try:
            from apps.payments.models import StylistWalletWithdrawalRequest

            has_pending_withdrawal = (
                StylistWalletWithdrawalRequest.objects.filter(
                    wallet=stylist_wallet,
                    status=StylistWalletWithdrawalRequest.Status.PENDING,
                ).exists()
                if stylist_wallet
                else False
            )
        except Exception:
            has_pending_withdrawal = False

        if has_pending_withdrawal:
            blockers.append(
                "درخواست برداشت در انتظار بررسی وجود دارد. ابتدا وضعیت برداشت مشخص شود."
            )

    return blockers


def _role_redirect_name(user):
    if hasattr(user, "salon_manager_profile"):
        return "dashboards:salon_manager_dashboard"
    if hasattr(user, "stylist"):
        return "dashboards:stylist_dashboard"
    if hasattr(user, "customer_profile"):
        return "accounts:customer_panel"
    return "salons:show_salons"


def _redirect_user_by_role(user):
    return redirect(_role_redirect_name(user))


def _user_role_access_label(user):
    if hasattr(user, "salon_manager_profile") and hasattr(user, "stylist"):
        return "مدیر سالن/متخصص"
    if hasattr(user, "salon_manager_profile"):
        return "مدیر سالن"
    if hasattr(user, "stylist"):
        return "متخصص"
    if hasattr(user, "customer_profile"):
        return "مشتری"
    if getattr(user, "is_admin", False):
        return "ادمین"
    return "کاربر"


def _add_wrong_area_message(request, *, target_area, redirect_area=None):
    role_label = _user_role_access_label(request.user)
    message = (
        f"این لینک مربوط به {target_area} است و با حساب {role_label} قابل دسترسی نیست."
    )
    if redirect_area:
        message += f" شما به {redirect_area} منتقل شدید."
    messages.error(request, message)


def _clean_next_url(request):
    next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()

    if not next_url:
        return ""

    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return ""

    login_path = reverse("accounts:login")
    logout_path = reverse("accounts:logout")

    if next_url.startswith(login_path) or next_url.startswith(logout_path):
        return ""

    return next_url


def _auth_context(request, **extra):
    next_url = _clean_next_url(request)
    context = {
        **AUTH_PAGE_SHARED_CONTEXT,
        "next_url": next_url,
        "next_query": f"?{urlencode({'next': next_url})}" if next_url else "",
    }
    context.update(extra)
    return context


def _redirect_after_auth(request, user, next_url=""):
    safe_next_url = next_url or _clean_next_url(request)

    if safe_next_url:
        return redirect(safe_next_url)

    return _redirect_user_by_role(user)


def _now_ts():
    return int(time.time())


def _otp_expiry_seconds():
    return max(int(getattr(settings, "OTP_EXPIRY_SECONDS", 180) or 180), 60)


def _otp_max_attempts():
    return max(int(getattr(settings, "OTP_MAX_ATTEMPTS", 5) or 5), 1)


def _otp_resend_cooldown_seconds():
    return max(
        int(getattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 60) or 60),
        30,
    )


def _password_reset_session_ttl_seconds():
    return max(
        int(getattr(settings, "PASSWORD_RESET_SESSION_TTL_SECONDS", 900) or 900),
        300,
    )


def _otp_code_length():
    return max(int(getattr(settings, "SMS_OTP_CODE_LENGTH", 5) or 5), 4)


def _verification_back_url(user_session):
    if user_session.get("remember_password"):
        return "accounts:remember_password"

    signup_kind = user_session.get("signup_kind")
    if signup_kind == "salon":
        return "accounts:register"
    if signup_kind == "stylist":
        return "accounts:stylist_signup"
    return "accounts:customer_signup"


def _otp_cooldown_cache_key(*, purpose, mobile_number):
    normalized_mobile = utils.normalize_mobile_number(mobile_number)
    return f"otp:cooldown:{purpose}:{normalized_mobile}"


class OtpRateLimitUnavailable(Exception):
    """Raised when OTP rate-limit storage is unavailable."""


def _otp_rate_limit_fail_closed():
    return bool(getattr(settings, "OTP_RATE_LIMIT_FAIL_CLOSED", True))


def _log_otp_cache_failure(*, purpose, mobile_number, operation, exc):
    logger.warning(
        "OTP rate-limit cache unavailable | operation=%s | purpose=%s | mobile=%s",
        operation,
        purpose,
        utils.mask_mobile_number(mobile_number),
        exc_info=exc,
    )


def _add_otp_rate_limit_unavailable_message(request):
    messages.error(
        request,
        "در حال حاضر امکان ارسال کد تایید وجود ندارد. لطفاً چند دقیقه دیگر دوباره تلاش کنید.",
        "danger",
    )


def _otp_cooldown_remaining(*, purpose, mobile_number):
    try:
        last_sent_at = cache.get(
            _otp_cooldown_cache_key(purpose=purpose, mobile_number=mobile_number)
        )
    except Exception as exc:
        _log_otp_cache_failure(
            purpose=purpose,
            mobile_number=mobile_number,
            operation="get",
            exc=exc,
        )
        if _otp_rate_limit_fail_closed():
            raise OtpRateLimitUnavailable from exc
        return 0

    if not last_sent_at:
        return 0

    remaining = _otp_resend_cooldown_seconds() - (_now_ts() - int(last_sent_at))
    return max(remaining, 0)


def _set_otp_cooldown(*, purpose, mobile_number, sent_at):
    try:
        cache.set(
            _otp_cooldown_cache_key(purpose=purpose, mobile_number=mobile_number),
            int(sent_at),
            timeout=_otp_resend_cooldown_seconds(),
        )
    except Exception as exc:
        _log_otp_cache_failure(
            purpose=purpose,
            mobile_number=mobile_number,
            operation="set",
            exc=exc,
        )
        if _otp_rate_limit_fail_closed():
            raise OtpRateLimitUnavailable from exc


def _build_verification_context(form, user_session):
    remember_password = bool(user_session.get("remember_password"))
    signup_kind = user_session.get("signup_kind", "customer")
    validity_minutes = max(math.ceil(_otp_expiry_seconds() / 60), 1)

    common_context = {
        "form": form,
        "mobile_number": utils.mask_mobile_number(
            user_session.get("mobile_number", "")
        ),
        "otp_validity_minutes": validity_minutes,
        "remaining_attempts": max(
            int(user_session.get("otp_max_attempts", _otp_max_attempts()))
            - int(user_session.get("otp_attempts", 0)),
            0,
        ),
        **AUTH_PAGE_SHARED_CONTEXT,
    }

    if remember_password:
        return {
            **common_context,
            "verification_mode": "password_reset",
            "verify_page_title": "تایید کد",
            "verify_heading": "کد تایید را وارد کنید",
            "verify_description": "کد ارسال‌شده را وارد کنید تا بتوانید رمز عبور خود را تغییر دهید.",
            "verify_submit_label": "ادامه",
            "verify_back_url": "accounts:remember_password",
        }

    signup_meta = {
        "salon": {
            "label": "سالن و کسب‌وکار",
            "back_url": "accounts:register",
        },
        "stylist": {
            "label": "متخصص",
            "back_url": "accounts:stylist_signup",
        },
        "customer": {
            "label": "مشتری",
            "back_url": "accounts:customer_signup",
        },
    }
    meta = signup_meta.get(signup_kind, signup_meta["customer"])

    return {
        **common_context,
        "verification_mode": "signup",
        "signup_kind": signup_kind,
        "verify_page_title": "تایید شماره موبایل",
        "verify_heading": f"کد فعال‌سازی {meta['label']} را وارد کنید",
        "verify_description": "کد ارسال‌شده به شماره موبایل شما را وارد کنید. پس از تأیید، ورود شما به‌صورت خودکار انجام می‌شود.",
        "verify_submit_label": "تایید و ورود",
        "verify_back_url": meta["back_url"],
    }


def _create_verification_session(
    *,
    mobile_number,
    code,
    signup_kind=None,
    remember_password=False,
    delivery_result=None,
    next_url="",
):
    now_ts = _now_ts()
    expires_at = now_ts + _otp_expiry_seconds()
    session_data = {
        "mobile_number": utils.normalize_mobile_number(mobile_number),
        "active_code": str(code),
        "remember_password": bool(remember_password),
        "signup_kind": signup_kind,
        "otp_created_at": now_ts,
        "otp_expires_at": expires_at,
        "otp_attempts": 0,
        "otp_max_attempts": _otp_max_attempts(),
        "otp_verified": False,
        "otp_purpose": (
            OTP_PURPOSE_PASSWORD_RESET if remember_password else OTP_PURPOSE_SIGNUP
        ),
        "password_reset_authorized_until": None,
        "next_url": next_url or "",
    }
    if delivery_result:
        session_data["otp_delivery_mode"] = delivery_result.mode
        session_data["otp_delivery_provider"] = delivery_result.provider
        session_data["otp_delivery_message_id"] = delivery_result.message_id
    return session_data


def _send_verification_code(request, *, user, purpose, signup_kind=None):
    try:
        remaining = _otp_cooldown_remaining(
            purpose=purpose,
            mobile_number=user.mobile_number,
        )
    except OtpRateLimitUnavailable:
        _add_otp_rate_limit_unavailable_message(request)
        return None

    if remaining > 0:
        messages.warning(
            request,
            f"کد قبلی هنوز معتبر است. لطفاً {remaining} ثانیه دیگر دوباره تلاش کنید.",
            "warning",
        )
        return None

    sent_at = _now_ts()
    try:
        _set_otp_cooldown(
            purpose=purpose,
            mobile_number=user.mobile_number,
            sent_at=sent_at,
        )
    except OtpRateLimitUnavailable:
        _add_otp_rate_limit_unavailable_message(request)
        return None

    code = str(utils.create_random_code(_otp_code_length())).zfill(_otp_code_length())
    delivery_result = utils.send_otp_sms(
        user.mobile_number,
        code,
        purpose=purpose,
    )

    should_show_code = bool(delivery_result.simulated)
    if not delivery_result.success and not should_show_code:
        messages.error(
            request,
            "ارسال کد تایید با خطا مواجه شد. لطفاً چند دقیقه دیگر دوباره تلاش کنید.",
            "danger",
        )
        return None

    user.active_code = utils.create_state_token()
    update_fields = ["active_code"]
    if purpose == OTP_PURPOSE_SIGNUP:
        user.is_active = False
        update_fields.append("is_active")
    user.save(update_fields=update_fields)

    request.session[USER_SESSION_KEY] = _create_verification_session(
        mobile_number=user.mobile_number,
        code=code,
        signup_kind=signup_kind,
        remember_password=(purpose == OTP_PURPOSE_PASSWORD_RESET),
        delivery_result=delivery_result,
        next_url=_clean_next_url(request),
    )
    request.session.modified = True
    _set_otp_cooldown(
        purpose=purpose,
        mobile_number=user.mobile_number,
        sent_at=_now_ts(),
    )

    if delivery_result.success and delivery_result.mode == "live":
        messages.success(
            request,
            "کد تایید برای شما ارسال شد. لطفاً آن را وارد کنید.",
            "success",
        )
    elif delivery_result.success and delivery_result.mode == "sandbox":
        messages.warning(
            request,
            f"درگاه پیامک در حالت Sandbox است و ارسال واقعی انجام نمی‌شود. کد تست شما: {code}",
            "warning",
        )
    else:
        messages.warning(
            request,
            f"ارسال پیامک در محیط تست/دمو شبیه‌سازی شد. کد تست شما: {code}",
            "warning",
        )

    return redirect("accounts:verify")


def _start_verification(request, *, user, signup_kind):
    return _send_verification_code(
        request,
        user=user,
        purpose=OTP_PURPOSE_SIGNUP,
        signup_kind=signup_kind,
    )


# ----------------------------------------------------------------------------------------------------
class CustomerSignupView(View):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return _redirect_after_auth(request, request.user)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        form = CustomerSignupForm()
        return render(
            request,
            "accounts/customer_signup.html",
            _auth_context(request, form=form),
        )

    def post(self, request):
        form = CustomerSignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            Customer.objects.get_or_create(user=user)
            _record_signup_consents(request, user=user, source="customer_signup")
            verification_response = _start_verification(
                request,
                user=user,
                signup_kind="customer",
            )
            if verification_response is not None:
                return verification_response
            user.delete()
            return render(
                request,
                "accounts/customer_signup.html",
                _auth_context(request, form=form),
            )

        messages.error(
            request, "خطا در ثبت‌نام. لطفاً اطلاعات را بررسی کنید.", "danger"
        )
        return render(
            request,
            "accounts/customer_signup.html",
            _auth_context(request, form=form),
        )


# --------------------------------------------------------------------------------------------------
class StylistSignupView(View):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return _redirect_user_by_role(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        form = StylistSignupForm()
        return render(
            request,
            "accounts/stylist_signup.html",
            {"form": form, **AUTH_PAGE_SHARED_CONTEXT},
        )

    def post(self, request):
        form = StylistSignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            expert = form.cleaned_data["expert"]

            Stylist.objects.update_or_create(
                user=user,
                defaults={
                    "expert": expert,
                    "display_name": user.get_fullName(),
                    "resume_headline": expert,
                    "public_visibility": Stylist.PublicVisibility.RESUME_ONLY,
                    "is_active": True,
                },
            )

            _record_signup_consents(request, user=user, source="stylist_signup")
            verification_response = _start_verification(
                request,
                user=user,
                signup_kind="stylist",
            )
            if verification_response is not None:
                return verification_response

            user.delete()
            return render(
                request,
                "accounts/stylist_signup.html",
                {"form": form, **AUTH_PAGE_SHARED_CONTEXT},
            )

        messages.error(
            request, "خطا در ثبت‌نام متخصص. لطفاً اطلاعات را بررسی کنید.", "danger"
        )
        return render(
            request,
            "accounts/stylist_signup.html",
            {"form": form, **AUTH_PAGE_SHARED_CONTEXT},
        )


# ----------------------------------------------------------------------------------------------------
class RegisterUserView(View):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return _redirect_after_auth(request, request.user)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = RegisterUserForm()
        return render(
            request,
            "accounts/register.html",
            _auth_context(request, form=form),
        )

    def post(self, request, *args, **kwargs):
        form = RegisterUserForm(request.POST)
        if form.is_valid():
            user = form.save()
            SalonManager.objects.get_or_create(user=user)
            _record_signup_consents(request, user=user, source="salon_signup")
            verification_response = _start_verification(
                request,
                user=user,
                signup_kind="salon",
            )
            if verification_response is not None:
                return verification_response
            user.delete()
            return render(
                request,
                "accounts/register.html",
                _auth_context(request, form=form),
            )

        messages.error(
            request, "خطا در انجام ثبت‌نام. لطفاً اطلاعات را بررسی کنید.", "danger"
        )
        return render(
            request,
            "accounts/register.html",
            _auth_context(request, form=form),
        )


# ----------------------------------------------------------------------------------------------------
class VerifyRegisterView(View):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return _redirect_after_auth(request, request.user)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        user_session = request.session.get(USER_SESSION_KEY)
        if not user_session:
            messages.info(
                request, "ابتدا شماره موبایل و کد دریافتی را ثبت کنید.", "info"
            )
            return redirect("accounts:login")

        expires_at = int(user_session.get("otp_expires_at", 0) or 0)
        if expires_at and _now_ts() > expires_at:
            request.session.pop(USER_SESSION_KEY, None)
            messages.error(
                request,
                "کد تایید منقضی شده است. لطفاً دوباره درخواست کد بدهید.",
                "danger",
            )
            return redirect(_verification_back_url(user_session))

        form = VerifyRegisterForm()
        return render(
            request,
            "accounts/verify.html",
            _build_verification_context(form, user_session),
        )

    def post(self, request, *args, **kwargs):
        user_session = request.session.get(USER_SESSION_KEY)
        if not user_session:
            messages.error(request, "جلسه بازیابی یا ثبت‌نام منقضی شده است.", "danger")
            return redirect("accounts:login")

        expires_at = int(user_session.get("otp_expires_at", 0) or 0)
        if expires_at and _now_ts() > expires_at:
            request.session.pop(USER_SESSION_KEY, None)
            messages.error(
                request,
                "کد تایید منقضی شده است. لطفاً دوباره درخواست کد بدهید.",
                "danger",
            )
            return redirect(_verification_back_url(user_session))

        if int(user_session.get("otp_attempts", 0) or 0) >= int(
            user_session.get("otp_max_attempts", _otp_max_attempts())
            or _otp_max_attempts()
        ):
            request.session.pop(USER_SESSION_KEY, None)
            messages.error(
                request,
                "تعداد تلاش‌های مجاز تمام شده است. لطفاً دوباره درخواست کد بدهید.",
                "danger",
            )
            return redirect(_verification_back_url(user_session))

        form = VerifyRegisterForm(request.POST)
        if not form.is_valid():
            messages.error(request, "اطلاعات وارد شده اشتباه است.", "danger")
            return render(
                request,
                "accounts/verify.html",
                _build_verification_context(form, user_session),
            )

        data = form.cleaned_data
        if str(user_session.get("active_code")) != str(data["active_code"]):
            user_session["otp_attempts"] = (
                int(user_session.get("otp_attempts", 0) or 0) + 1
            )
            request.session[USER_SESSION_KEY] = user_session
            request.session.modified = True
            remaining_attempts = max(
                int(user_session.get("otp_max_attempts", _otp_max_attempts()))
                - int(user_session.get("otp_attempts", 0)),
                0,
            )
            if remaining_attempts <= 0:
                request.session.pop(USER_SESSION_KEY, None)
                messages.error(
                    request,
                    "کد تایید بیش از حد اشتباه وارد شد. لطفاً دوباره درخواست کد بدهید.",
                    "danger",
                )
                return redirect(_verification_back_url(user_session))

            messages.error(
                request,
                f"کد وارد شده اشتباه است. {remaining_attempts} تلاش دیگر باقی مانده است.",
                "danger",
            )
            return render(
                request,
                "accounts/verify.html",
                _build_verification_context(form, user_session),
            )

        try:
            user = CustomUser.objects.get(mobile_number=user_session["mobile_number"])
        except CustomUser.DoesNotExist:
            request.session.pop(USER_SESSION_KEY, None)
            messages.error(request, "کاربر مرتبط با این کد پیدا نشد.", "danger")
            return redirect("accounts:login")

        if user_session.get("remember_password"):
            user_session["otp_verified"] = True
            user_session["password_reset_authorized_until"] = (
                _now_ts() + _password_reset_session_ttl_seconds()
            )
            request.session[USER_SESSION_KEY] = user_session
            request.session.modified = True
            return redirect("accounts:change_password")

        signup_kind = user_session.get("signup_kind")

        user.is_active = True
        user.active_code = utils.create_state_token()
        user.save(update_fields=["is_active", "active_code"])

        request.session.pop(USER_SESSION_KEY, None)
        login(request, user)

        if signup_kind == "stylist":
            messages.success(
                request,
                "ثبت‌نام متخصص کامل شد. حالا پروفایل حرفه‌ای خودت را تکمیل کن.",
                "success",
            )
            return redirect("dashboards:stylist_profile")

        messages.success(request, "ثبت‌نام شما کامل شد و وارد حساب شدید.", "success")
        return _redirect_user_by_role(user)


# ------------------------------------------------------------------------------------------------------
class LoginUserView(View):
    template_name = "accounts/login.html"
    form_class = LoginUserForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return _redirect_after_auth(request, request.user)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = self.form_class()
        return render(
            request,
            self.template_name,
            _auth_context(request, form=form),
        )

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        next_url = _clean_next_url(request)

        if not form.is_valid():
            messages.error(request, "لطفاً تمام فیلدها را به درستی پر کنید.", "danger")
            return render(
                request,
                self.template_name,
                _auth_context(request, form=form),
            )

        cleaned_data = form.cleaned_data
        user = authenticate(
            username=cleaned_data["mobile_number"],
            password=cleaned_data["password"],
        )

        if user is None:
            messages.error(request, "شماره موبایل یا رمز عبور اشتباه است.", "danger")
            return render(
                request,
                self.template_name,
                _auth_context(request, form=form),
            )

        if not user.is_active:
            messages.error(request, "حساب کاربری شما فعال نمی‌باشد.", "danger")
            return render(
                request,
                self.template_name,
                _auth_context(request, form=form),
            )

        if user.is_admin and not (next_url or "").startswith("/platform/"):
            messages.warning(
                request,
                "برای ورود به پنل پلتفرم، ابتدا آدرس /platform/ را باز کن یا از ورود امن مدیران استفاده کن.",
                "warning",
            )
            return render(
                request,
                self.template_name,
                _auth_context(request, form=form),
            )

        login(request, user)
        messages.success(request, "ورود با موفقیت انجام شد.", "success")
        return _redirect_after_auth(request, user, next_url=next_url)


# ----------------------------------------------------------------------------------------------------
class LogoutUserView(View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("salons:show_salons")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        session_data = request.session.get("order_cart")
        logout(request)
        request.session["order_cart"] = session_data
        return redirect("salons:show_salons")


# ---------------------------------------------------------------------------------------------------
def _get_valid_password_reset_session(request):
    user_session = request.session.get(USER_SESSION_KEY)
    if not user_session:
        return None
    if not user_session.get("remember_password"):
        return None
    if not user_session.get("otp_verified"):
        return None
    authorized_until = int(user_session.get("password_reset_authorized_until", 0) or 0)
    if authorized_until and _now_ts() <= authorized_until:
        return user_session
    request.session.pop(USER_SESSION_KEY, None)
    return None


class ChangePasswordView(View):
    def get(self, request, *args, **kwargs):
        requires_current_password = request.user.is_authenticated
        form = ChangePasswordForm(require_current_password=requires_current_password)
        context = {
            "form": form,
            "user_mobile": None,
            "requires_current_password": requires_current_password,
        }

        if request.user.is_authenticated:
            context["user_mobile"] = request.user.mobile_number
        else:
            user_session = _get_valid_password_reset_session(request)
            if not user_session:
                messages.error(
                    request,
                    "ابتدا کد تایید بازیابی رمز را با موفقیت وارد کنید.",
                    "danger",
                )
                return redirect("accounts:remember_password")
            try:
                user = CustomUser.objects.get(
                    mobile_number=user_session["mobile_number"]
                )
                context["user_mobile"] = user.mobile_number
            except CustomUser.DoesNotExist:
                request.session.pop(USER_SESSION_KEY, None)
                messages.error(request, "کاربر یافت نشد", "danger")
                return redirect("accounts:login")

        return render(request, "accounts/change_password.html", context)

    def post(self, request, *args, **kwargs):
        requires_current_password = request.user.is_authenticated
        form = ChangePasswordForm(
            request.POST, require_current_password=requires_current_password
        )

        user = None
        user_mobile = None

        if request.user.is_authenticated:
            user = request.user
            user_mobile = user.mobile_number
        else:
            user_session = _get_valid_password_reset_session(request)
            if not user_session:
                messages.error(
                    request,
                    "جلسه بازیابی رمز منقضی شده است. دوباره کد دریافت کنید.",
                    "danger",
                )
                return redirect("accounts:remember_password")
            try:
                user = CustomUser.objects.get(
                    mobile_number=user_session["mobile_number"]
                )
                user_mobile = user.mobile_number
            except CustomUser.DoesNotExist:
                request.session.pop(USER_SESSION_KEY, None)
                messages.error(request, "کاربر یافت نشد", "danger")
                return redirect("accounts:login")

        if form.is_valid():
            data = form.cleaned_data

            if request.user.is_authenticated:
                if not user.check_password(data["current_password"]):
                    messages.error(request, "رمز عبور فعلی اشتباه است", "danger")
                    return render(
                        request,
                        "accounts/change_password.html",
                        {
                            "form": form,
                            "user_mobile": user_mobile,
                            "requires_current_password": requires_current_password,
                        },
                    )

            user.set_password(data["password1"])
            user.active_code = utils.create_state_token()
            user.save(update_fields=["password", "active_code"])
            request.session.pop(USER_SESSION_KEY, None)

            messages.success(request, "رمز عبور شما با موفقیت تغییر کرد", "success")

            if request.user.is_authenticated:
                logout(request)

            return redirect("accounts:login")

        messages.error(request, "اطلاعات وارد شده اشتباه است", "danger")
        return render(
            request,
            "accounts/change_password.html",
            {
                "form": form,
                "user_mobile": user_mobile,
                "requires_current_password": requires_current_password,
            },
        )


# ---------------------------------------------------------------------------------------------------
class RememberPasswordView(View):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return _redirect_user_by_role(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = RememberPasswordForm()
        return render(
            request,
            "accounts/remember_password.html",
            {"form": form, **AUTH_PAGE_SHARED_CONTEXT},
        )

    def post(self, request, *args, **kwargs):
        form = RememberPasswordForm(request.POST)
        if not form.is_valid():
            messages.error(request, "شماره موبایل را درست وارد کنید.", "danger")
            return render(
                request,
                "accounts/remember_password.html",
                {"form": form, **AUTH_PAGE_SHARED_CONTEXT},
            )

        data = form.cleaned_data
        try:
            user = CustomUser.objects.get(mobile_number=data["mobile_number"])
        except CustomUser.DoesNotExist:
            messages.error(request, "شماره وارد شده در سیستم پیدا نشد.", "danger")
            return render(
                request,
                "accounts/remember_password.html",
                {"form": form, **AUTH_PAGE_SHARED_CONTEXT},
            )

        verification_response = _send_verification_code(
            request,
            user=user,
            purpose=OTP_PURPOSE_PASSWORD_RESET,
        )
        if verification_response is not None:
            return verification_response

        return render(
            request,
            "accounts/remember_password.html",
            {"form": form, **AUTH_PAGE_SHARED_CONTEXT},
        )


def _redirect_if_non_customer_user(request):
    if hasattr(request.user, "stylist") or hasattr(
        request.user, "salon_manager_profile"
    ):
        _add_wrong_area_message(
            request,
            target_area="پنل مشتری",
            redirect_area="داشبورد مناسب حساب خود",
        )
        return _redirect_user_by_role(request.user)
    return None


def _get_customer_profile(user):
    try:
        return user.customer_profile
    except Customer.DoesNotExist as exc:
        raise Http404("پروفایل مشتری یافت نشد") from exc


def _bootstrap_customer_addresses(customer):
    if customer.addresses.exists() or not customer.address:
        return
    CustomerAddress.objects.create(
        customer=customer,
        title="آدرس اصلی",
        recipient_name=customer.get_fullName(),
        phone_number=customer.user.mobile_number,
        address_line=customer.address,
        is_default=True,
    )


def _get_primary_address(customer):
    _bootstrap_customer_addresses(customer)
    return (
        customer.addresses.filter(is_default=True).first() or customer.addresses.first()
    )


# ---------------------------------------------------------------------------------------------------
class CustomerUpdateProfileView(LoginRequiredMixin, View):
    def get(self, request):
        redirect_response = _redirect_if_non_customer_user(request)
        if redirect_response:
            return redirect_response
        user = request.user
        customer = _get_customer_profile(user)
        form = CustomerUpdateProfileForm(customer_instance=customer, instance=user)
        return render(
            request,
            "accounts/edit_profile.html",
            {"form": form, "customer": customer, "user": user},
        )

    def post(self, request):
        redirect_response = _redirect_if_non_customer_user(request)
        if redirect_response:
            return redirect_response
        user = request.user
        customer = _get_customer_profile(user)
        form = CustomerUpdateProfileForm(
            request.POST, request.FILES, customer_instance=customer, instance=user
        )

        if form.is_valid():
            form.save()
            messages.success(request, "ویرایش با موفقیت ثبت شد", "success")
            return redirect("accounts:customerProfile")

        messages.error(request, "لطفاً خطاهای فرم را بررسی کنید.", "error")
        return render(
            request,
            "accounts/edit_profile.html",
            {"form": form, "customer": customer, "user": user},
        )


# ---------------------------------------------------------------------------------------------------
class CustomerPanelPageView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        redirect_response = _redirect_if_non_customer_user(request)
        if redirect_response:
            return redirect_response
        user = get_object_or_404(
            CustomUser.objects.select_related("customer_profile"),
            id=request.user.id,
        )
        customer = _get_customer_profile(user)
        primary_address = _get_primary_address(customer)

        context = {
            "customer": customer,
            "wallet": getattr(user, "wallet", None),
            "primary_address": primary_address,
            "address_count": customer.addresses.count(),
        }

        return render(request, "accounts/customer_panel.html", context)


# ---------------------------------------------------------------------------------------------------
class CustomerProfilePageView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        redirect_response = _redirect_if_non_customer_user(request)
        if redirect_response:
            return redirect_response
        customer = _get_customer_profile(request.user)
        _bootstrap_customer_addresses(customer)
        addresses = customer.addresses.all()
        context = {
            "customer": customer,
            "addresses": addresses,
            "primary_address": addresses.filter(is_default=True).first()
            or addresses.first(),
        }
        return render(request, "accounts/customer_profile.html", context)


class CustomerAddressListView(LoginRequiredMixin, View):
    def get(self, request):
        customer = _get_customer_profile(request.user)
        _bootstrap_customer_addresses(customer)
        addresses = customer.addresses.all()
        return render(
            request,
            "accounts/customer_addresses.html",
            {
                "customer": customer,
                "addresses": addresses,
                "primary_address": addresses.filter(is_default=True).first()
                or addresses.first(),
            },
        )


class CustomerAddressCreateView(LoginRequiredMixin, View):
    def get(self, request):
        customer = _get_customer_profile(request.user)
        form = CustomerAddressForm(initial={"phone_number": request.user.mobile_number})
        return render(
            request,
            "accounts/address_form.html",
            {"form": form, "mode": "create", "customer": customer},
        )

    def post(self, request):
        customer = _get_customer_profile(request.user)
        form = CustomerAddressForm(request.POST)
        if form.is_valid():
            form.save(customer=customer)
            messages.success(request, "آدرس جدید با موفقیت ذخیره شد.")
            return redirect("accounts:customer_addresses")
        return render(
            request,
            "accounts/address_form.html",
            {"form": form, "mode": "create", "customer": customer},
        )


class CustomerAddressUpdateView(LoginRequiredMixin, View):
    def _get_object(self, request, address_id):
        customer = _get_customer_profile(request.user)
        _bootstrap_customer_addresses(customer)
        return get_object_or_404(CustomerAddress, pk=address_id, customer=customer)

    def get(self, request, address_id):
        address = self._get_object(request, address_id)
        form = CustomerAddressForm(instance=address)
        return render(
            request,
            "accounts/address_form.html",
            {"form": form, "mode": "edit", "address": address},
        )

    def post(self, request, address_id):
        address = self._get_object(request, address_id)
        form = CustomerAddressForm(request.POST, instance=address)
        if form.is_valid():
            form.save(customer=address.customer)
            messages.success(request, "آدرس با موفقیت ویرایش شد.")
            return redirect("accounts:customer_addresses")
        return render(
            request,
            "accounts/address_form.html",
            {"form": form, "mode": "edit", "address": address},
        )


@login_required
@require_POST
def customer_address_delete(request, address_id):
    customer = _get_customer_profile(request.user)
    address = get_object_or_404(CustomerAddress, pk=address_id, customer=customer)
    address.delete()
    messages.success(request, "آدرس حذف شد.")
    return redirect("accounts:customer_addresses")


@login_required
@require_POST
def customer_address_set_default(request, address_id):
    customer = _get_customer_profile(request.user)
    address = get_object_or_404(CustomerAddress, pk=address_id, customer=customer)
    address.is_default = True
    address.save()
    messages.success(request, "آدرس پیش‌فرض شما به‌روزرسانی شد.")
    return redirect("accounts:customer_addresses")


# ---------------------------------------------------------------------------------------------------
ALLOWED_PROFILE_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

ALLOWED_PROFILE_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

BLOCKED_FILENAME_PARTS = {
    ".php",
    ".phtml",
    ".phar",
    ".html",
    ".htm",
    ".js",
    ".svg",
    ".xml",
    ".exe",
    ".sh",
    ".bat",
    ".cmd",
}

MAX_PROFILE_IMAGE_SIZE = 2 * 1024 * 1024  # 2MB


def _customer_profile_image_max_dimension():
    return max(
        int(getattr(settings, "CUSTOMER_PROFILE_IMAGE_MAX_DIMENSION", 5000) or 1),
        1,
    )


def _customer_profile_image_max_pixels():
    return max(
        int(getattr(settings, "CUSTOMER_PROFILE_IMAGE_MAX_PIXELS", 10_000_000) or 1),
        1,
    )


def _validate_profile_image_dimensions(image):
    width, height = image.size
    max_dimension = _customer_profile_image_max_dimension()
    max_pixels = _customer_profile_image_max_pixels()

    if width <= 0 or height <= 0:
        raise ValidationError("ابعاد تصویر معتبر نیست.")

    if width > max_dimension or height > max_dimension:
        raise ValidationError("ابعاد تصویر بیش از حد مجاز است.")

    if width * height > max_pixels:
        raise ValidationError("تعداد پیکسل‌های تصویر بیش از حد مجاز است.")


def validate_uploaded_profile_image(uploaded_file):
    if not uploaded_file:
        raise ValidationError("تصویر ارسال نشده است.")

    if uploaded_file.size > MAX_PROFILE_IMAGE_SIZE:
        raise ValidationError("حجم تصویر نباید بیشتر از ۲ مگابایت باشد.")

    original_name = os.path.basename(uploaded_file.name or "").lower()
    _, ext = os.path.splitext(original_name)

    if ext not in ALLOWED_PROFILE_IMAGE_EXTENSIONS:
        raise ValidationError(
            "پسوند تصویر مجاز نیست. فقط JPG، PNG یا WEBP قابل قبول است."
        )

    name_without_last_ext = original_name[: -len(ext)] if ext else original_name
    if any(blocked in name_without_last_ext for blocked in BLOCKED_FILENAME_PARTS):
        raise ValidationError("نام یا پسوند فایل مجاز نیست.")

    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    if content_type not in ALLOWED_PROFILE_IMAGE_CONTENT_TYPES:
        raise ValidationError(
            "فرمت فایل مجاز نیست. فقط JPG، PNG یا WEBP قابل قبول است."
        )

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image.verify()
        uploaded_file.seek(0)
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError("فایل ارسال‌شده تصویر معتبر نیست.")

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)

        if image.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValidationError("فرمت واقعی تصویر مجاز نیست.")

        if _profile_image_is_animated(image):
            raise ValidationError("تصویر متحرک برای پروفایل مجاز نیست.")

        _validate_profile_image_dimensions(image)

        uploaded_file.seek(0)
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError("فایل ارسال‌شده تصویر معتبر نیست.")


@login_required
@require_POST
def customer_update_profile_image(request):
    try:
        customer = Customer.objects.get(user=request.user)
    except Customer.DoesNotExist:
        return JsonResponse(
            {"status": "error", "error": "کاربر مربوطه یافت نشد."},
            status=404,
        )

    image = request.FILES.get("image")

    try:
        validate_uploaded_profile_image(image)
    except ValidationError as exc:
        message = (
            exc.messages[0] if hasattr(exc, "messages") and exc.messages else str(exc)
        )
        return JsonResponse(
            {"status": "error", "error": message},
            status=400,
        )

    customer.profile_image = image
    customer.save(update_fields=["profile_image"])

    return JsonResponse(
        {
            "status": "success",
            "image_url": customer.profile_image.url,
        }
    )


# ---------------------------------------------------------------------------------------------------
@login_required
def add_customer(request, salon_id):
    salon = get_object_or_404(
        Salon.objects.select_related("salon_manager__user"),
        pk=salon_id,
        salon_manager__user=request.user,
    )

    from apps.dashboards.layout import build_dashboard_context

    def _is_ajax(req):
        return req.headers.get(
            "x-requested-with"
        ) == "XMLHttpRequest" or "application/json" in (req.headers.get("Accept") or "")

    next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if next_url and not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = ""

    form = AddCustomerForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        try:
            user = CustomUser.objects.create(
                mobile_number=cd["mobile_number"],
                name=cd["name"],
                family=cd["family"],
                email=cd.get("email", ""),
                is_active=True,
            )
            customer = Customer.objects.create(
                user=user,
                address=cd.get("address", ""),
                added_by_salon=salon,
            )
        except IntegrityError:
            form.add_error("mobile_number", "این شماره موبایل قبلاً ثبت شده است.")
        else:
            success_message = "مشتری با موفقیت ایجاد شد."
            redirect_url = next_url or reverse(
                "accounts:detail_customer", kwargs={"customer_id": customer.pk}
            )
            if _is_ajax(request):
                return JsonResponse(
                    {
                        "success": True,
                        "message": success_message,
                        "redirect_url": redirect_url,
                    }
                )
            messages.success(request, success_message)
            return redirect(redirect_url)

    elif request.method == "POST" and _is_ajax(request):
        return JsonResponse({"success": False, "errors": form.errors}, status=400)

    context = build_dashboard_context(
        request.user,
        nav_active="home",
        sidebar_active="clients",
        page_title="افزودن مشتری",
        request_path=request.path,
    )
    context.update(
        {
            "hide_dashboardHeader": True,
            "target_salon": salon,
            "form": form,
            "back_url": next_url or reverse("dashboards:salons_customers_page"),
            "next_url": next_url,
        }
    )
    return render(request, "accounts/add_customer.html", context)


# ---------------------------------------------------------------------------------------------------
def _get_request_manager_salon_or_403(request):
    if not request.user.is_authenticated:
        raise PermissionDenied

    if not hasattr(request.user, "salon_manager_profile"):
        raise PermissionDenied

    salon_manager = request.user.salon_manager_profile

    return get_object_or_404(
        Salon.objects.select_related("salon_manager__user"),
        salon_manager=salon_manager,
        is_active=True,
    )


def _manager_customer_queryset_for_salon(salon):
    customer_ids_from_orders = (
        OrderDetail.objects.filter(salon=salon)
        .values_list("order__customer_id", flat=True)
        .distinct()
    )

    return (
        Customer.objects.filter(
            Q(user_id__in=customer_ids_from_orders) | Q(added_by_salon=salon)
        )
        .select_related("user")
        .distinct()
    )


def _customer_note_text_max_chars():
    return max(
        int(getattr(settings, "CUSTOMER_NOTE_TEXT_MAX_CHARS", 2000) or 1),
        1,
    )


class DetailCustomerView(LoginRequiredMixin, View):
    def get(self, request, customer_id):
        # =================================================================
        # ۱. واکشی اطلاعات اولیه (بهینه شده)
        # =================================================================
        salon = _get_request_manager_salon_or_403(request)
        customer = get_object_or_404(
            _manager_customer_queryset_for_salon(salon),
            pk=customer_id,
        )

        # =================================================================
        # ۲. اطلاعات سفارش‌ها و قرارها (یک کوئری جامع)
        # =================================================================
        order_details_qs = (
            OrderDetail.objects.filter(order__customer=customer, salon=salon)
            .select_related("order", "service", "stylist__user")
            .order_by("-date", "-time")
        )

        # =================================================================
        # ۳. محاسبه فروش کل (یک کوئری aggregate)
        # =================================================================
        total_sales_data = OrderDetail.objects.filter(
            order__customer=customer,
            salon=salon,
            order__is_finally=True,
        ).aggregate(total=Sum("price"))
        total_sales = total_sales_data.get("total") or 0

        # =================================================================
        # ۴. نظرات و امتیازات مشتری (یک کوئری جامع)
        # =================================================================
        comments_qs = Comments.objects.filter(
            comment_user=customer, salon=salon
        ).select_related("stylist__user", "service", "scoring")

        rating_aggregate = comments_qs.filter(scoring__score__isnull=False).aggregate(
            avg_score=Avg("scoring__score")
        )
        avg_rating = (
            round(rating_aggregate["avg_score"], 1)
            if rating_aggregate["avg_score"] is not None
            else "-"
        )

        # =================================================================
        # ۵. یادداشت‌های مشتری و نوبت‌ها (دو کوئری بهینه)
        # =================================================================
        customer_notes_qs = (
            CustomerNote.objects.filter(customer=customer, salon=salon)
            .select_related("created_by")
            .order_by("-created_at")
        )

        appointment_notes_qs = (
            Order.objects.filter(customer=customer, salon=salon)
            .exclude(description__exact="")
            .prefetch_related("order_details1")
            .distinct()
            .order_by("-update_date")
        )

        context = {
            "hide_dashboardHeader": True,
            "customer": customer,
            "order_details": order_details_qs,
            "completed_appointments": [
                od for od in order_details_qs if od.order.is_finally
            ],
            "appointments_count": order_details_qs.count(),
            "total_sales": total_sales,
            "canceled_count": 0,
            "no_show_count": 0,
            "rating": avg_rating,
            "wallet_balance": 0,
            "comments_count": comments_qs.count(),
            "customer_ratings": comments_qs,  # ارسال مستقیم queryset بهینه شده
            "customer_notes": customer_notes_qs,
            "customer_notes_count": customer_notes_qs.count(),
            "appointment_notes": appointment_notes_qs,
            "appointment_notes_count": appointment_notes_qs.count(),
        }

        return render(request, "dashboards/customer_detail.html", context)

    def post(self, request, customer_id):
        # بهینه‌سازی واکشی اولیه در متد POST
        salon = _get_request_manager_salon_or_403(request)
        customer = get_object_or_404(
            _manager_customer_queryset_for_salon(salon),
            pk=customer_id,
        )

        if "note" in request.POST:
            note_text = request.POST.get("note", "").strip()
            note_image = request.FILES.get("note_image", None)

            if len(note_text) > _customer_note_text_max_chars():
                messages.error(request, "متن یادداشت بیش از حد مجاز است.")
                return redirect("accounts:detail_customer", customer_id=customer_id)

            if note_image:
                try:
                    note_image = validate_customer_profile_image_upload(
                        note_image,
                        declared_content_type=getattr(note_image, "content_type", "")
                        or None,
                    )
                except ValidationError as exc:
                    error_message = (
                        exc.messages[0]
                        if getattr(exc, "messages", None)
                        else "تصویر یادداشت معتبر نیست."
                    )
                    messages.error(request, error_message)
                    return redirect("accounts:detail_customer", customer_id=customer_id)

            if note_text:
                CustomerNote.objects.create(
                    salon=salon,
                    customer=customer,
                    note=note_text,
                    note_image=note_image,
                    created_by=request.user,
                )
                messages.success(request, "یادداشت با موفقیت ثبت شد.")

        return redirect("accounts:detail_customer", customer_id=customer_id)


# ---------------------------------------------------------------------------------------------------
@require_POST
@login_required
def delete_customer_note(request, note_id, customer_id):
    if not hasattr(request.user, "salon_manager_profile"):
        raise PermissionDenied

    try:
        note = CustomerNote.objects.get(
            id=note_id,
            customer_id=customer_id,
            salon__salon_manager=request.user.salon_manager_profile,
        )
        note.delete()
        messages.success(request, "یادداشت با موفقیت حذف شد.")
    except CustomerNote.DoesNotExist:
        messages.error(request, "یادداشت مورد نظر یافت نشد.")

    return redirect("accounts:detail_customer", customer_id=customer_id)


# ----------------------------------------------------------------------------------------------------
class CustomerSettingsView(LoginRequiredMixin, View):
    def get(self, request):
        customer = _get_customer_profile(request.user)
        _bootstrap_customer_addresses(customer)
        return render(
            request,
            "accounts/customer_settings.html",
            {"customer": customer, "address_count": customer.addresses.count()},
        )


# ----------------------------------------------------------------------------------------------------
class NotificationSettingsView(LoginRequiredMixin, View):
    """Notification Settings Page"""

    def get(self, request):
        try:
            customer = request.user.customer_profile
        except Customer.DoesNotExist:
            raise Http404("پروفایل مشتری یافت نشد")

        context = {
            "customer": customer,
        }
        return render(request, "accounts/notification_settings.html", context)


# ----------------------------------------------------------------------------------------------------
@login_required
@require_POST
def update_notification_settings(request):
    """API endpoint to update customer notification settings via AJAX."""
    try:
        customer = request.user.customer_profile
    except Customer.DoesNotExist:
        return JsonResponse({"error": "access_denied"}, status=403)

    try:
        data = _load_notification_settings_payload(request)
    except NotificationSettingsPayloadTooLarge:
        return JsonResponse({"error": "payload_too_large"}, status=413)
    except NotificationSettingsPayloadInvalid:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    valid_fields = [
        "notify_appointment_email",
        "notify_appointment_sms",
        "notify_appointment_whatsapp",
        "notify_marketing_email",
        "notify_marketing_sms",
        "notify_marketing_whatsapp",
    ]

    changed_fields = []
    try:
        for field, value in data.items():
            if field not in valid_fields:
                continue

            setattr(customer, field, _coerce_notification_boolean(value))
            changed_fields.append(field)
    except NotificationSettingsValueInvalid:
        return JsonResponse({"error": "invalid_notification_value"}, status=400)

    if changed_fields:
        customer.save(update_fields=changed_fields)

    return JsonResponse({"status": "success"})


# ----------------------------------------------------------------------------------------------------
class CustomerNotificationsView(LoginRequiredMixin, View):
    """Customer in-app notification center."""

    template_name = "accounts/notifications.html"
    paginate_by = 12

    def get(self, request):
        redirect_response = _redirect_if_non_customer_user(request)
        if redirect_response:
            return redirect_response

        customer = _get_customer_profile(request.user)
        active_filter = request.GET.get("filter", "all")
        active_category = request.GET.get("category", "all")

        notifications = CustomerNotification.objects.filter(user=request.user).order_by(
            "-created_at", "-id"
        )

        if active_filter == "unread":
            notifications = notifications.filter(is_read=False)
        elif active_filter == "read":
            notifications = notifications.filter(is_read=True)

        valid_categories = {
            choice[0] for choice in CustomerNotification.CATEGORY_CHOICES
        }
        if active_category in valid_categories:
            notifications = notifications.filter(category=active_category)
        else:
            active_category = "all"

        paginator = Paginator(notifications, self.paginate_by)
        page_obj = paginator.get_page(request.GET.get("page"))

        context = {
            "customer": customer,
            "notifications": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            "is_paginated": page_obj.has_other_pages(),
            "active_filter": active_filter,
            "active_category": active_category,
            "category_choices": CustomerNotification.CATEGORY_CHOICES,
            "unread_count": CustomerNotification.objects.filter(
                user=request.user, is_read=False
            ).count(),
            "total_count": CustomerNotification.objects.filter(
                user=request.user
            ).count(),
        }
        return render(request, self.template_name, context)


def _customer_notification_summary_body_max_chars():
    return max(
        int(
            getattr(
                settings,
                "CUSTOMER_NOTIFICATION_SUMMARY_BODY_MAX_CHARS",
                500,
            )
            or 1
        ),
        1,
    )


def _customer_notification_summary_action_url_max_chars():
    return max(
        int(
            getattr(
                settings,
                "CUSTOMER_NOTIFICATION_SUMMARY_ACTION_URL_MAX_CHARS",
                500,
            )
            or 1
        ),
        1,
    )


def _truncate_customer_notification_summary_text(value, max_chars):
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _safe_customer_notification_action_url(request, action_url):
    target_url = str(action_url or "").strip()
    if not target_url or "\x00" in target_url:
        return ""

    target_url = target_url[: _customer_notification_summary_action_url_max_chars()]

    if not url_has_allowed_host_and_scheme(
        url=target_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return ""

    return target_url


def _serialize_customer_notification(notification, request):
    return {
        "id": notification.id,
        "category": notification.category,
        "category_label": notification.get_category_display(),
        "priority": notification.priority,
        "title": _truncate_customer_notification_summary_text(
            notification.title,
            160,
        ),
        "body": _truncate_customer_notification_summary_text(
            notification.body,
            _customer_notification_summary_body_max_chars(),
        ),
        "icon": notification.icon or "fa-regular fa-bell",
        "action_url": _safe_customer_notification_action_url(
            request,
            notification.action_url,
        ),
        "is_read": notification.is_read,
        "created_at": notification.created_at.strftime("%Y-%m-%d %H:%M"),
    }


@login_required
@require_GET
def customer_notifications_summary(request):
    redirect_response = _redirect_if_non_customer_user(request)
    if redirect_response:
        return JsonResponse({"error": "not_customer"}, status=403)

    latest_notifications = CustomerNotification.objects.filter(
        user=request.user
    ).order_by("-created_at", "-id")[:5]

    return JsonResponse(
        {
            "unread_count": CustomerNotification.objects.filter(
                user=request.user, is_read=False
            ).count(),
            "notifications": [
                _serialize_customer_notification(notification, request)
                for notification in latest_notifications
            ],
        }
    )


@require_POST
@login_required
def mark_customer_notification_read(request, notification_id):
    redirect_response = _redirect_if_non_customer_user(request)
    if redirect_response:
        return JsonResponse({"error": "not_customer"}, status=403)

    if _customer_notification_action_payload_too_large(request):
        return JsonResponse({"error": "payload_too_large"}, status=413)

    notification = get_object_or_404(
        CustomerNotification,
        id=notification_id,
        user=request.user,
    )
    notification.mark_as_read()

    return JsonResponse(
        {
            "status": "success",
            "notification_id": notification.id,
            "unread_count": CustomerNotification.objects.filter(
                user=request.user, is_read=False
            ).count(),
        }
    )


@require_POST
@login_required
def mark_all_customer_notifications_read(request):
    redirect_response = _redirect_if_non_customer_user(request)
    if redirect_response:
        return JsonResponse({"error": "not_customer"}, status=403)

    if _customer_notification_action_payload_too_large(request):
        return JsonResponse({"error": "payload_too_large"}, status=413)

    updated = CustomerNotification.objects.filter(
        user=request.user,
        is_read=False,
    ).update(
        is_read=True,
        read_at=timezone.now(),
    )

    return JsonResponse(
        {
            "status": "success",
            "updated": updated,
            "unread_count": CustomerNotification.objects.filter(
                user=request.user,
                is_read=False,
            ).count(),
        }
    )


# ----------------------------------------------------------------------------------------------------
class DeleteAccountView(LoginRequiredMixin, View):
    """Delete user account with multi-step confirmation and operational blockers."""

    template_name = "accounts/delete_account.html"

    def _context(self, request, form):
        user = request.user
        blockers = _get_account_deletion_blockers(user)
        return {
            "form": form,
            "user_email": user.email,
            "deletion_blockers": blockers,
            "can_delete_account": not blockers,
        }

    def get(self, request):
        form = DeleteAccountReasonForm()
        return render(request, self.template_name, self._context(request, form))

    def post(self, request):
        form = DeleteAccountReasonForm(request.POST)
        blockers = _get_account_deletion_blockers(request.user)

        if blockers:
            messages.error(
                request,
                "حذف حساب در حال حاضر ممکن نیست. ابتدا موارد نمایش‌داده‌شده را تعیین تکلیف کنید.",
                "danger",
            )
            return render(request, self.template_name, self._context(request, form))

        if form.is_valid():
            try:
                user = request.user

                if not user.check_password(form.cleaned_data.get("password")):
                    messages.error(request, "رمز عبور صحیح نمی‌باشد", "danger")
                    return render(
                        request, self.template_name, self._context(request, form)
                    )

                _anonymize_account_for_deletion(
                    request,
                    user=user,
                    reason=form.cleaned_data.get("reason"),
                )
                logout(request)

                messages.success(
                    request,
                    "حساب شما غیرفعال و اطلاعات شخصی آن ناشناس‌سازی شد. شماره موبایل قبلی برای ثبت‌نام دوباره آزاد شد.",
                    "success",
                )
                return redirect("accounts:login")

            except Exception as e:
                messages.error(request, f"خطا در حذف حساب: {str(e)}", "danger")

        return render(request, self.template_name, self._context(request, form))
