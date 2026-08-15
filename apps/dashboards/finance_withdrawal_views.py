from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.dashboards.finance_cost_views import _SalonFinanceOperationMixin, _money
from apps.dashboards.finance_withdrawal_forms import StylistWithdrawalRequestForm
from apps.dashboards.layout import build_dashboard_context
from apps.payments.models import (
    OrderDetailFinancialSnapshot,
    StylistWallet,
    StylistWalletWithdrawalRequest,
)
from apps.salons.models import Salon
from django.urls import reverse

from apps.notifications.models import (
    NotificationAudienceRole,
    NotificationCategory,
    NotificationChannel,
    NotificationPriority,
)
from apps.notifications.services import create_notification
from apps.salons.membership import get_active_salon_for_stylist
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageSequence, UnidentifiedImageError

FINANCE_PAYMENT_RECEIPT_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
FINANCE_PAYMENT_RECEIPT_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "application/pdf",
}
FINANCE_PAYMENT_RECEIPT_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png"}
FINANCE_PAYMENT_RECEIPT_IMAGE_FORMATS = {"JPEG", "PNG"}

FINANCE_PAYMENT_RECEIPT_BLOCKED_FILENAME_PARTS = {
    ".php",
    ".phtml",
    ".php3",
    ".php4",
    ".php5",
    ".asp",
    ".aspx",
    ".jsp",
    ".cgi",
    ".pl",
    ".py",
    ".rb",
    ".htm",
    ".html",
    ".js",
    ".svg",
    ".xml",
    ".exe",
    ".sh",
    ".bat",
    ".cmd",
    ".gif",
    ".webp",
}


def _finance_payment_receipt_max_size_bytes():
    return max(
        int(
            getattr(
                settings,
                "FINANCE_PAYMENT_RECEIPT_MAX_SIZE_BYTES",
                5 * 1024 * 1024,
            )
            or 1
        ),
        1,
    )


def _finance_payment_receipt_image_max_dimension():
    return max(
        int(
            getattr(
                settings,
                "FINANCE_PAYMENT_RECEIPT_IMAGE_MAX_DIMENSION",
                7000,
            )
            or 1
        ),
        1,
    )


def _finance_payment_receipt_image_max_pixels():
    return max(
        int(
            getattr(
                settings,
                "FINANCE_PAYMENT_RECEIPT_IMAGE_MAX_PIXELS",
                20_000_000,
            )
            or 1
        ),
        1,
    )


def _finance_payment_receipt_image_is_animated(image):
    if getattr(image, "is_animated", False):
        return True

    try:
        return sum(1 for _frame in ImageSequence.Iterator(image)) > 1
    except Exception:
        return False


def _validate_finance_payment_receipt_image(uploaded_file):
    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)

        if image.format not in FINANCE_PAYMENT_RECEIPT_IMAGE_FORMATS:
            raise ValidationError("فرمت واقعی تصویر رسید مجاز نیست.")

        if _finance_payment_receipt_image_is_animated(image):
            raise ValidationError("تصویر متحرک برای رسید واریز مجاز نیست.")

        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValidationError("ابعاد تصویر رسید معتبر نیست.")

        max_dimension = _finance_payment_receipt_image_max_dimension()
        if width > max_dimension or height > max_dimension:
            raise ValidationError("ابعاد تصویر رسید بیش از حد مجاز است.")

        if width * height > _finance_payment_receipt_image_max_pixels():
            raise ValidationError("تعداد پیکسل‌های تصویر رسید بیش از حد مجاز است.")

        uploaded_file.seek(0)
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError("فایل رسید، تصویر معتبر نیست.")


def _validate_finance_payment_receipt_pdf(uploaded_file):
    uploaded_file.seek(0)
    header = uploaded_file.read(8)
    uploaded_file.seek(0)

    if not header.startswith(b"%PDF-"):
        raise ValidationError("فایل PDF رسید معتبر نیست.")


def validate_finance_payment_receipt_upload(uploaded_file):
    if not uploaded_file:
        return uploaded_file

    if uploaded_file.size > _finance_payment_receipt_max_size_bytes():
        raise ValidationError("حجم فایل رسید بیش از حد مجاز است.")

    original_name = Path(uploaded_file.name or "").name.lower()
    ext = Path(original_name).suffix.lower()

    if ext not in FINANCE_PAYMENT_RECEIPT_ALLOWED_EXTENSIONS:
        raise ValidationError(
            "پسوند رسید مجاز نیست. فقط JPG، PNG یا PDF قابل قبول است."
        )

    name_without_last_ext = original_name[: -len(ext)] if ext else original_name
    if any(
        blocked in name_without_last_ext
        for blocked in FINANCE_PAYMENT_RECEIPT_BLOCKED_FILENAME_PARTS
    ):
        raise ValidationError("نام یا پسوند فایل رسید مجاز نیست.")

    content_type = str(getattr(uploaded_file, "content_type", "") or "")
    content_type = content_type.split(";")[0].strip().lower()

    if content_type not in FINANCE_PAYMENT_RECEIPT_ALLOWED_CONTENT_TYPES:
        raise ValidationError("فرمت رسید مجاز نیست. فقط JPG، PNG یا PDF قابل قبول است.")

    if ext == ".pdf":
        if content_type != "application/pdf":
            raise ValidationError("فرمت PDF رسید معتبر نیست.")
        _validate_finance_payment_receipt_pdf(uploaded_file)
        return uploaded_file

    if content_type not in FINANCE_PAYMENT_RECEIPT_IMAGE_CONTENT_TYPES:
        raise ValidationError("فرمت تصویر رسید معتبر نیست.")

    _validate_finance_payment_receipt_image(uploaded_file)
    return uploaded_file


def _stylist_withdrawal_pending_amount(requests_qs):
    return int(
        requests_qs.filter(
            status=StylistWalletWithdrawalRequest.Status.PENDING,
        )
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )


def _stylist_withdrawal_summary_cards(wallet, requests_qs, salon):
    pending_withdrawal_amount = _stylist_withdrawal_pending_amount(requests_qs)

    return [
        {
            "label": "مانده قابل دریافت این مجموعه",
            "value": _money(wallet.available_balance_for_salon(salon)),
            "icon": "fa-solid fa-wallet",
        },
        {
            "label": "درخواست‌های در انتظار پرداخت این مجموعه",
            "value": _money(pending_withdrawal_amount),
            "icon": "fa-regular fa-clock",
        },
        {
            "label": "درآمد در انتظار آزادسازی این مجموعه",
            "value": _money(wallet.pending_balance_for_salon(salon)),
            "icon": "fa-solid fa-hourglass-half",
        },
        {
            "label": "جمع مانده مالی این مجموعه",
            "value": _money(wallet.total_balance_for_salon(salon)),
            "icon": "fa-solid fa-coins",
        },
    ]


def _notify_managers_for_stylist_withdrawal_request(withdrawal, *, actor=None):
    stylist = withdrawal.wallet.stylist
    salon = withdrawal.salon
    amount = int(withdrawal.amount or 0)

    manager_user = getattr(getattr(salon, "salon_manager", None), "user", None)
    if not manager_user:
        return None

    stylist_name = (
        stylist.get_fullName() if hasattr(stylist, "get_fullName") else str(stylist)
    )

    return create_notification(
        event_type="stylist_withdrawal_requested",
        category=NotificationCategory.FINANCE,
        priority=NotificationPriority.HIGH,
        title="درخواست دریافت درآمد متخصص",
        body=f"{stylist_name} درخواست دریافت درآمد به مبلغ {amount:,} تومان برای مجموعه {salon.salon_name} ثبت کرد.",
        recipients=[
            {
                "user": manager_user,
                "audience_role": NotificationAudienceRole.MANAGER,
                "channels": [NotificationChannel.DASHBOARD],
            }
        ],
        action_url=reverse("dashboards:finance_stylist_withdrawals"),
        icon="fa-solid fa-money-bill-transfer",
        actor=actor,
        salon=salon,
        related_object=withdrawal,
        metadata={
            "withdrawal_id": withdrawal.pk,
            "stylist_id": stylist.pk,
            "salon_id": salon.pk,
            "amount": amount,
        },
        dedupe_key=f"stylist-withdrawal-requested-{withdrawal.pk}",
    )


def _notify_stylist_for_withdrawal_review(withdrawal, *, action, actor=None):
    stylist = withdrawal.wallet.stylist
    stylist_user = getattr(stylist, "user", None)

    if not stylist_user:
        return None

    amount = int(withdrawal.amount or 0)

    if action == "approved":
        title = "درخواست دریافت درآمد تایید شد"
        body = f"درخواست دریافت درآمد شما به مبلغ {amount:,} تومان تایید شد."
        priority = NotificationPriority.HIGH
    elif action == "rejected":
        title = "درخواست دریافت درآمد رد شد"
        body = (
            f"درخواست دریافت درآمد شما به مبلغ {amount:,} تومان رد شد. "
            "مبلغ به مانده قابل دریافت شما برگشت داده شد."
        )
        priority = NotificationPriority.HIGH
    elif action == "cancelled":
        title = "درخواست دریافت درآمد لغو شد"
        body = (
            f"درخواست دریافت درآمد شما به مبلغ {amount:,} تومان لغو شد. "
            "مبلغ به مانده قابل دریافت شما برگشت داده شد."
        )
        priority = NotificationPriority.NORMAL
    else:
        return None

    if withdrawal.note:
        body = f"{body} توضیح مدیر مجموعه: {withdrawal.note}"

    return create_notification(
        event_type=f"stylist_withdrawal_{action}",
        category=NotificationCategory.FINANCE,
        priority=priority,
        title=title,
        body=body,
        recipients=[
            {
                "user": stylist_user,
                "audience_role": NotificationAudienceRole.STYLIST,
                "channels": [NotificationChannel.DASHBOARD],
            }
        ],
        action_url=reverse("dashboards:stylist_withdrawals"),
        icon="fa-solid fa-money-bill-transfer",
        actor=actor,
        related_object=withdrawal,
        metadata={
            "withdrawal_id": withdrawal.pk,
            "stylist_id": stylist.pk,
            "amount": amount,
            "status": withdrawal.status,
        },
        dedupe_key=f"stylist-withdrawal-{action}-{withdrawal.pk}",
    )


class StylistWithdrawalRequestsView(LoginRequiredMixin, View):
    template_name = "dashboards/stylist_withdrawals.html"

    def dispatch(self, request, *args, **kwargs):
        if hasattr(request.user, "stylist"):
            return super().dispatch(request, *args, **kwargs)

        if hasattr(request.user, "salon_manager_profile"):
            messages.info(request, "این بخش مخصوص متخصصهاست.")
            return redirect("dashboards:salon_manager_dashboard")

        return redirect("accounts:login")

    def _get_wallet(self, request):
        stylist = request.user.stylist
        wallet, _ = StylistWallet.objects.get_or_create(stylist=stylist)
        return stylist, wallet

    def get(self, request):
        stylist, wallet = self._get_wallet(request)
        salon = get_active_salon_for_stylist(request.user, request=request)

        if not salon:
            messages.error(
                request,
                "برای ثبت یا مشاهده درخواست دریافت، ابتدا یک مجموعه فعال انتخاب کنید.",
            )
            return redirect("dashboards:stylist_dashboard")

        requests_qs = StylistWalletWithdrawalRequest.objects.filter(
            wallet=wallet,
            salon=salon,
        ).order_by("-created_at", "-id")

        transactions = (
            wallet.transactions.filter(
                salon=salon,
                transaction_type__in=["withdraw_request", "withdraw_restore"],
            )
            .select_related("withdrawal_request")
            .order_by("-created_at", "-id")[:50]
        )

        context = build_dashboard_context(
            request.user,
            sidebar_active="my_finance",
            page_title="درخواست دریافت درآمد",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update(
            {
                "stylist_obj": stylist,
                "salon": salon,
                "wallet": wallet,
                "withdrawal_form": StylistWithdrawalRequestForm(
                    wallet=wallet, salon=salon
                ),
                "withdrawal_requests": requests_qs,
                "transactions": transactions,
                "summary_cards": _stylist_withdrawal_summary_cards(
                    wallet, requests_qs, salon
                ),
            }
        )
        return render(request, self.template_name, context)

    def post(self, request):
        stylist, wallet = self._get_wallet(request)

        salon = get_active_salon_for_stylist(request.user, request=request)
        if not salon:
            messages.error(
                request, "برای ثبت درخواست دریافت، ابتدا یک مجموعه فعال انتخاب کنید."
            )
            return redirect("dashboards:stylist_dashboard")

        form = StylistWithdrawalRequestForm(request.POST, wallet=wallet, salon=salon)

        if form.is_valid():
            try:
                withdrawal = form.save()
                _notify_managers_for_stylist_withdrawal_request(
                    withdrawal,
                    actor=request.user,
                )

                messages.success(
                    request,
                    "درخواست دریافت درآمد شما ثبت شد و برای بررسی مدیر مجموعه ارسال شد.",
                )
                return redirect("dashboards:stylist_withdrawals")
            except ValidationError as exc:
                messages.error(request, str(exc))
        else:
            messages.error(request, "اطلاعات درخواست دریافت معتبر نیست.")

        requests_qs = StylistWalletWithdrawalRequest.objects.filter(
            wallet=wallet,
            salon=salon,
        ).order_by("-created_at", "-id")

        transactions = (
            wallet.transactions.filter(
                salon=salon,
                transaction_type__in=["withdraw_request", "withdraw_restore"],
            )
            .select_related("withdrawal_request")
            .order_by("-created_at", "-id")[:50]
        )

        context = build_dashboard_context(
            request.user,
            sidebar_active="my_finance",
            page_title="درخواست دریافت درآمد",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update(
            {
                "stylist_obj": stylist,
                "salon": salon,
                "wallet": wallet,
                "withdrawal_form": form,
                "withdrawal_requests": requests_qs,
                "transactions": transactions,
                "summary_cards": _stylist_withdrawal_summary_cards(
                    wallet, requests_qs, salon
                ),
            }
        )
        return render(request, self.template_name, context)


class ManagerStylistWithdrawalRequestsView(_SalonFinanceOperationMixin, View):
    template_name = "dashboards/manager_stylist_withdrawals.html"

    def get(self, request):
        salon = self.get_salon(request)
        withdrawals = StylistWalletWithdrawalRequest.objects.filter(
            salon=salon,
        ).select_related(
            "wallet__stylist__user"
        ).order_by("-created_at", "-id")

        pending = withdrawals.filter(
            status=StylistWalletWithdrawalRequest.Status.PENDING
        )
        reviewed = withdrawals.exclude(
            status=StylistWalletWithdrawalRequest.Status.PENDING
        )
        approved = withdrawals.filter(
            status=StylistWalletWithdrawalRequest.Status.APPROVED
        )
        returned = withdrawals.filter(
            status__in=[
                StylistWalletWithdrawalRequest.Status.REJECTED,
                StylistWalletWithdrawalRequest.Status.CANCELLED,
            ]
        )

        pending_amount = pending.aggregate(total=Sum("amount")).get("total") or 0
        approved_amount = approved.aggregate(total=Sum("amount")).get("total") or 0
        returned_amount = returned.aggregate(total=Sum("amount")).get("total") or 0

        context = self.base_context(
            request,
            title="برداشت متخصصان",
            sidebar_active="finance",
        )
        context.update(
            {
                "salon": salon,
                "pending_withdrawals": pending[:100],
                "reviewed_withdrawals": reviewed[:100],
                # Kept for compatibility with any downstream dashboard extension
                # that still reads the previous all-in-one collection.
                "withdrawals": withdrawals[:100],
                "withdrawal_summary": {
                    "pending_count": pending.count(),
                    "pending_amount": _money(pending_amount),
                    "approved_amount": _money(approved_amount),
                    "returned_amount": _money(returned_amount),
                },
            }
        )
        return render(request, self.template_name, context)

    def post(self, request):
        salon = self.get_salon(request)

        withdrawal = get_object_or_404(
            StylistWalletWithdrawalRequest.objects.select_related(
                "wallet__stylist__user",
                "salon",
            ),
            pk=request.POST.get("withdrawal_id"),
            salon=salon,
        )

        action = (request.POST.get("action") or "").strip()
        note = request.POST.get("note") or ""

        try:
            if action == "approve":
                payment_receipt = request.FILES.get("payment_receipt")
                if payment_receipt:
                    payment_receipt = validate_finance_payment_receipt_upload(
                        payment_receipt
                    )

                withdrawal.approve(
                    note=note or "تأیید دریافت درآمد توسط مدیر مجموعه",
                    payment_receipt=payment_receipt,
                )

                _notify_stylist_for_withdrawal_review(
                    withdrawal,
                    action="approved",
                    actor=request.user,
                )

                if payment_receipt:
                    messages.success(
                        request,
                        "درخواست دریافت درآمد با رسید واریز تأیید شد و به متخصص اطلاع داده شد.",
                    )
                else:
                    messages.success(
                        request,
                        "درخواست دریافت درآمد بدون رسید تأیید شد و به متخصص اطلاع داده شد.",
                    )

            elif action == "reject":
                withdrawal.reject(
                    note=note or "رد درخواست دریافت درآمد توسط مدیر مجموعه"
                )

                _notify_stylist_for_withdrawal_review(
                    withdrawal,
                    action="rejected",
                    actor=request.user,
                )

                messages.warning(
                    request,
                    "درخواست دریافت درآمد رد شد، مبلغ برگشت داده شد و به متخصص اطلاع داده شد.",
                )

            elif action == "cancel":
                withdrawal.cancel(
                    note=note or "لغو درخواست دریافت درآمد توسط مدیر مجموعه"
                )

                _notify_stylist_for_withdrawal_review(
                    withdrawal,
                    action="cancelled",
                    actor=request.user,
                )

                messages.warning(
                    request,
                    "درخواست دریافت درآمد لغو شد، مبلغ برگشت داده شد و به متخصص اطلاع داده شد.",
                )

            else:
                messages.error(request, "عملیات انتخاب‌شده معتبر نیست.")

        except ValidationError as exc:
            messages.error(request, str(exc))

        return redirect("dashboards:finance_stylist_withdrawals")
