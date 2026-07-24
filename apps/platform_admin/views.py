from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import (
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)
from django.db import models, transaction
from apps.articles.models import (
    Article,
    ContentReport,
    SalonStory,
    StaffContentSubmission,
)
from apps.dashboards.jalali_utils import parse_jalali_input
from apps.main.models import (
    AdminAuditLog,
    DisputeCase,
    DisputeEvent,
    MediaProcessingJob,
    OperationalJobRun,
    PlatformSetting,
    SecurityAuditLog,
    SupportEvent,
    SupportTicket,
    SupportTicketMessage,
    SuspensionRecord,
)
from apps.notifications.models import (
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationRecipient,
)
from apps.orders.models import Order, OrderDetail
from apps.payments.models import (
    CustomerCompensation,
    FinancialAdjustment,
    LedgerEntry,
    OrderDetailFinancialSnapshot,
    Payment,
    PaymentTransaction,
    RefundRequest,
    StaffEarning,
    StaffPayoutRequest,
)
from apps.salons.models import (
    Salon,
    SalonMembership,
    SalonVerification,
    SalonVerificationStatus,
)
from .audit import create_admin_audit_log
from .forms import (
    DisputeActionForm,
    ModerationActionForm,
    PlatformSettingForm,
    SalonVerificationActionForm,
    SupportStatusForm,
    SuspensionActionForm,
)
from .permissions import (
    PlatformAdminRequiredMixin,
    ROLE_CONTENT,
    ROLE_FINANCE,
    ROLE_READ_ONLY,
    ROLE_SUPPORT,
    ROLE_SUPER,
    ROLE_VERIFY,
)
from django.core.exceptions import ValidationError
from apps.dashboards.beta_readiness import (
    serialize_beta_salon_readiness,
    with_beta_readiness_annotations,
)

User = get_user_model()
PLATFORM_SUPPORT_STATUS_VALUES = {value for value, _ in SupportTicket.STATUS_CHOICES}
PLATFORM_SUPPORT_CATEGORY_VALUES = {
    value for value, _ in SupportTicket.CATEGORY_CHOICES
}


def _platform_support_query_max_chars():
    return max(
        int(getattr(settings, "PLATFORM_SUPPORT_QUERY_MAX_CHARS", 2048) or 1),
        1,
    )


def _platform_support_action_post_max_bytes():
    return max(
        int(
            getattr(settings, "PLATFORM_SUPPORT_ACTION_POST_MAX_BYTES", 16 * 1024) or 1
        ),
        1,
    )


def _platform_support_admin_reply_max_chars():
    return max(
        int(getattr(settings, "PLATFORM_SUPPORT_ADMIN_REPLY_MAX_CHARS", 3000) or 1),
        1,
    )


def _platform_support_internal_note_max_chars():
    return max(
        int(getattr(settings, "PLATFORM_SUPPORT_INTERNAL_NOTE_MAX_CHARS", 2000) or 1),
        1,
    )


def _platform_request_body_too_large(request, max_bytes):
    try:
        content_length = int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        content_length = 0

    return content_length > max_bytes


def _validate_platform_support_query_size(request):
    query_string = request.META.get("QUERY_STRING") or ""
    if len(query_string.encode("utf-8")) > _platform_support_query_max_chars():
        raise ValidationError("حجم فیلترهای صف پشتیبانی بیش از حد مجاز است.")


def _validate_platform_support_action_size(request):
    if _platform_request_body_too_large(
        request,
        _platform_support_action_post_max_bytes(),
    ):
        raise ValidationError("حجم اطلاعات ارسالی بیش از حد مجاز است.")


def _clean_platform_support_choice(raw_value, allowed_values):
    value = str(raw_value or "").strip()
    return value if value in allowed_values else ""


def _clean_platform_support_text(raw_value, *, max_chars, field_label):
    text = str(raw_value or "").strip()
    text = text.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")

    if len(text) > max_chars:
        raise ValidationError(f"{field_label} بیش از حد مجاز است.")

    return text


class PlatformAdminBaseMixin(PlatformAdminRequiredMixin):
    template_name = "platform_admin/base.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("section", "dashboard")
        ctx["hide_navbar"] = True
        ctx["hide_footer"] = True
        ctx["platform_nav"] = [
            {
                "key": "dashboard",
                "label": "داشبورد",
                "url": reverse("platform_admin:dashboard"),
                "icon": "fa-solid fa-house",
            },
            {
                "key": "salons",
                "label": "مجموعه‌ها",
                "url": reverse("platform_admin:salons"),
                "icon": "fa-solid fa-shop",
            },
            {
                "key": "users",
                "label": "کاربران",
                "url": reverse("platform_admin:users"),
                "icon": "fa-solid fa-users",
            },
            {
                "key": "appointments",
                "label": "نوبت‌ها",
                "url": reverse("platform_admin:appointments"),
                "icon": "fa-regular fa-calendar-check",
            },
            {
                "key": "content",
                "label": "محتوا",
                "url": reverse("platform_admin:content_reports"),
                "icon": "fa-solid fa-newspaper",
            },
            {
                "key": "finance",
                "label": "مالی",
                "url": reverse("platform_admin:finance"),
                "icon": "fa-solid fa-coins",
            },
            {
                "key": "notifications",
                "label": "اعلان‌ها",
                "url": reverse("platform_admin:notifications"),
                "icon": "fa-regular fa-bell",
            },
            {
                "key": "support",
                "label": "پشتیبانی",
                "url": reverse("platform_admin:support"),
                "icon": "fa-solid fa-headset",
            },
            {
                "key": "disputes",
                "label": "اختلاف‌ها",
                "url": reverse("platform_admin:disputes"),
                "icon": "fa-solid fa-scale-balanced",
            },
            {
                "key": "analytics",
                "label": "گزارش‌ها",
                "url": reverse("platform_admin:analytics"),
                "icon": "fa-solid fa-chart-simple",
            },
            {
                "key": "infrastructure",
                "label": "زیرساخت",
                "url": reverse("platform_admin:infrastructure"),
                "icon": "fa-solid fa-server",
            },
            {
                "key": "settings",
                "label": "تنظیمات",
                "url": reverse("platform_admin:settings"),
                "icon": "fa-solid fa-gear",
            },
            {
                "key": "audit",
                "label": "لاگ‌ها",
                "url": reverse("platform_admin:audit"),
                "icon": "fa-solid fa-clipboard-list",
            },
        ]
        return ctx


def _safe_count(qs):
    try:
        return qs.count()
    except Exception:
        return 0


def _paginate(request, queryset, per_page=25):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get("page"))


def _content_target_admin_meta(report):
    """Attach safe display metadata for content reports without changing models."""
    target = None
    try:
        target = report.target_object
    except Exception:
        target = None

    meta = {
        "exists": bool(target),
        "type_label": (
            getattr(getattr(target, "_meta", None), "verbose_name", "محتوا")
            if target
            else "محتوای حذف‌شده"
        ),
        "title": "محتوای حذف‌شده یا ناموجود",
        "status": "",
        "status_label": "",
        "author": "",
        "salon": "",
        "url": "",
        "image_url": "",
        "summary": "",
        "object_id": getattr(report, "target_object_id", ""),
    }

    if not target:
        return meta

    meta["title"] = (
        getattr(target, "title", "")
        or getattr(target, "caption", "")
        or getattr(target, "summary", "")
        or str(target)
    )
    meta["status"] = getattr(target, "status", "") or ""
    get_status_display = getattr(target, "get_status_display", None)
    if callable(get_status_display):
        try:
            meta["status_label"] = get_status_display()
        except Exception:
            meta["status_label"] = meta["status"]
    else:
        meta["status_label"] = meta["status"]

    salon = getattr(target, "salon", None) or getattr(target, "author_salon", None)
    if salon:
        meta["salon"] = getattr(salon, "salon_name", "") or str(salon)

    author = getattr(target, "author_display_name", "") or ""
    if not author and getattr(target, "stylist", None):
        stylist = target.stylist
        try:
            author = stylist.get_fullName()
        except Exception:
            author = str(stylist)
    meta["author"] = author

    summary = (
        getattr(target, "summary", "")
        or getattr(target, "caption", "")
        or getattr(target, "content", "")
        or ""
    )
    meta["summary"] = str(summary)[:180]

    for attr in ("cover_image", "featured_image", "image", "video"):
        media = getattr(target, attr, None)
        if media:
            try:
                meta["image_url"] = media.url
                break
            except Exception:
                pass

    url = ""
    get_url = getattr(target, "get_absolute_url", None)
    if callable(get_url):
        try:
            url = get_url()
        except Exception:
            url = ""

    if isinstance(target, SalonStory):
        try:
            url = f"{reverse('articles:magazine_home')}?story={target.pk}"
        except Exception:
            url = f"/magazine/?story={target.pk}"

    meta["url"] = url
    return meta


class DashboardView(PlatformAdminBaseMixin, TemplateView):
    template_name = "platform_admin/dashboard.html"
    required_roles = ()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        ctx.update(
            section="dashboard",
            cards=[
                {
                    "label": "مجموعه‌ها",
                    "value": _safe_count(Salon.objects.all()),
                    "url": reverse("platform_admin:salons"),
                },
                {
                    "label": "در انتظار احراز",
                    "value": _safe_count(
                        SalonVerification.objects.filter(
                            status=SalonVerificationStatus.UNDER_REVIEW
                        )
                    ),
                    "url": reverse("platform_admin:salons")
                    + "?verification=under_review",
                },
                {
                    "label": "کاربران",
                    "value": _safe_count(User.objects.all()),
                    "url": reverse("platform_admin:users"),
                },
                {
                    "label": "نوبت‌های امروز",
                    "value": _safe_count(OrderDetail.objects.filter(date=today)),
                    "url": reverse("platform_admin:appointments"),
                },
                {
                    "label": "no-show/اختلاف",
                    "value": _safe_count(
                        OrderDetail.objects.filter(
                            lifecycle_status__in=[
                                "no_show_pending_review",
                                "no_show_confirmed",
                                "disputed",
                            ]
                        )
                    ),
                    "url": reverse("platform_admin:appointments") + "?status=disputed",
                },
                {
                    "label": "گزارش محتوا",
                    "value": _safe_count(
                        ContentReport.objects.filter(status="pending")
                    ),
                    "url": reverse("platform_admin:content_reports"),
                },
                {
                    "label": "تیکت‌های باز",
                    "value": _safe_count(
                        SupportTicket.objects.exclude(status="closed")
                    ),
                    "url": reverse("platform_admin:support"),
                },
                {
                    "label": "اعلان‌های ناموفق",
                    "value": _safe_count(
                        NotificationDelivery.objects.filter(
                            status=NotificationDeliveryStatus.FAILED
                        )
                    ),
                    "url": reverse("platform_admin:notifications") + "?status=failed",
                },
            ],
            recent_audit=AdminAuditLog.objects.select_related(
                "actor", "target_content_type"
            )[:10],
            pending_finance={
                "staff_payouts": _safe_count(
                    StaffPayoutRequest.objects.filter(status="pending")
                ),
                "adjustments": _safe_count(
                    FinancialAdjustment.objects.filter(status="pending")
                ),
                "refunds": _safe_count(RefundRequest.objects.filter(status="pending")),
            },
            beta_flags={
                "BETA_MODE": getattr(settings, "BETA_MODE", True),
                "ONLINE_PAYMENT_ENABLED": getattr(
                    settings, "ONLINE_PAYMENT_ENABLED", False
                ),
                "BNPL_ENABLED": getattr(settings, "BNPL_ENABLED", False),
                "COMMISSION_ENABLED": getattr(settings, "COMMISSION_ENABLED", False),
            },
        )
        return ctx


class SalonListView(PlatformAdminBaseMixin, ListView):
    template_name = "platform_admin/salon_list.html"
    required_roles = (ROLE_SUPPORT, ROLE_VERIFY, ROLE_READ_ONLY)
    context_object_name = "salons"
    paginate_by = 30

    def get_queryset(self):
        qs = with_beta_readiness_annotations(
            Salon.objects.select_related(
                "salon_manager__user",
                "verification",
                "neighborhood",
            )
        ).order_by("-registere_date", "-id")
        q = (self.request.GET.get("q") or "").strip()
        verification = (self.request.GET.get("verification") or "").strip()
        active = (self.request.GET.get("active") or "").strip()
        if q:
            qs = qs.filter(
                Q(salon_name__icontains=q)
                | Q(address__icontains=q)
                | Q(salon_manager__user__mobile_number__icontains=q)
            )
        if verification:
            qs = qs.filter(verification_status=verification)
        if active in {"0", "1"}:
            qs = qs.filter(is_active=(active == "1"))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        salon_rows = [
            {
                "salon": salon,
                "readiness": serialize_beta_salon_readiness(salon),
            }
            for salon in ctx.get("salons", [])
        ]

        ctx.update(
            section="salons",
            verification_choices=(SalonVerificationStatus.choices),
            salon_rows=salon_rows,
        )

        return ctx


class SalonDetailView(PlatformAdminBaseMixin, DetailView):
    template_name = "platform_admin/salon_detail.html"
    required_roles = (ROLE_SUPPORT, ROLE_VERIFY, ROLE_READ_ONLY)
    model = Salon
    context_object_name = "salon"

    def get_queryset(self):
        return with_beta_readiness_annotations(
            Salon.objects.select_related(
                "salon_manager__user",
                "verification",
                "neighborhood",
            )
        ).prefetch_related(
            "memberships__stylist__user",
            "bank_accounts",
        )

    def get_context_data(self, **kwargs):
        salon = self.object
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            section="salons",
            beta_readiness=serialize_beta_salon_readiness(salon),
            verification_form=SalonVerificationActionForm(
                initial={"status": salon.verification_status}
            ),
            recent_orders=OrderDetail.objects.filter(salon=salon)
            .select_related("order__customer__user", "stylist__user", "service")
            .order_by("-date", "-time")[:20],
            content_reports=ContentReport.objects.filter(
                target_object_id__isnull=False
            ).order_by("-created_at")[:10],
            staff_memberships=salon.memberships.select_related(
                "stylist__user", "dashboard_permissions"
            )[:50],
            ledger_total=LedgerEntry.objects.filter(
                order_detail__salon=salon, status="posted"
            ).aggregate(total=Sum("amount"))["total"]
            or 0,
        )
        return ctx


class SalonVerificationActionView(PlatformAdminBaseMixin, View):
    required_roles = (ROLE_VERIFY,)

    def post(self, request, pk):
        salon = get_object_or_404(Salon, pk=pk)
        form = SalonVerificationActionForm(request.POST)
        if not form.is_valid():
            messages.error(request, "اطلاعات وضعیت احراز معتبر نیست.")
            return redirect("platform_admin:salon_detail", pk=salon.pk)
        old = salon.verification_status
        new = form.cleaned_data["status"]
        reason = form.cleaned_data.get("reason") or ""
        verification, _ = SalonVerification.objects.get_or_create(salon=salon)
        verification.status = new
        verification.reviewed_by = request.user
        verification.reviewed_at = timezone.now()
        if new == SalonVerificationStatus.REJECTED:
            verification.rejection_reason = reason
        verification.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "rejection_reason",
                "updated_at",
            ]
        )
        salon.verification_status = new
        salon.save(update_fields=["verification_status"])
        create_admin_audit_log(
            request=request,
            action="salon.verification_status_changed",
            target=salon,
            old_value={"verification_status": old},
            new_value={"verification_status": new},
            reason=reason,
        )
        messages.success(request, "وضعیت احراز مجموعه به‌روزرسانی شد.")
        return redirect("platform_admin:salon_detail", pk=salon.pk)


class UserListView(PlatformAdminBaseMixin, ListView):
    template_name = "platform_admin/user_list.html"
    required_roles = (ROLE_SUPPORT, ROLE_READ_ONLY)
    context_object_name = "users"
    paginate_by = 30

    def get_queryset(self):
        qs = User.objects.all().order_by("-register_date", "-id")
        q = (self.request.GET.get("q") or "").strip()
        role = (self.request.GET.get("role") or "").strip()
        active = (self.request.GET.get("active") or "").strip()
        if q:
            qs = qs.filter(
                Q(mobile_number__icontains=q)
                | Q(name__icontains=q)
                | Q(family__icontains=q)
                | Q(email__icontains=q)
            )
        if active in {"0", "1"}:
            qs = qs.filter(is_active=(active == "1"))
        if role == "customer":
            qs = qs.filter(customer_profile__isnull=False)
        elif role == "stylist":
            qs = qs.filter(stylist__isnull=False)
        elif role == "manager":
            qs = qs.filter(salon_manager_profile__isnull=False)
        elif role == "admin":
            qs = qs.filter(
                Q(is_admin=True) | Q(platform_admin_roles__is_active=True)
            ).distinct()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(section="users")
        return ctx


class UserDetailView(PlatformAdminBaseMixin, DetailView):
    template_name = "platform_admin/user_detail.html"
    required_roles = (ROLE_SUPPORT, ROLE_READ_ONLY)
    model = User
    context_object_name = "target_user"

    def get_context_data(self, **kwargs):
        user = self.object
        ctx = super().get_context_data(**kwargs)
        stylist = getattr(user, "stylist", None)
        manager = getattr(user, "salon_manager_profile", None)
        ctx.update(
            section="users",
            suspension_form=SuspensionActionForm(),
            admin_roles=user.platform_admin_roles.filter(is_active=True),
            support_tickets=(
                user.support_tickets.all()[:10]
                if hasattr(user, "support_tickets")
                else []
            ),
            stylist_memberships=(
                stylist.salon_memberships.select_related("salon")[:20]
                if stylist
                else []
            ),
            managed_salons=manager.salon_manager.all()[:20] if manager else [],
            security_logs=SecurityAuditLog.objects.filter(actor=user)[:10],
        )
        return ctx


class UserSuspendActionView(PlatformAdminBaseMixin, View):
    required_roles = (ROLE_SUPPORT,)

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        form = SuspensionActionForm(request.POST)
        if not form.is_valid():
            messages.error(request, "اطلاعات تعلیق معتبر نیست.")
            return redirect("platform_admin:user_detail", pk=user.pk)
        ct = ContentType.objects.get_for_model(user, for_concrete_model=False)
        SuspensionRecord.objects.create(
            target_content_type=ct,
            target_object_id=user.pk,
            reason=form.cleaned_data["reason"],
            user_facing_reason=form.cleaned_data.get("user_facing_reason") or "",
            internal_note=form.cleaned_data.get("internal_note") or "",
            expires_at=form.cleaned_data.get("expires_at"),
            created_by=request.user,
        )
        old = user.is_active
        user.is_active = False
        user.save(update_fields=["is_active"])
        create_admin_audit_log(
            request=request,
            action="user.suspended",
            target=user,
            old_value={"is_active": old},
            new_value={
                "is_active": user.is_active,
                "reason": form.cleaned_data["reason"],
            },
            reason=form.cleaned_data["reason"],
        )
        messages.warning(request, "کاربر تعلیق شد.")
        return redirect("platform_admin:user_detail", pk=user.pk)


class AppointmentListView(PlatformAdminBaseMixin, ListView):
    template_name = "platform_admin/appointment_list.html"
    required_roles = (ROLE_SUPPORT, ROLE_READ_ONLY)
    context_object_name = "appointments"
    paginate_by = 30

    def get_queryset(self):
        qs = OrderDetail.objects.select_related(
            "order__customer__user", "salon", "stylist__user", "service"
        ).order_by("-date", "-time", "-id")
        status = (self.request.GET.get("status") or "").strip()
        q = (self.request.GET.get("q") or "").strip()
        if status == "disputed":
            qs = qs.filter(
                lifecycle_status__in=[
                    "no_show_pending_review",
                    "no_show_confirmed",
                    "disputed",
                    "service_overrun",
                ]
            )
        elif status:
            qs = qs.filter(lifecycle_status=status)
        if q:
            qs = qs.filter(
                Q(salon__salon_name__icontains=q)
                | Q(order__customer__user__mobile_number__icontains=q)
                | Q(stylist__user__mobile_number__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(section="appointments")
        return ctx


class ContentReportListView(PlatformAdminBaseMixin, ListView):
    template_name = "platform_admin/content_report_list.html"
    required_roles = (ROLE_CONTENT, ROLE_SUPPORT, ROLE_READ_ONLY)
    context_object_name = "reports"
    paginate_by = 30

    def get_queryset(self):
        qs = ContentReport.objects.select_related(
            "reported_by", "target_content_type", "reviewed_by"
        ).order_by("-created_at")
        status = (self.request.GET.get("status") or "pending").strip()
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        reports = ctx.get("reports") or ctx.get("object_list") or []
        for report in reports:
            report.target_admin_meta = _content_target_admin_meta(report)
        ctx.update(section="content", form=ModerationActionForm())
        return ctx


class ContentReportActionView(PlatformAdminBaseMixin, View):
    required_roles = (ROLE_CONTENT,)

    def post(self, request, pk):
        report = get_object_or_404(ContentReport, pk=pk)
        form = ModerationActionForm(request.POST)
        if not form.is_valid():
            messages.error(request, "عملیات گزارش محتوا معتبر نیست.")
            return redirect("platform_admin:content_reports")
        action = form.cleaned_data["action"]
        note = form.cleaned_data.get("note") or ""
        target = report.target_object
        old_status = getattr(target, "status", "") if target else ""
        if action in {"accept", "suspend"} and target and hasattr(target, "status"):
            setattr(target, "status", "suspended")
            target.save(update_fields=["status"] if hasattr(target, "status") else None)
            report.status = "accepted"
        elif action == "remove" and target and hasattr(target, "status"):
            setattr(target, "status", "removed_by_loomera")
            if hasattr(target, "removed_by"):
                target.removed_by = request.user
            if hasattr(target, "removed_at"):
                target.removed_at = timezone.now()
            update_fields = ["status"]
            if hasattr(target, "removed_by"):
                update_fields.append("removed_by")
            if hasattr(target, "removed_at"):
                update_fields.append("removed_at")
            target.save(update_fields=update_fields)
            report.status = "accepted"
        elif action == "reject":
            report.status = "rejected"
        report.reviewed_by = request.user
        report.reviewed_at = timezone.now()
        report.resolution_note = note
        report.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "resolution_note",
                "updated_at",
            ]
        )
        create_admin_audit_log(
            request=request,
            action="content_report.reviewed",
            target=report,
            old_value={"target_status": old_status, "report_status": "pending"},
            new_value={
                "action": action,
                "report_status": report.status,
                "target_status": getattr(target, "status", "") if target else "",
            },
            reason=note,
        )
        messages.success(request, "گزارش محتوا بررسی شد.")
        return redirect("platform_admin:content_reports")


class FinanceOverviewView(PlatformAdminBaseMixin, TemplateView):
    template_name = "platform_admin/finance.html"
    required_roles = (ROLE_FINANCE, ROLE_READ_ONLY)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            section="finance",
            payments=Payment.objects.select_related("customer__user", "order").order_by(
                "-register_date"
            )[:20],
            payment_transactions=PaymentTransaction.objects.select_related(
                "order", "order_detail", "provider"
            ).order_by("-created_at")[:20],
            financial_snapshots=OrderDetailFinancialSnapshot.objects.select_related(
                "order", "order_detail", "salon", "stylist__user", "service"
            ).order_by("-finalized_at", "-id")[:20],
            staff_earnings=StaffEarning.objects.select_related(
                "order_detail", "financial_snapshot", "salon", "stylist__user"
            ).order_by("-calculated_at", "-id")[:20],
            ledger_entries=LedgerEntry.objects.select_related(
                "account", "order", "order_detail"
            ).order_by("-created_at", "-id")[:40],
            staff_payouts=StaffPayoutRequest.objects.select_related(
                "salon", "stylist__user"
            )
            .prefetch_related("earnings")
            .order_by("-requested_at")[:20],
            adjustments=FinancialAdjustment.objects.select_related(
                "order", "order_detail", "requested_by", "approved_by"
            ).order_by("-created_at")[:20],
            refunds=RefundRequest.objects.select_related(
                "order", "payment_transaction"
            ).order_by("-created_at")[:20],
            compensations=CustomerCompensation.objects.select_related(
                "order", "order_detail", "salon", "customer__user"
            ).order_by("-created_at")[:20],
            ledger_total=LedgerEntry.objects.filter(status="posted").aggregate(
                total=Sum("amount")
            )["total"]
            or 0,
            posted_ledger_count=LedgerEntry.objects.filter(status="posted").count(),
            finalized_snapshot_count=OrderDetailFinancialSnapshot.objects.filter(
                status=OrderDetailFinancialSnapshot.Status.FINALIZED
            ).count(),
            payable_earning_count=StaffEarning.objects.filter(
                status__in=[
                    StaffEarning.Status.PENDING,
                    StaffEarning.Status.PAYABLE,
                    StaffEarning.Status.REQUESTED,
                ]
            ).count(),
        )
        return ctx


class NotificationMonitorView(PlatformAdminBaseMixin, ListView):
    template_name = "platform_admin/notifications.html"
    required_roles = (ROLE_SUPPORT, ROLE_READ_ONLY)
    context_object_name = "deliveries"
    paginate_by = 30

    def get_queryset(self):
        qs = NotificationDelivery.objects.select_related(
            "recipient__notification", "recipient__user"
        ).order_by("-created_at")
        status = (self.request.GET.get("status") or "").strip()
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            section="notifications",
            failed_count=_safe_count(
                NotificationDelivery.objects.filter(
                    status=NotificationDeliveryStatus.FAILED
                )
            ),
        )
        return ctx


class SupportQueueView(PlatformAdminBaseMixin, ListView):
    template_name = "platform_admin/support.html"
    required_roles = (ROLE_SUPPORT, ROLE_READ_ONLY)
    context_object_name = "tickets"
    paginate_by = 30

    def get(self, request, *args, **kwargs):
        try:
            _validate_platform_support_query_size(request)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("platform_admin:support")

        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qs = SupportTicket.objects.select_related(
            "user",
            "assigned_to",
            "salon",
            "stylist__user",
            "order",
            "order_detail",
        ).order_by("-updated_at", "-created_at")

        status = _clean_platform_support_choice(
            self.request.GET.get("status"),
            PLATFORM_SUPPORT_STATUS_VALUES,
        )
        if status:
            qs = qs.filter(status=status)

        category = _clean_platform_support_choice(
            self.request.GET.get("category"),
            PLATFORM_SUPPORT_CATEGORY_VALUES,
        )
        if category:
            qs = qs.filter(category=category)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            section="support",
            form=SupportStatusForm(),
            status_choices=SupportTicket.STATUS_CHOICES,
            category_choices=SupportTicket.CATEGORY_CHOICES,
        )
        return ctx


class SupportDetailView(PlatformAdminBaseMixin, DetailView):
    template_name = "platform_admin/support_detail.html"
    required_roles = (ROLE_SUPPORT, ROLE_READ_ONLY)
    context_object_name = "ticket"

    def get_queryset(self):
        return SupportTicket.objects.select_related(
            "user", "assigned_to", "salon", "stylist__user", "order", "order_detail"
        ).prefetch_related("messages__attachments", "events", "dispute_cases__events")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            section="support",
            form=SupportStatusForm(
                initial={
                    "status": self.object.status,
                    "priority": self.object.priority,
                    "assigned_team": self.object.assigned_team,
                }
            ),
        )
        return ctx


class SupportStatusActionView(PlatformAdminBaseMixin, View):
    required_roles = (ROLE_SUPPORT,)

    def post(self, request, pk):
        try:
            _validate_platform_support_action_size(request)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("platform_admin:support_detail", pk=pk)

        from apps.accounts.notifications import notify_support_reply
        from apps.main.support_services import (
            add_support_message,
            log_admin_support_action,
            update_support_ticket_status,
        )

        with transaction.atomic():
            ticket = get_object_or_404(
                SupportTicket.objects.select_for_update(),
                pk=pk,
            )

            form = SupportStatusForm(request.POST)
            if not form.is_valid():
                messages.error(request, "اطلاعات تیکت معتبر نیست.")
                return redirect("platform_admin:support_detail", pk=ticket.pk)

            try:
                reply = _clean_platform_support_text(
                    form.cleaned_data.get("admin_reply"),
                    max_chars=_platform_support_admin_reply_max_chars(),
                    field_label="متن پاسخ",
                )
                internal_note = _clean_platform_support_text(
                    form.cleaned_data.get("internal_note"),
                    max_chars=_platform_support_internal_note_max_chars(),
                    field_label="یادداشت داخلی",
                )
            except ValidationError as exc:
                messages.error(request, str(exc))
                return redirect("platform_admin:support_detail", pk=ticket.pk)

            old = {
                "status": ticket.status,
                "priority": ticket.priority,
                "assigned_team": ticket.assigned_team,
                "admin_reply": ticket.admin_reply,
            }

            ticket.priority = form.cleaned_data.get("priority") or ticket.priority
            ticket.assigned_team = (
                form.cleaned_data.get("assigned_team") or ticket.assigned_team
            )
            ticket.save(update_fields=["priority", "assigned_team", "updated_at"])

            status = form.cleaned_data["status"]
            if status != ticket.status:
                update_support_ticket_status(
                    ticket=ticket,
                    status=status,
                    actor=request.user,
                    note=internal_note,
                    request=request,
                )

            if reply:
                add_support_message(
                    ticket=ticket,
                    sender=request.user,
                    sender_role="support_admin",
                    body=reply,
                    request=request,
                )

                if ticket.user_id:
                    transaction.on_commit(
                        lambda ticket_id=ticket.pk: notify_support_reply(
                            user=SupportTicket.objects.select_related("user")
                            .get(pk=ticket_id)
                            .user,
                            ticket=SupportTicket.objects.get(pk=ticket_id),
                            action_url=reverse(
                                "main:support_ticket_detail",
                                kwargs={"pk": ticket_id},
                            ),
                        )
                    )

            log_admin_support_action(
                request=request,
                action="support_ticket.updated",
                target=ticket,
                old_value=old,
                new_value={
                    "status": ticket.status,
                    "priority": ticket.priority,
                    "assigned_team": ticket.assigned_team,
                },
                reason=internal_note or reply,
            )

        messages.success(request, "تیکت به‌روزرسانی شد.")
        return redirect("platform_admin:support_detail", pk=ticket.pk)


class DisputeListView(PlatformAdminBaseMixin, ListView):
    template_name = "platform_admin/disputes.html"
    required_roles = (ROLE_SUPPORT, ROLE_FINANCE, ROLE_READ_ONLY)
    context_object_name = "disputes"
    paginate_by = 30

    def get_queryset(self):
        qs = DisputeCase.objects.select_related(
            "salon",
            "stylist__user",
            "customer__user",
            "order",
            "order_detail",
            "support_ticket",
            "resolved_by",
        ).order_by("-updated_at", "-created_at")
        status = (self.request.GET.get("status") or "").strip()
        if status:
            qs = qs.filter(status=status)
        dispute_type = (self.request.GET.get("type") or "").strip()
        if dispute_type:
            qs = qs.filter(dispute_type=dispute_type)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            section="disputes",
            form=DisputeActionForm(),
            status_choices=DisputeCase.STATUS_CHOICES,
            type_choices=DisputeCase.TYPE_CHOICES,
        )
        return ctx


class DisputeDetailView(PlatformAdminBaseMixin, DetailView):
    template_name = "platform_admin/dispute_detail.html"
    required_roles = (ROLE_SUPPORT, ROLE_FINANCE, ROLE_READ_ONLY)
    context_object_name = "dispute"

    def get_queryset(self):
        return DisputeCase.objects.select_related(
            "salon",
            "stylist__user",
            "customer__user",
            "order",
            "order_detail",
            "support_ticket",
            "financial_snapshot",
            "financial_adjustment",
            "resolved_by",
        ).prefetch_related("events")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            section="disputes",
            form=DisputeActionForm(
                initial={
                    "status": self.object.status,
                    "priority": self.object.priority,
                    "resolution": self.object.resolution,
                    "resolution_note": self.object.resolution_note,
                }
            ),
        )
        return ctx


class DisputeActionView(PlatformAdminBaseMixin, View):
    required_roles = (ROLE_SUPPORT, ROLE_FINANCE)

    def post(self, request, pk):
        from apps.main.support_services import log_admin_support_action

        dispute = get_object_or_404(DisputeCase, pk=pk)
        form = DisputeActionForm(request.POST)
        if not form.is_valid():
            messages.error(request, "عملیات پرونده اختلاف معتبر نیست.")
            return redirect("platform_admin:dispute_detail", pk=dispute.pk)
        old_status = dispute.status
        dispute.status = form.cleaned_data["status"]
        dispute.priority = form.cleaned_data.get("priority") or dispute.priority
        dispute.resolution = form.cleaned_data.get("resolution") or dispute.resolution
        dispute.resolution_note = (
            form.cleaned_data.get("resolution_note") or dispute.resolution_note
        )
        if (
            dispute.status
            in {
                "resolved_for_customer",
                "resolved_for_salon",
                "resolved_partially",
                "rejected",
                "closed",
            }
            and not dispute.resolved_at
        ):
            dispute.resolved_at = timezone.now()
            dispute.resolved_by = request.user
        dispute.save(
            update_fields=[
                "status",
                "priority",
                "resolution",
                "resolution_note",
                "resolved_at",
                "resolved_by",
                "updated_at",
            ]
        )
        DisputeEvent.objects.create(
            dispute=dispute,
            event_type="status_changed",
            actor=request.user,
            old_status=old_status,
            new_status=dispute.status,
            note=dispute.resolution_note,
        )
        log_admin_support_action(
            request=request,
            action="dispute.updated",
            target=dispute,
            old_value={"status": old_status},
            new_value={"status": dispute.status, "resolution": dispute.resolution},
            reason=dispute.resolution_note,
        )
        messages.success(request, "پرونده اختلاف به‌روزرسانی شد.")
        return redirect("platform_admin:dispute_detail", pk=dispute.pk)


class InfrastructureOverviewView(PlatformAdminBaseMixin, TemplateView):
    template_name = "platform_admin/infrastructure.html"
    required_roles = (ROLE_SUPPORT, ROLE_READ_ONLY)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            section="infrastructure",
            cache_backend=settings.CACHES.get("default", {}).get("BACKEND", ""),
            celery_enabled=getattr(settings, "LOOMERA_ENABLE_CELERY", False),
            sentry_enabled=bool(getattr(settings, "SENTRY_DSN", "")),
            media_processing_enabled=getattr(
                settings, "LOOMERA_MEDIA_PROCESSING_ENABLED", True
            ),
            recent_jobs=OperationalJobRun.objects.all()[:30],
            failed_jobs=OperationalJobRun.objects.filter(
                status=OperationalJobRun.Status.FAILED
            )[:10],
            media_jobs=MediaProcessingJob.objects.all()[:30],
            pending_media_jobs=_safe_count(
                MediaProcessingJob.objects.filter(
                    status=MediaProcessingJob.Status.PENDING
                )
            ),
        )
        return ctx


class PlatformSettingListView(PlatformAdminBaseMixin, ListView):
    template_name = "platform_admin/settings.html"
    required_roles = (ROLE_SUPER, ROLE_READ_ONLY)
    context_object_name = "settings_list"
    paginate_by = 50

    def get_queryset(self):
        return PlatformSetting.objects.select_related("updated_by").order_by("key")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            section="settings",
            env_flags={
                "BETA_MODE": getattr(settings, "BETA_MODE", True),
                "COMMISSION_ENABLED": getattr(settings, "COMMISSION_ENABLED", False),
                "ONLINE_PAYMENT_ENABLED": getattr(
                    settings, "ONLINE_PAYMENT_ENABLED", False
                ),
                "BNPL_ENABLED": getattr(settings, "BNPL_ENABLED", False),
                "DEBT_ENFORCEMENT_ENABLED": getattr(
                    settings, "DEBT_ENFORCEMENT_ENABLED", False
                ),
            },
        )
        return ctx


class PlatformSettingUpdateView(PlatformAdminBaseMixin, UpdateView):
    model = PlatformSetting
    form_class = PlatformSettingForm
    template_name = "platform_admin/setting_form.html"
    success_url = reverse_lazy("platform_admin:settings")
    required_roles = (ROLE_SUPER,)

    def form_valid(self, form):
        old = (
            PlatformSetting.objects.filter(pk=self.object.pk)
            .values("value", "value_type", "is_sensitive", "is_runtime_editable")
            .first()
            or {}
        )
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        create_admin_audit_log(
            request=self.request,
            action="platform_setting.updated_from_panel",
            target=self.object,
            old_value=old,
            new_value={
                "key": self.object.key,
                "value": "***" if self.object.is_sensitive else self.object.value,
            },
        )
        messages.success(self.request, "تنظیم پلتفرم به‌روزرسانی شد.")
        return response


class AuditLogListView(PlatformAdminBaseMixin, ListView):
    template_name = "platform_admin/audit.html"
    required_roles = (ROLE_SUPER, ROLE_READ_ONLY)
    context_object_name = "logs"
    paginate_by = 40

    def get_queryset(self):
        qs = AdminAuditLog.objects.select_related(
            "actor", "target_content_type"
        ).order_by("-created_at", "-id")
        action = (self.request.GET.get("action") or "").strip()
        if action:
            qs = qs.filter(action__icontains=action)
        return qs


class AnalyticsOverviewView(PlatformAdminBaseMixin, TemplateView):
    template_name = "platform_admin/analytics.html"
    required_roles = (ROLE_SUPPORT, ROLE_FINANCE, ROLE_READ_ONLY)

    def get_context_data(self, **kwargs):
        from apps.analytics.models import (
            DailyPlatformMetric,
            DailySalonMetric,
            DailyStaffMetric,
            DailyContentMetric,
            DailySearchMetric,
            ReportExportJob,
        )

        ctx = super().get_context_data(**kwargs)
        ctx.update(
            section="analytics",
            latest_platform=DailyPlatformMetric.objects.order_by("-date").first(),
            platform_metrics=DailyPlatformMetric.objects.order_by("-date")[:14],
            top_salons=DailySalonMetric.objects.select_related("salon").order_by(
                "-date", "-gross_revenue"
            )[:20],
            top_staff=DailyStaffMetric.objects.select_related(
                "stylist__user", "salon"
            ).order_by("-date", "-net_profit")[:20],
            top_content=DailyContentMetric.objects.select_related("salon").order_by(
                "-date", "-views"
            )[:20],
            top_searches=DailySearchMetric.objects.order_by("-date", "-searches_count")[
                :20
            ],
            export_jobs=ReportExportJob.objects.select_related("requested_by").order_by(
                "-created_at"
            )[:10],
            report_types=ReportExportJob.ReportType.choices,
        )
        return ctx


class AnalyticsExportCreateView(PlatformAdminBaseMixin, View):
    required_roles = (ROLE_SUPPORT, ROLE_FINANCE)

    def post(self, request):
        from apps.analytics.models import ReportExportJob
        from apps.analytics.services import create_report_export_job

        report_type = (
            request.POST.get("report_type") or ReportExportJob.ReportType.PLATFORM_DAILY
        )
        allowed = {choice[0] for choice in ReportExportJob.ReportType.choices}
        if report_type not in allowed:
            messages.error(request, "نوع گزارش معتبر نیست.")
            return redirect("platform_admin:analytics")
        start_date = parse_jalali_input(request.POST.get("start_date"))
        end_date = parse_jalali_input(request.POST.get("end_date"))
        filters = {
            "start_date": start_date.isoformat() if start_date else "",
            "end_date": end_date.isoformat() if end_date else "",
            "salon_id": request.POST.get("salon_id") or "",
        }
        job = create_report_export_job(
            user=request.user, report_type=report_type, filters=filters
        )
        create_admin_audit_log(
            request=request,
            action="analytics.report_export_requested",
            target=job,
            new_value={"report_type": report_type, "filters": filters},
        )
        messages.success(
            request, "درخواست خروجی گزارش ثبت شد. command پردازش خروجی را اجرا کنید."
        )
        return redirect("platform_admin:analytics")
