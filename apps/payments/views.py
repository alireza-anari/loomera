import logging
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import View, ListView
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from .models import Wallet, WalletTransaction, WalletWithdrawalRequest, Payment
from apps.dashboards.jalali_utils import (
    to_english_digits,
    format_jalali_with_weekday,
    format_time_fa,
)
from .forms import WalletWithdrawalRequestForm
import uuid
from django.db.models import Q
from .gateways import (
    initiate_payment,
    verify_payment,
    get_gateway_mode,
    get_gateway_provider,
)
from apps.accounts.notifications import (
    notify_booking_created,
    notify_payment_failed,
    notify_payment_success,
    notify_wallet_charge,
    notify_wallet_charge_failed,
    notify_wallet_withdraw_cancelled,
    notify_wallet_withdraw_requested,
)
from apps.orders.lifecycle import (
    cancel_order_reminder,
    mark_review_requested,
    notify_manager_and_stylists_for_booking,
    notify_operational_milestone,
    schedule_order_reminder,
)

logger = logging.getLogger(__name__)


def _wallet_operations_enabled() -> bool:
    """Customer wallet charge/withdraw flows stay off while online payment is off."""
    return bool(getattr(settings, "ONLINE_PAYMENT_ENABLED", False))


def _redirect_wallet_operation_disabled(request):
    messages.info(
        request,
        "در نسخه بتا شارژ و برداشت کیف پول فعال نیست و پرداخت فقط در مجموعه انجام می‌شود.",
    )
    return redirect("payments:detail")


def _normalize_amount_input(value):
    raw = to_english_digits(value or "")
    raw = (
        raw.replace(",", "")
        .replace("٬", "")
        .replace(" ", "")
        .replace("تومان", "")
        .strip()
    )
    return "".join(ch for ch in raw if ch.isdigit())


def _find_finalized_booking_conflict(order):
    """Return the first finalized appointment that overlaps this pending online order.

    Online checkout orders are allowed to stay pending without holding the slot.
    The slot is checked again when payment is actually verified; if another
    customer finalized it first, this order must not become active.
    """
    if not order or not getattr(order, "pk", None):
        return None

    from apps.orders.booking_utils import BLOCKING_STATUSES
    from apps.orders.models import OrderDetail

    details = list(
        order.order_details1.select_related("service", "stylist", "salon").order_by(
            "date", "time", "id"
        )
    )
    for detail in details:
        if not detail.stylist_id or not detail.date or not detail.time:
            continue
        booking_end = detail.occupied_until or detail.end_time
        if not booking_end:
            detail.recompute_schedule_snapshots(save=False)
            booking_end = detail.occupied_until or detail.end_time
        if not booking_end:
            continue

        conflict = (
            OrderDetail.objects.select_for_update()
            .filter(
                stylist=detail.stylist,
                date=detail.date,
                time__lt=booking_end,
                end_time__gt=detail.time,
                order__status__in=BLOCKING_STATUSES,
            )
            .filter(Q(order__is_finally=True) | Q(order__is_paid=True))
            .exclude(order=order)
            .select_related("order", "service", "stylist__user")
            .order_by("time", "id")
            .first()
        )
        if conflict:
            return conflict
    return None


# ----------------------------------------------------------------------------------------------------------------------
class WalletDetailView(LoginRequiredMixin, View):
    """نمایش جزئیات کیف پول کاربر و تاریخچه تراکنش‌ها"""

    def get(self, request):
        try:
            # دریافت یا ایجاد کیف پول برای کاربر
            wallet, created = Wallet.objects.get_or_create(user=request.user)

            transactions = list(
                WalletTransaction.objects.filter(wallet=wallet).order_by("-created_at")[
                    :10
                ]
            )

            points_total = 0
            for tx in transactions:
                tx.points_earned = max(int(abs(tx.amount or 0) // 10000), 0)
                points_total += tx.points_earned

            try:
                withdrawal_requests = list(wallet.withdrawal_requests.all()[:5])
            except Exception:
                withdrawal_requests = []
            context = {
                "wallet": wallet,
                "transactions": transactions,
                "withdrawal_requests": withdrawal_requests,
                "created": created,
                "points_total": points_total,
            }

            return render(request, "payments/wallet_detail.html", context)

        except Exception as e:
            logger.error(f"Error in WalletDetailView: {e}")
            messages.error(request, "خطا در بارگذاری اطلاعات کیف پول")
            return redirect("accounts:customer_panel")


# ----------------------------------------------------------------------------------------------------------------------
class WalletChargeView(LoginRequiredMixin, View):
    """شارژ کیف پول کاربر با همان gateway abstraction جدید"""

    def get(self, request):
        if not _wallet_operations_enabled():
            return _redirect_wallet_operation_disabled(request)
        try:
            wallet, _ = Wallet.objects.get_or_create(user=request.user)
            presets = [50000, 100000, 200000, 500000]
            gateway_mode = get_gateway_mode()
            gateway_provider = get_gateway_provider()
            context = {
                "wallet": wallet,
                "presets": presets,
                "gateway_mode": gateway_mode,
                "gateway_provider": (
                    Payment.Provider.MOCK
                    if gateway_mode == "mock"
                    else gateway_provider
                ),
            }
            return render(request, "payments/wallet_charge.html", context)
        except Exception as e:
            logger.error("Error in WalletChargeView GET: %s", e)
            messages.error(request, "خطا در بارگذاری صفحه شارژ")
            return redirect("payments:detail")

    def post(self, request):
        if not _wallet_operations_enabled():
            return _redirect_wallet_operation_disabled(request)
        try:
            amount_str = request.POST.get("amount", "")
            amount_cleaned = _normalize_amount_input(amount_str)

            if not amount_cleaned:
                messages.error(request, "لطفاً مبلغ مورد نظر را وارد کنید")
                return redirect("payments:charge")

            try:
                amount = int(amount_cleaned)
                if amount < 10000:
                    messages.error(request, "حداقل مبلغ شارژ 10,000 تومان است")
                    return redirect("payments:charge")
                if amount > 50000000:
                    messages.error(request, "حداکثر مبلغ شارژ 50,000,000 تومان است")
                    return redirect("payments:charge")
            except (ValueError, TypeError):
                messages.error(request, "مبلغ وارد شده معتبر نیست")
                return redirect("payments:charge")

            gateway_mode = get_gateway_mode()
            gateway_provider = get_gateway_provider()
            payment = Payment.objects.create(
                customer=request.user.customer_profile,
                amount=amount,
                description=f"شارژ کیف پول کاربر {request.user.name}",
                is_finally=False,
                provider=(
                    Payment.Provider.MOCK
                    if gateway_mode == "mock"
                    else gateway_provider
                ),
                purpose=Payment.Purpose.WALLET,
                state=Payment.State.PENDING,
                sandbox_mode=(gateway_mode != "live"),
                callback_token=uuid.uuid4().hex,
                idempotency_key=uuid.uuid4().hex,
                meta={
                    "source": "wallet_charge",
                    "customer_mobile": getattr(request.user, "mobile_number", ""),
                },
            )

            gateway_result = initiate_payment(
                request=request,
                payment=payment,
                amount_toman=amount,
                description=payment.description,
                mobile_number=getattr(request.user, "mobile_number", ""),
            )

            if not gateway_result.success or not gateway_result.payment_url:
                payment.mark_failure(
                    status_code=gateway_result.code or -2,
                    meta={
                        "request_error_message": gateway_result.message,
                        "request_payload": gateway_result.raw or {},
                    },
                )
                notify_wallet_charge_failed(
                    customer=payment.customer,
                    payment=payment,
                    amount=amount,
                    title="شروع پرداخت شارژ ناموفق بود",
                )
                messages.error(
                    request, gateway_result.message or "شروع پرداخت ناموفق بود."
                )
                return redirect("payments:charge")

            payment.gateway_track_id = gateway_result.track_id
            payment.status_code = gateway_result.code or 100
            payment.meta = {**(payment.meta or {}), "request": gateway_result.raw or {}}
            payment.save(
                update_fields=["gateway_track_id", "status_code", "meta", "update_date"]
            )

            return redirect(gateway_result.payment_url)

        except Exception as e:
            logger.error("Error in WalletChargeView POST: %s", e, exc_info=True)
            messages.error(request, "خطا در پردازش درخواست شارژ")
            return redirect("payments:charge")


# ----------------------------------------------------------------------------------------------------------------------
class WalletChargeVerifyView(View):
    """تایید پرداخت شارژ کیف پول با معماری جدید gateway"""

    def get(self, request, payment_id, token):
        payment = get_object_or_404(
            Payment.objects.select_related("customer__user"),
            id=payment_id,
            callback_token=token,
            purpose=Payment.Purpose.WALLET,
        )

        if payment.state == Payment.State.SUCCESS and payment.is_finally:
            messages.success(request, "این پرداخت قبلاً با موفقیت تایید شده است.")
            return redirect("payments:detail")

        track_id = str(
            request.GET.get("trackId")
            or request.GET.get("Authority")
            or payment.gateway_track_id
            or ""
        ).strip()

        callback_status = (
            str(
                request.GET.get("status")
                or request.GET.get("Status")
                or request.GET.get("success")
                or ""
            )
            .strip()
            .lower()
        )

        if not track_id:
            logger.warning(
                "Wallet callback missing track id | payment=%s | state=%s",
                payment.pk,
                payment.state,
            )
            with transaction.atomic():
                locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
                if not (
                    locked_payment.state == Payment.State.SUCCESS
                    and locked_payment.is_finally
                ):
                    locked_payment.mark_failure(
                        state=Payment.State.FAILED,
                        status_code=-10,
                        meta={"callback": dict(request.GET)},
                    )
            notify_wallet_charge_failed(
                customer=payment.customer,
                payment=payment,
                title="کد رهگیری شارژ کیف پول معتبر نبود",
            )
            messages.error(request, "کد رهگیری پرداخت معتبر نبود.")
            return redirect("payments:detail")

        cancelled_markers = {
            "0",
            "-1",
            "cancel",
            "canceled",
            "cancelled",
            "nok",
            "false",
        }
        if callback_status in cancelled_markers:
            logger.warning(
                "Wallet callback cancelled by user | "
                "payment=%s | callback_status=%s",
                payment.pk,
                callback_status,
            )
            with transaction.atomic():
                locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
                if not (
                    locked_payment.state == Payment.State.SUCCESS
                    and locked_payment.is_finally
                ):
                    locked_payment.mark_failure(
                        state=Payment.State.CANCELLED,
                        status_code=-1,
                        meta={"callback": dict(request.GET)},
                    )
            notify_wallet_charge_failed(
                customer=payment.customer,
                payment=payment,
                title="پرداخت شارژ کیف پول لغو شد",
            )
            messages.warning(request, "پرداخت شارژ کیف پول لغو شد.")
            return redirect("payments:charge")

        result = verify_payment(payment=payment, track_id=track_id)

        if result.success:
            with transaction.atomic():
                locked_payment = (
                    Payment.objects.select_for_update()
                    .select_related("customer__user")
                    .get(pk=payment.pk)
                )

                if (
                    locked_payment.state == Payment.State.SUCCESS
                    and locked_payment.is_finally
                ):
                    messages.success(
                        request, "این پرداخت قبلاً با موفقیت تایید شده است."
                    )
                    return redirect("payments:detail")

                locked_payment.mark_success(
                    ref_id=result.ref_id or locked_payment.ref_id or track_id,
                    track_id=result.track_id or track_id,
                    status_code=result.code or 100,
                    meta={
                        "card_number": result.card_number,
                        "verify": result.raw or {},
                        "source": "wallet_charge",
                    },
                )

                wallet, _ = Wallet.objects.select_for_update().get_or_create(
                    user=locked_payment.customer.user
                )
                wallet.deposit(
                    amount=int(locked_payment.amount),
                    description=f"شارژ کیف پول از درگاه پرداخت - کد پرداخت: {locked_payment.id}",
                )
                transaction.on_commit(
                    lambda payment=locked_payment: notify_wallet_charge(
                        customer=payment.customer,
                        payment=payment,
                        amount=int(payment.amount),
                    )
                )

            messages.success(
                request, f"کیف پول شما با مبلغ {payment.amount:,} تومان شارژ شد"
            )
            return redirect("payments:detail")

        if result.retryable or result.requires_review:
            log_method = logger.error if result.requires_review else logger.warning

            log_method(
                "Wallet callback verify pending | "
                "payment=%s | track_id=%s | code=%s | "
                "retryable=%s | requires_review=%s | "
                "integrity_errors=%s | message=%s",
                payment.pk,
                track_id,
                result.code,
                result.retryable,
                result.requires_review,
                ",".join(result.integrity_errors),
                result.message or "",
            )

            with transaction.atomic():
                locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)

                if (
                    locked_payment.state
                    in {
                        Payment.State.INITIATED,
                        Payment.State.PENDING,
                    }
                    and not locked_payment.is_finally
                ):
                    locked_payment.mark_pending(
                        status_code=result.code,
                        meta={
                            "verify": result.raw or {},
                            "callback": dict(request.GET),
                            "verify_pending": {
                                "retryable": bool(result.retryable),
                                "requires_review": bool(result.requires_review),
                                "integrity_errors": list(result.integrity_errors),
                                "message": result.message or "",
                            },
                        },
                    )

            messages.warning(
                request,
                "نتیجه قطعی پرداخت هنوز قابل تأیید نیست. "
                "لطفاً دوباره پرداخت نکنید؛ "
                "وضعیت تراکنش در حال بررسی است.",
            )

            return redirect("payments:detail")

        logger.warning(
            "Wallet callback verify failed | payment=%s | track_id=%s | code=%s | message=%s",
            payment.pk,
            track_id,
            result.code,
            result.message or "",
        )
        with transaction.atomic():
            locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if not (
                locked_payment.state == Payment.State.SUCCESS
                and locked_payment.is_finally
            ):
                locked_payment.mark_failure(
                    status_code=result.code or -2,
                    meta={"verify": result.raw or {}, "callback": dict(request.GET)},
                )
        notify_wallet_charge_failed(
            customer=payment.customer,
            payment=payment,
            title="تأیید شارژ کیف پول ناموفق بود",
        )
        messages.error(
            request, result.message or "تایید پرداخت شارژ کیف پول ناموفق بود."
        )
        return redirect("payments:detail")


# ----------------------------------------------------------------------------------------------------------------------
class WalletWithdrawView(LoginRequiredMixin, View):
    template_name = "payments/wallet_withdraw.html"

    def get(self, request):
        if not _wallet_operations_enabled():
            return _redirect_wallet_operation_disabled(request)
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        form = WalletWithdrawalRequestForm()

        try:
            recent_requests = wallet.withdrawal_requests.all()[:10]
        except Exception:
            recent_requests = []
        return render(
            request,
            self.template_name,
            {
                "wallet": wallet,
                "form": form,
                "recent_requests": recent_requests,
                "min_amount": int(
                    getattr(settings, "WALLET_WITHDRAW_MIN_AMOUNT", 50000) or 50000
                ),
                "max_amount": int(
                    getattr(settings, "WALLET_WITHDRAW_MAX_AMOUNT", 50000000)
                    or 50000000
                ),
            },
        )

    def post(self, request):
        if not _wallet_operations_enabled():
            return _redirect_wallet_operation_disabled(request)
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        form = WalletWithdrawalRequestForm(request.POST)

        try:
            recent_requests = wallet.withdrawal_requests.all()[:10]
        except Exception:
            recent_requests = []
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    "wallet": wallet,
                    "form": form,
                    "recent_requests": recent_requests,
                    "min_amount": int(
                        getattr(settings, "WALLET_WITHDRAW_MIN_AMOUNT", 50000) or 50000
                    ),
                    "max_amount": int(
                        getattr(settings, "WALLET_WITHDRAW_MAX_AMOUNT", 50000000)
                        or 50000000
                    ),
                },
            )

        amount = int(form.cleaned_data["amount"])
        try:
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
                wallet.withdraw(
                    amount=amount,
                    description="ثبت درخواست برداشت از کیف پول",
                    transaction_type=WalletTransaction.TransactionType.WITHDRAW,
                )
                withdrawal_request = WalletWithdrawalRequest.objects.create(
                    wallet=wallet,
                    amount=amount,
                    iban=form.cleaned_data["iban"],
                    legacy_destination_iban=form.cleaned_data["iban"],
                    account_holder_name=form.cleaned_data["account_holder_name"],
                    legacy_destination_account_holder_name=form.cleaned_data[
                        "account_holder_name"
                    ],
                    bank_name=form.cleaned_data.get("bank_name", ""),
                    legacy_destination_bank_name=form.cleaned_data.get("bank_name", ""),
                    note="در انتظار بررسی تیم مالی",
                )
                transaction.on_commit(
                    lambda withdrawal=withdrawal_request, amount=amount, user=request.user: notify_wallet_withdraw_requested(
                        user=user,
                        withdrawal=withdrawal,
                        amount=amount,
                    )
                )
        except ValidationError as exc:
            form.add_error("amount", str(exc))
            return render(
                request,
                self.template_name,
                {
                    "wallet": wallet,
                    "form": form,
                    "recent_requests": recent_requests,
                    "min_amount": int(
                        getattr(settings, "WALLET_WITHDRAW_MIN_AMOUNT", 50000) or 50000
                    ),
                    "max_amount": int(
                        getattr(settings, "WALLET_WITHDRAW_MAX_AMOUNT", 50000000)
                        or 50000000
                    ),
                },
            )

        logger.info(
            "Wallet withdrawal requested | user=%s | wallet=%s | amount=%s",
            request.user.pk,
            wallet.pk,
            amount,
        )
        messages.success(
            request, "درخواست برداشت شما ثبت شد و پس از بررسی مالی پیگیری می‌شود."
        )
        return redirect("payments:detail")


# ----------------------------------------------------------------------------------------------------------------------
class WalletWithdrawalCancelView(LoginRequiredMixin, View):
    def post(self, request, request_id):
        if not _wallet_operations_enabled():
            return _redirect_wallet_operation_disabled(request)
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        withdraw_request = get_object_or_404(
            WalletWithdrawalRequest.objects.select_related("wallet", "wallet__user"),
            pk=request_id,
            wallet=wallet,
        )
        try:
            withdraw_request.cancel(
                note="درخواست برداشت توسط کاربر لغو شد و مبلغ به کیف پول برگشت داده شد."
            )
        except ValidationError as exc:
            messages.error(request, str(exc))
        else:
            logger.info(
                "Wallet withdrawal cancelled | user=%s | request=%s | wallet=%s",
                request.user.pk,
                withdraw_request.pk,
                wallet.pk,
            )
            notify_wallet_withdraw_cancelled(
                user=request.user,
                withdrawal=withdraw_request,
                amount=int(withdraw_request.amount or 0),
            )
            messages.success(
                request, "درخواست برداشت لغو شد و مبلغ به کیف پول شما برگشت داده شد."
            )

        next_url = (request.POST.get("next") or "").strip()
        if next_url:
            return redirect(next_url)
        return redirect("payments:detail")


# ----------------------------------------------------------------------------------------------------------------------
class WalletTransactionsView(LoginRequiredMixin, ListView):
    """نمایش تاریخچه کامل تراکنش‌های کیف پول"""

    model = WalletTransaction
    template_name = "payments/wallet_transactions.html"
    context_object_name = "transactions"
    paginate_by = 20

    def get_queryset(self):
        """فیلتر تراکنش‌ها بر اساس کاربر فعلی"""
        try:
            wallet = Wallet.objects.get(user=self.request.user)
            return WalletTransaction.objects.filter(wallet=wallet).order_by(
                "-created_at"
            )
        except Wallet.DoesNotExist:
            return WalletTransaction.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            wallet, created = Wallet.objects.get_or_create(user=self.request.user)
            context["wallet"] = wallet
        except Exception as e:
            logger.error(f"Error getting wallet in transactions view: {e}")
        return context


# ----------------------------------------------------------------------------------------------------------------------
# Appointment payment flow (Zibal-ready / mock-first)
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .gateways import verify_payment
from .finance import cancel_order_with_financials, sync_settlement_for_order


class MockGatewayView(View):
    template_name = "payments/mock_gateway.html"

    def get(self, request, payment_id, token):
        payment = get_object_or_404(
            Payment.objects.select_related("order", "order__salon", "customer__user"),
            id=payment_id,
            callback_token=token,
        )
        if payment.state == Payment.State.SUCCESS:
            return redirect(
                "payments:appointment_result",
                payment_id=payment.id,
                token=payment.callback_token,
            )
        context = {"payment": payment, "order": payment.order}
        return render(request, self.template_name, context)


class MockGatewayCompleteView(View):
    def post(self, request, payment_id, token):
        payment = get_object_or_404(
            Payment,
            id=payment_id,
            callback_token=token,
        )

        action = (request.POST.get("action") or "success").strip().lower()

        if action not in {"success", "cancel", "fail"}:
            action = "success"

        payment.meta = {
            **(payment.meta or {}),
            "mock_gateway_action": action,
        }
        payment.save(update_fields=["meta", "update_date"])

        if payment.purpose == Payment.Purpose.WALLET:
            verify_url = reverse(
                "payments:charge_verify",
                kwargs={
                    "payment_id": payment.id,
                    "token": token,
                },
            )
        else:
            verify_url = reverse(
                "payments:appointment_verify",
                kwargs={
                    "payment_id": payment.id,
                    "token": token,
                },
            )

        track_id = payment.gateway_track_id or f"mock-{payment.id}"

        params = f"?trackId={track_id}&success=1&status=2"

        if action == "cancel":
            params = f"?trackId={track_id}&success=0&status=0"

        elif action == "fail":
            params = f"?trackId={track_id}&status=2"

        return redirect(f"{verify_url}{params}")


@method_decorator(csrf_exempt, name="dispatch")
class AppointmentPaymentVerifyView(View):
    def get(self, request, payment_id, token):
        payment = get_object_or_404(
            Payment.objects.select_related("order", "order__customer", "order__salon"),
            id=payment_id,
            callback_token=token,
            purpose=Payment.Purpose.APPOINTMENT,
        )

        if payment.state == Payment.State.SUCCESS and payment.is_finally:
            logger.info(
                "Appointment callback duplicate success | payment=%s | order=%s",
                payment.pk,
                payment.order_id,
            )
            return redirect(
                "payments:appointment_result",
                payment_id=payment.id,
                token=payment.callback_token,
            )

        track_id = str(
            request.GET.get("trackId")
            or request.GET.get("Authority")
            or payment.gateway_track_id
            or ""
        ).strip()
        callback_status = (
            str(
                request.GET.get("status")
                or request.GET.get("Status")
                or request.GET.get("success")
                or ""
            )
            .strip()
            .lower()
        )
        callback_meta = {"callback": dict(request.GET)}

        if not track_id:
            logger.warning(
                "Appointment callback missing track id | " "payment=%s | state=%s",
                payment.pk,
                payment.state,
            )
            with transaction.atomic():
                locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
                if not (
                    locked_payment.state == Payment.State.SUCCESS
                    and locked_payment.is_finally
                ):
                    locked_payment.mark_failure(
                        state=Payment.State.FAILED,
                        status_code=-10,
                        meta=callback_meta,
                    )
                    if locked_payment.order_id:
                        if (locked_payment.meta or {}).get(
                            "source"
                        ) == "pay_in_salon_online":
                            order = locked_payment.order
                            order.selected_payment_method = "pay_in_salon"
                            order.status = (
                                "completed"
                                if (
                                    order.service_completed_at
                                    or order.status == "completed"
                                )
                                else order.status
                            )
                            order.save(
                                update_fields=[
                                    "selected_payment_method",
                                    "status",
                                    "update_date",
                                ]
                            )
                            sync_settlement_for_order(order, payment=locked_payment)
                        else:
                            cancel_order_with_financials(
                                order=locked_payment.order,
                                reason="کال‌بک پرداخت بدون کد رهگیری",
                                refund_reason="پرداخت نامعتبر",
                                payment=locked_payment,
                            )
            notify_payment_failed(
                customer=payment.customer,
                payment=payment,
                order=payment.order,
                action_url=reverse(
                    "payments:appointment_result",
                    kwargs={"payment_id": payment.id, "token": payment.callback_token},
                ),
                title="کد رهگیری پرداخت نامعتبر بود",
            )
            messages.error(request, "کد رهگیری پرداخت نامعتبر بود.")
            return redirect(
                "payments:appointment_result",
                payment_id=payment.id,
                token=payment.callback_token,
            )

        cancelled_markers = {
            "0",
            "-1",
            "cancel",
            "canceled",
            "cancelled",
            "nok",
            "false",
        }
        if callback_status in cancelled_markers:
            logger.warning(
                "Appointment callback cancelled by user | "
                "payment=%s | callback_status=%s",
                payment.pk,
                callback_status,
            )
            with transaction.atomic():
                locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
                if not (
                    locked_payment.state == Payment.State.SUCCESS
                    and locked_payment.is_finally
                ):
                    locked_payment.mark_failure(
                        state=Payment.State.CANCELLED,
                        status_code=-1,
                        meta=callback_meta,
                    )
                    if locked_payment.order_id:
                        if (locked_payment.meta or {}).get(
                            "source"
                        ) == "pay_in_salon_online":
                            order = locked_payment.order
                            order.selected_payment_method = "pay_in_salon"
                            order.status = (
                                "completed"
                                if (
                                    order.service_completed_at
                                    or order.status == "completed"
                                )
                                else order.status
                            )
                            order.save(
                                update_fields=[
                                    "selected_payment_method",
                                    "status",
                                    "update_date",
                                ]
                            )
                            sync_settlement_for_order(order, payment=locked_payment)
                        else:
                            cancel_order_with_financials(
                                order=locked_payment.order,
                                reason="لغو پرداخت توسط کاربر",
                                refund_reason="لغو پرداخت",
                                payment=locked_payment,
                            )
            notify_payment_failed(
                customer=payment.customer,
                payment=payment,
                order=payment.order,
                action_url=reverse(
                    "payments:appointment_result",
                    kwargs={"payment_id": payment.id, "token": payment.callback_token},
                ),
                title="پرداخت لغو شد",
            )
            messages.warning(request, "پرداخت شما لغو شد.")
            return redirect(
                "payments:appointment_result",
                payment_id=payment.id,
                token=payment.callback_token,
            )

        result = verify_payment(payment=payment, track_id=track_id)
        if result.success:
            logger.info(
                "Appointment callback verify success | payment=%s | order=%s | track_id=%s | ref_id=%s",
                payment.pk,
                payment.order_id,
                track_id,
                result.ref_id or "",
            )
            abandoned_meta = payment.meta or {}
            abandoned_checkout = abandoned_meta.get("abandoned_checkout") or {}

            if (
                payment.order_id
                and payment.order
                and payment.order.status == "cancelled"
                and abandoned_checkout.get("expired")
            ):
                logger.error(
                    "Late successful payment for expired checkout | "
                    "payment=%s | order=%s | track_id=%s | ref_id=%s",
                    payment.pk,
                    payment.order_id,
                    track_id,
                    result.ref_id or "",
                )

                with transaction.atomic():
                    locked_payment = (
                        Payment.objects.select_for_update(of=("self",))
                        .select_related("order")
                        .get(pk=payment.pk)
                    )

                    if not (
                        locked_payment.state == Payment.State.SUCCESS
                        and locked_payment.is_finally
                    ):
                        locked_payment.mark_pending(
                            status_code=result.code,
                            meta={
                                "verify": result.raw or {},
                                "callback": dict(request.GET),
                                "verify_pending": {
                                    "retryable": False,
                                    "requires_review": True,
                                    "integrity_errors": [
                                        "late_success_after_abandoned_checkout"
                                    ],
                                    "message": (
                                        "پرداخت پس از پایان مهلت رزرو "
                                        "به callback برگشته است."
                                    ),
                                    "checked_at": timezone.now().isoformat(),
                                },
                            },
                        )

                messages.warning(
                    request,
                    "پرداخت پس از پایان مهلت رزرو برگشته است و برای "
                    "جلوگیری از رزرو اشتباه، نیازمند بررسی پشتیبانی است.",
                )

                return redirect(
                    "payments:appointment_result",
                    payment_id=payment.id,
                    token=payment.callback_token,
                )
            with transaction.atomic():
                locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
                if not (
                    locked_payment.state == Payment.State.SUCCESS
                    and locked_payment.is_finally
                ):
                    locked_payment.mark_success(
                        ref_id=result.ref_id or locked_payment.ref_id or track_id,
                        track_id=result.track_id or track_id,
                        status_code=result.code or 100,
                        meta={
                            "card_number": result.card_number,
                            "verify": result.raw or {},
                        },
                    )
                    if locked_payment.order_id:
                        order = locked_payment.order
                        conflict = _find_finalized_booking_conflict(order)
                        if conflict:
                            order.is_paid = True
                            order.checkout_locked_at = timezone.now()
                            order.save(
                                update_fields=[
                                    "is_paid",
                                    "checkout_locked_at",
                                    "update_date",
                                ]
                            )

                            cancel_order_with_financials(
                                order=order,
                                reason="زمان رزرو قبل از تکمیل پرداخت توسط کاربر دیگری نهایی شد",
                                refund_reason="عدم دسترسی زمان انتخاب‌شده",
                                payment=locked_payment,
                            )
                            cancel_order_reminder(order)
                            transaction.on_commit(
                                lambda order=order, payment=locked_payment: notify_payment_failed(
                                    customer=order.customer,
                                    payment=payment,
                                    order=order,
                                    action_url=reverse(
                                        "payments:appointment_result",
                                        kwargs={
                                            "payment_id": payment.id,
                                            "token": payment.callback_token,
                                        },
                                    ),
                                    title="زمان رزرو دیگر آزاد نیست",
                                )
                            )
                            messages.error(
                                request,
                                "پرداخت دریافت شد، اما این زمان قبل از نهایی‌شدن پرداخت توسط کاربر دیگری رزرو شده بود. سفارش لغو شد و مبلغ طبق قوانین پرداخت به کیف پول/مسیر بازگشت وجه منتقل می‌شود. لطفاً زمان دیگری انتخاب کنید.",
                            )
                            return redirect(
                                "payments:appointment_result",
                                payment_id=payment.id,
                                token=payment.callback_token,
                            )

                        order.is_paid = True
                        order.is_finally = True
                        order.status = (
                            "completed"
                            if (
                                order.service_completed_at
                                or order.status == "completed"
                            )
                            else "paid"
                        )
                        order.checkout_locked_at = timezone.now()
                        order.save(
                            update_fields=[
                                "is_paid",
                                "is_finally",
                                "status",
                                "checkout_locked_at",
                                "update_date",
                            ]
                        )
                        sync_settlement_for_order(order, payment=locked_payment)
                        if order.service_completed_at or order.status == "completed":
                            notify_operational_milestone(
                                order,
                                event_type="payment_completed",
                                title="پرداخت رزرو نهایی شد",
                                body="پرداخت رزرو ثبت شد و مسیر ثبت دیدگاه برای مشتری فعال است.",
                            )
                            mark_review_requested(order)
                        else:
                            schedule_order_reminder(order)
                            notify_manager_and_stylists_for_booking(
                                order, event_type="booking_paid"
                            )
                        transaction.on_commit(
                            lambda order=order: notify_booking_created(
                                customer=order.customer,
                                order=order,
                            )
                        )
                        transaction.on_commit(
                            lambda order=order, payment=locked_payment: notify_payment_success(
                                customer=order.customer,
                                payment=payment,
                                order=order,
                            )
                        )
            messages.success(request, "پرداخت رزرو با موفقیت تایید شد.")
        elif result.retryable or result.requires_review:
            log_method = logger.error if result.requires_review else logger.warning

            log_method(
                "Appointment callback verify pending | "
                "payment=%s | order=%s | track_id=%s | "
                "code=%s | retryable=%s | "
                "requires_review=%s | integrity_errors=%s | "
                "message=%s",
                payment.pk,
                payment.order_id,
                track_id,
                result.code,
                result.retryable,
                result.requires_review,
                ",".join(result.integrity_errors),
                result.message or "",
            )

            with transaction.atomic():
                locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)

                if (
                    locked_payment.state
                    in {
                        Payment.State.INITIATED,
                        Payment.State.PENDING,
                    }
                    and not locked_payment.is_finally
                ):
                    locked_payment.mark_pending(
                        status_code=result.code,
                        meta={
                            "verify": result.raw or {},
                            **callback_meta,
                            "verify_pending": {
                                "retryable": bool(result.retryable),
                                "requires_review": bool(result.requires_review),
                                "integrity_errors": list(result.integrity_errors),
                                "message": result.message or "",
                            },
                        },
                    )

            messages.warning(
                request,
                "نتیجه قطعی پرداخت هنوز قابل تأیید نیست. "
                "لطفاً دوباره پرداخت نکنید؛ "
                "وضعیت تراکنش در حال بررسی است.",
            )

        else:
            logger.warning(
                "Appointment callback verify failed | "
                "payment=%s | order=%s | track_id=%s | code=%s | message=%s",
                payment.pk,
                payment.order_id,
                track_id,
                result.code,
                result.message or "",
            )
            with transaction.atomic():
                locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
                if not (
                    locked_payment.state == Payment.State.SUCCESS
                    and locked_payment.is_finally
                ):
                    locked_payment.mark_failure(
                        status_code=result.code or -2,
                        meta={"verify": result.raw or {}, **callback_meta},
                    )
                    if locked_payment.order_id:
                        if (locked_payment.meta or {}).get(
                            "source"
                        ) == "pay_in_salon_online":
                            order = locked_payment.order
                            order.selected_payment_method = "pay_in_salon"
                            order.status = (
                                "completed"
                                if (
                                    order.service_completed_at
                                    or order.status == "completed"
                                )
                                else order.status
                            )
                            order.save(
                                update_fields=[
                                    "selected_payment_method",
                                    "status",
                                    "update_date",
                                ]
                            )
                            sync_settlement_for_order(order, payment=locked_payment)
                        else:
                            cancel_order_with_financials(
                                order=locked_payment.order,
                                reason="تایید پرداخت ناموفق بود",
                                refund_reason="تایید ناموفق پرداخت",
                                payment=locked_payment,
                            )
            notify_payment_failed(
                customer=payment.customer,
                payment=payment,
                order=payment.order,
                action_url=reverse(
                    "payments:appointment_result",
                    kwargs={"payment_id": payment.id, "token": payment.callback_token},
                ),
                title="تأیید پرداخت ناموفق بود",
            )
            messages.error(request, result.message or "تایید پرداخت ناموفق بود.")

        return redirect(
            "payments:appointment_result",
            payment_id=payment.id,
            token=payment.callback_token,
        )


def _appointment_payment_pending_review_context(payment):
    verify_pending = {}
    meta = payment.meta or {}
    raw_verify_pending = meta.get("verify_pending")
    if isinstance(raw_verify_pending, dict):
        verify_pending = raw_verify_pending

    is_pending_review = (
        payment.state in {Payment.State.INITIATED, Payment.State.PENDING}
        and not payment.is_finally
    )

    requires_review = bool(verify_pending.get("requires_review"))
    retryable = bool(verify_pending.get("retryable"))
    message = str(verify_pending.get("message") or "").strip()

    if requires_review:
        title = "پرداخت نیاز به بررسی دارد"
        body = (
            "اطلاعات برگشتی درگاه با اطلاعات سفارش کاملاً منطبق نبود. "
            "برای امنیت مالی، وضعیت تراکنش در حال بررسی است."
        )
    else:
        title = "نتیجه پرداخت هنوز قطعی نیست"
        body = (
            "وضعیت این تراکنش هنوز نهایی نشده است. "
            "ممکن است تراکنش توسط بانک یا درگاه پردازش شده باشد، اما نتیجه قطعی هنوز برای لومرا مشخص نیست."
        )

    if retryable:
        body = (
            "ارتباط با درگاه برای تأیید نهایی کامل نشد. "
            "ممکن است تراکنش توسط بانک پردازش شده باشد، اما نتیجه قطعی هنوز به لومرا نرسیده است."
        )

    if message:
        body = f"{body} پیام ثبت‌شده: {message}"

    return {
        "is_active": is_pending_review,
        "requires_review": requires_review,
        "retryable": retryable,
        "title": title,
        "body": body,
        "primary_hint": "لطفاً دوباره پرداخت نکنید تا وضعیت همین تراکنش مشخص شود.",
        "secondary_hint": (
            "اگر مبلغ از حساب شما کسر شده باشد، نتیجه پس از بررسی درگاه یا بررسی خودکار تراکنش مشخص می‌شود."
        ),
    }


def _appointment_payment_expired_checkout_context(payment):
    meta = payment.meta or {}
    abandoned_checkout = meta.get("abandoned_checkout")
    if not isinstance(abandoned_checkout, dict):
        abandoned_checkout = {}

    is_expired = payment.state == Payment.State.CANCELLED and bool(
        abandoned_checkout.get("expired")
    )

    return {
        "is_active": is_expired,
        "reason": str(abandoned_checkout.get("reason") or "").strip(),
        "expired_at": str(abandoned_checkout.get("expired_at") or "").strip(),
        "title": "مهلت پرداخت به پایان رسید",
        "body": (
            "چون پرداخت آنلاین در زمان مجاز کامل نشد، رزرو از حالت انتظار خارج شد "
            "و زمان انتخاب‌شده دوباره آزاد شده است."
        ),
        "primary_hint": "برای رزرو این خدمت، لطفاً یک زمان آزاد جدید انتخاب کنید.",
        "secondary_hint": (
            "اگر مبلغی از حساب شما کسر شده باشد، وضعیت آن از طریق پشتیبانی یا بررسی خودکار تراکنش قابل پیگیری است."
        ),
    }


class AppointmentPaymentResultView(View):
    template_name = "payments/appointment_result.html"

    def get(self, request, payment_id, token):
        payment = get_object_or_404(
            Payment.objects.select_related("order", "order__salon", "customer__user"),
            id=payment_id,
            callback_token=token,
            purpose=Payment.Purpose.APPOINTMENT,
        )
        order = payment.order
        settlement = getattr(order, "salon_settlement", None) if order else None
        grouped_days = []
        is_split_day_booking = False
        if order:
            day_map = {}
            order_items = sorted(
                order.order_details1.all(),
                key=lambda item: (item.date, item.time, item.pk),
            )
            for item in order_items:
                bucket = day_map.setdefault(
                    item.date,
                    {
                        "date": (
                            format_jalali_with_weekday(item.date) if item.date else ""
                        ),
                        "service_count": 0,
                        "start": item.time,
                        "end": item.end_time or item.time,
                    },
                )
                bucket["service_count"] += 1
                if item.time and bucket["start"] and item.time < bucket["start"]:
                    bucket["start"] = item.time
                if (
                    (item.end_time or item.time)
                    and bucket["end"]
                    and (item.end_time or item.time) > bucket["end"]
                ):
                    bucket["end"] = item.end_time or item.time
            grouped_days = [
                {
                    "date": bucket["date"],
                    "service_count": bucket["service_count"],
                    "time_label": (
                        f"{format_time_fa(bucket['start'])} تا {format_time_fa(bucket['end'])}"
                        if bucket["start"] and bucket["end"]
                        else ""
                    ),
                }
                for _, bucket in sorted(day_map.items(), key=lambda item: item[0])
            ]
            is_split_day_booking = len(grouped_days) > 1

        payment_source = ((payment.meta or {}).get("source") or "").strip()
        is_pay_in_salon_followup = payment_source == "pay_in_salon_online"
        pay_in_salon_online_failed = is_pay_in_salon_followup and payment.state in {
            Payment.State.FAILED,
            Payment.State.CANCELLED,
        }
        pending_review_context = _appointment_payment_pending_review_context(payment)
        expired_checkout_context = _appointment_payment_expired_checkout_context(
            payment
        )
        context = {
            "payment": payment,
            "order": order,
            "settlement": settlement,
            "is_success": payment.state == Payment.State.SUCCESS,
            "is_cancelled": (
                payment.state == Payment.State.CANCELLED
                and not expired_checkout_context["is_active"]
            ),
            "is_payment_pending_review": pending_review_context["is_active"],
            "payment_pending_requires_review": pending_review_context[
                "requires_review"
            ],
            "payment_pending_retryable": pending_review_context["retryable"],
            "payment_pending_title": pending_review_context["title"],
            "payment_pending_body": pending_review_context["body"],
            "payment_pending_primary_hint": pending_review_context["primary_hint"],
            "payment_pending_secondary_hint": pending_review_context["secondary_hint"],
            "refund_amount": (
                int(getattr(order, "refunded_to_wallet_amount", 0) or 0) if order else 0
            ),
            "refund_time": (
                getattr(order, "refunded_to_wallet_at", None) if order else None
            ),
            "payment_status_label": payment.get_state_display(),
            "order_status_label": order.get_status_display() if order else "—",
            "grouped_days": grouped_days,
            "is_split_day_booking": is_split_day_booking,
            "is_pay_in_salon_followup": is_pay_in_salon_followup,
            "pay_in_salon_online_failed": pay_in_salon_online_failed,
            "is_expired_checkout": expired_checkout_context["is_active"],
            "expired_checkout_reason": expired_checkout_context["reason"],
            "expired_checkout_title": expired_checkout_context["title"],
            "expired_checkout_body": expired_checkout_context["body"],
            "expired_checkout_primary_hint": expired_checkout_context["primary_hint"],
            "expired_checkout_secondary_hint": expired_checkout_context[
                "secondary_hint"
            ],
        }
        return render(request, self.template_name, context)
