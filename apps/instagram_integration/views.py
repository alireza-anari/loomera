from django.contrib import messages
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from apps.dashboards.layout import build_dashboard_context

from .models import (
    InstagramAccountConnection,
    InstagramConnectionStatus,
)
from .subscriptions import (
    InstagramWebhookSubscriptionError,
    subscribe_professional_account,
    unsubscribe_professional_account,
)
from .oauth import (
    InstagramOAuthStateError,
    InstagramProviderError,
    build_authorization_url,
    consume_oauth_state,
    exchange_code_for_connection,
    expiry_from_result,
    issue_oauth_state,
    require_messaging_enabled,
    resolve_context_for_user,
)


def _dashboard_url(context):
    if context.kind == "stylist":
        return reverse("dashboards:stylist_dashboard")
    return reverse("dashboards:salon_manager_dashboard")


def _context_connection(context):
    return InstagramAccountConnection.objects.filter(
        salon=context.salon,
        stylist=context.stylist,
    ).first()


@login_required
@require_GET
def connection_settings(request, context_kind, salon_id):
    context_owner = resolve_context_for_user(
        user=request.user,
        salon_id=salon_id,
        context_kind=context_kind,
    )
    connection = _context_connection(context_owner)

    if context_owner.kind == "stylist":
        dashboard_context = build_dashboard_context(
            request.user,
            sidebar_active="my_settings",
            page_title="Instagram و Lumi",
            request_path=request.path,
            role="stylist",
            salon_override=context_owner.salon,
            stylist_override=context_owner.stylist,
        )
        return_url = reverse("dashboards:stylist_settings")
    else:
        dashboard_context = build_dashboard_context(
            request.user,
            nav_active="home",
            sidebar_active="settings",
            page_title="Instagram و Lumi",
            request_path=request.path,
        )
        return_url = reverse("dashboards:workspace_settings")

    feature_ready = bool(
        getattr(settings, "INSTAGRAM_ENABLED", False)
        and getattr(settings, "INSTAGRAM_MESSAGING_ENABLED", False)
    )
    connection_ready = bool(
        connection is not None
        and connection.status == InstagramConnectionStatus.CONNECTED
        and connection.webhook_subscribed_at is not None
        and connection.is_context_active()
    )

    if connection is None:
        status_label = "متصل نشده"
    elif connection_ready:
        status_label = "متصل و آماده دریافت پیام"
    elif connection.status == InstagramConnectionStatus.NEEDS_REAUTH:
        status_label = "نیاز به اتصال مجدد"
    elif connection.status == InstagramConnectionStatus.DISCONNECTED:
        status_label = "قطع شده"
    else:
        status_label = "اتصال نیاز به بررسی دارد"

    dashboard_context.update(
        {
            "hide_dashboard_header": True,
            "hide_dashboard_top_nav": True,
            "instagram_context_kind": context_owner.kind,
            "instagram_salon": context_owner.salon,
            "instagram_stylist": context_owner.stylist,
            "instagram_connection": connection,
            "instagram_connection_ready": connection_ready,
            "instagram_status_label": status_label,
            "instagram_feature_ready": feature_ready,
            "instagram_connect_url": reverse(
                "instagram_integration:oauth_start",
                kwargs={
                    "context_kind": context_owner.kind,
                    "salon_id": context_owner.salon.pk,
                },
            ),
            "instagram_disconnect_url": reverse(
                "instagram_integration:disconnect",
                kwargs={
                    "context_kind": context_owner.kind,
                    "salon_id": context_owner.salon.pk,
                },
            ),
            "instagram_return_url": return_url,
        }
    )
    return render(
        request,
        "instagram_integration/settings.html",
        dashboard_context,
    )


@login_required
@require_GET
def oauth_start(request, context_kind, salon_id):
    require_messaging_enabled()
    context = resolve_context_for_user(
        user=request.user,
        salon_id=salon_id,
        context_kind=context_kind,
    )
    state = issue_oauth_state(request=request, context=context)
    return redirect(build_authorization_url(state=state))


@login_required
@require_GET
@transaction.atomic
def oauth_callback(request):
    state = request.GET.get("state")

    try:
        require_messaging_enabled()
        context = consume_oauth_state(request=request, state=state)
    except InstagramOAuthStateError:
        messages.error(
            request,
            "اتصال اینستاگرام معتبر نیست یا زمان آن تمام شده است. دوباره تلاش کنید.",
        )
        return redirect("dashboards:salon_manager_dashboard")

    target_url = _dashboard_url(context)

    if request.GET.get("error"):
        messages.error(
            request,
            "اتصال اینستاگرام تکمیل نشد. دوباره تلاش کنید.",
        )
        return redirect(target_url)

    code = request.GET.get("code")
    if not code:
        messages.error(
            request,
            "کد اتصال اینستاگرام دریافت نشد. دوباره تلاش کنید.",
        )
        return redirect(target_url)

    try:
        result = exchange_code_for_connection(code=code)

        subscribe_professional_account(
            account_id=result.account_id,
            access_token=result.access_token,
        )

        conflicting = InstagramAccountConnection.objects.filter(
            instagram_account_id=result.account_id,
        ).first()
        expected_stylist_id = (
            context.stylist.pk if context.stylist is not None else None
        )
        if conflicting is not None and (
            conflicting.salon_id != context.salon.pk
            or conflicting.stylist_id != expected_stylist_id
        ):
            raise ValidationError(
                "Instagram account is already connected elsewhere."
            )

        connection = _context_connection(context)
        if connection is None:
            connection = InstagramAccountConnection(
                salon=context.salon,
                stylist=context.stylist,
                instagram_account_id=result.account_id,
            )
        else:
            connection.instagram_account_id = result.account_id

        connection.username = result.username
        connection.granted_scopes = list(result.scopes)
        connection.token_expires_at = expiry_from_result(result)
        connection.set_access_token(result.access_token)
        connection.mark_connected()
        connection.webhook_subscribed_at = timezone.now()
        connection.save()

    except (
        InstagramProviderError,
        InstagramWebhookSubscriptionError,
        ValidationError,
    ):
        messages.error(
            request,
            "اتصال اینستاگرام انجام نشد. تنظیمات حساب یا دسترسی‌های Meta را بررسی کنید.",
        )
        return redirect(target_url)

    messages.success(
        request,
        "حساب اینستاگرام با موفقیت به Loomera متصل شد.",
    )
    return redirect(target_url)


@login_required
@require_POST
def disconnect(request, context_kind, salon_id):
    context = resolve_context_for_user(
        user=request.user,
        salon_id=salon_id,
        context_kind=context_kind,
    )
    connection = _context_connection(context)

    if connection is None:
        messages.info(request, "حساب اینستاگرامی برای قطع اتصال وجود ندارد.")
        return redirect(_dashboard_url(context))

    try:
        token = connection.get_access_token()
    except Exception:
        token = ""

    unsubscribe_professional_account(
        account_id=connection.instagram_account_id,
        access_token=token,
    )
    connection.mark_disconnected()
    connection.webhook_subscribed_at = None
    connection.save()

    messages.success(request, "اتصال اینستاگرام قطع شد.")
    return redirect(_dashboard_url(context))
