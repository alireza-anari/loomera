from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.dashboards.finance_forms import (
    AppointmentMaterialUsageForm,
    MaterialItemForm,
    ServiceMaterialTemplateForm,
    StylistCommissionRuleForm,
)
from apps.dashboards.layout import build_dashboard_context
from apps.orders.models import AppointmentMaterialUsage, OrderDetail
from apps.payments.finance import (
    finalize_order_detail_financials,
    finalize_order_financials,
    release_eligible_salon_wallet_funds_for_salon,
    release_eligible_stylist_wallet_funds_for_salon,
)
from apps.payments.models import OrderDetailFinancialSnapshot, StylistWallet
from apps.salons.models import Salon
from apps.services.models import (
    MaterialItem,
    ServiceMaterialTemplate,
    StylistCommissionRule,
)


def _money(value):
    return f"{int(value or 0):,} تومان"


def _to_decimal(value, default="0"):
    try:
        return Decimal(str(value or default))
    except Exception:
        return Decimal(default)


def _safe_int(value):
    try:
        return int(value or 0)
    except Exception:
        return 0


def _percent(part, total):
    total = _safe_int(total)
    if total <= 0:
        return 0
    return round((_safe_int(part) * 100) / total)


def _snapshot_has_material_rows(snapshot):
    material_snapshot = snapshot.material_snapshot or []
    return bool(material_snapshot) or _safe_int(snapshot.material_cost_total) > 0


def _snapshot_material_status(snapshot, service_ids_with_templates):
    if _snapshot_has_material_rows(snapshot):
        return {
            "label": "مواد ثبت شده",
            "tone": "success",
            "hint": "هزینه مواد در سند مالی لحاظ شده است.",
        }

    if snapshot.service_id in service_ids_with_templates:
        return {
            "label": "نیازمند بررسی مواد",
            "tone": "warning",
            "hint": "برای این خدمت قالب مواد وجود دارد اما در سند فعلی ماده‌ای ثبت نشده است.",
        }

    return {
        "label": "بدون مواد",
        "tone": "muted",
        "hint": "برای این سند ماده مصرفی ثبت نشده است.",
    }


class _SalonFinanceOperationMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if hasattr(request.user, "salon_manager_profile"):
            return super().dispatch(request, *args, **kwargs)

        if hasattr(request.user, "stylist"):
            messages.info(request, "این بخش فقط برای مدیر مجموعه در دسترس است.")
            return redirect("dashboards:stylist_dashboard")

        return redirect("accounts:login")

    def get_salon(self, request):
        return get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

    def base_context(self, request, *, title, sidebar_active="settings"):
        return build_dashboard_context(
            request.user,
            nav_active="home",
            sidebar_active=sidebar_active,
            page_title=title,
            request_path=request.path,
        )


class SalonCostCenterView(_SalonFinanceOperationMixin, View):
    template_name = "dashboards/finance_cost_center.html"

    def _build_context(
        self,
        request,
        salon,
        *,
        material_form=None,
        template_form=None,
        rule_form=None,
    ):
        materials = MaterialItem.objects.filter(salon=salon).order_by(
            "-is_active", "name"
        )

        templates = (
            ServiceMaterialTemplate.objects.filter(salon=salon)
            .select_related("service", "material")
            .order_by("service__service_name", "material__name")
        )

        rules = (
            StylistCommissionRule.objects.filter(salon=salon)
            .select_related("stylist__user", "service")
            .order_by("-is_active", "service__service_name", "stylist__user__name")
        )

        snapshots = OrderDetailFinancialSnapshot.objects.filter(salon=salon)
        summary = snapshots.aggregate(
            finalized_count=Count("id"),
            gross=Sum("gross_amount"),
            materials=Sum("material_cost_total"),
            materials_salon=Sum("material_cost_paid_by_salon"),
            materials_stylist=Sum("material_cost_paid_by_stylist"),
            stylist=Sum("stylist_net_share"),
            salon=Sum("salon_net_share"),
            profit=Sum("salon_net_profit"),
        )

        context = self.base_context(
            request,
            title="هزینه‌ها و سهم متخصصان",
        )
        context.update(
            {
                "salon": salon,
                "material_form": material_form or MaterialItemForm(salon=salon),
                "template_form": template_form
                or ServiceMaterialTemplateForm(salon=salon),
                "rule_form": rule_form or StylistCommissionRuleForm(salon=salon),
                "materials": materials,
                "templates": templates,
                "rules": rules,
                "summary_cards": [
                    {
                        "label": "سند مالی نهایی‌شده",
                        "value": summary.get("finalized_count") or 0,
                    },
                    {"label": "فروش خام خدمات", "value": _money(summary.get("gross"))},
                    {"label": "هزینه مواد", "value": _money(summary.get("materials"))},
                    {
                        "label": "مواد با مجموعه",
                        "value": _money(summary.get("materials_salon")),
                    },
                    {
                        "label": "مواد با متخصص",
                        "value": _money(summary.get("materials_stylist")),
                    },
                    {"label": "سهم متخصصان", "value": _money(summary.get("stylist"))},
                    {"label": "سهم خالص مجموعه", "value": _money(summary.get("salon"))},
                    {
                        "label": "سود خالص مجموعه",
                        "value": _money(summary.get("profit")),
                    },
                ],
            }
        )
        return context

    def get(self, request):
        salon = self.get_salon(request)
        return render(request, self.template_name, self._build_context(request, salon))

    def post(self, request):
        salon = self.get_salon(request)
        action = (request.POST.get("action") or "").strip()

        material_form = MaterialItemForm(salon=salon)
        template_form = ServiceMaterialTemplateForm(salon=salon)
        rule_form = StylistCommissionRuleForm(salon=salon)

        if action == "create_material":
            material_form = MaterialItemForm(request.POST, salon=salon)
            if material_form.is_valid():
                material_form.save()
                messages.success(request, "ماده مصرفی با موفقیت ثبت شد.")
                return redirect("dashboards:finance_cost_center")
            messages.error(request, "اطلاعات ماده مصرفی کامل یا معتبر نیست.")

        elif action == "update_material":
            item = get_object_or_404(
                MaterialItem, pk=request.POST.get("material_id"), salon=salon
            )
            form = MaterialItemForm(request.POST, salon=salon, instance=item)
            if form.is_valid():
                form.save()
                messages.success(request, "ماده مصرفی بروزرسانی شد.")
                return redirect("dashboards:finance_cost_center")
            messages.error(request, "اطلاعات ماده مصرفی معتبر نیست.")

        elif action == "toggle_material":
            item = get_object_or_404(
                MaterialItem, pk=request.POST.get("material_id"), salon=salon
            )
            item.is_active = not item.is_active
            item.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "وضعیت ماده مصرفی تغییر کرد.")
            return redirect("dashboards:finance_cost_center")

        elif action == "create_template":
            template_form = ServiceMaterialTemplateForm(request.POST, salon=salon)
            if template_form.is_valid():
                template_form.save()
                messages.success(request, "قالب مواد مصرفی خدمت ذخیره شد.")
                return redirect("dashboards:finance_cost_center")
            messages.error(request, "اطلاعات قالب مواد مصرفی معتبر نیست.")

        elif action == "update_template":
            item = get_object_or_404(
                ServiceMaterialTemplate, pk=request.POST.get("template_id"), salon=salon
            )
            form = ServiceMaterialTemplateForm(request.POST, salon=salon, instance=item)
            if form.is_valid():
                form.save()
                messages.success(request, "قالب مواد مصرفی خدمت بروزرسانی شد.")
                return redirect("dashboards:finance_cost_center")
            messages.error(request, "اطلاعات قالب مواد مصرفی معتبر نیست.")

        elif action == "toggle_template":
            item = get_object_or_404(
                ServiceMaterialTemplate, pk=request.POST.get("template_id"), salon=salon
            )
            item.is_active = not item.is_active
            item.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "وضعیت قالب مواد مصرفی تغییر کرد.")
            return redirect("dashboards:finance_cost_center")

        elif action == "create_rule":
            rule_form = StylistCommissionRuleForm(request.POST, salon=salon)
            if rule_form.is_valid():
                rule_form.save()
                messages.success(request, "قانون سهم متخصص ذخیره شد.")
                return redirect("dashboards:finance_cost_center")
            messages.error(request, "اطلاعات قانون سهم معتبر نیست.")

        elif action == "update_rule":
            item = get_object_or_404(
                StylistCommissionRule, pk=request.POST.get("rule_id"), salon=salon
            )
            form = StylistCommissionRuleForm(request.POST, salon=salon, instance=item)
            if form.is_valid():
                form.save()
                messages.success(request, "قانون سهم متخصص بروزرسانی شد.")
                return redirect("dashboards:finance_cost_center")
            messages.error(request, "اطلاعات قانون سهم معتبر نیست.")

        elif action == "toggle_rule":
            item = get_object_or_404(
                StylistCommissionRule, pk=request.POST.get("rule_id"), salon=salon
            )
            item.is_active = not item.is_active
            item.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "وضعیت قانون سهم تغییر کرد.")
            return redirect("dashboards:finance_cost_center")

        elif action == "delete_rule":
            item = get_object_or_404(
                StylistCommissionRule, pk=request.POST.get("rule_id"), salon=salon
            )
            item.is_active = False
            item.save(update_fields=["is_active", "updated_at"])
            messages.warning(
                request,
                "قانون سهم غیرفعال شد. برای حفظ سوابق مالی، حذف فیزیکی انجام نشد.",
            )
            return redirect("dashboards:finance_cost_center")

        else:
            messages.error(request, "عملیات انتخاب‌شده معتبر نیست.")

        return render(
            request,
            self.template_name,
            self._build_context(
                request,
                salon,
                material_form=material_form,
                template_form=template_form,
                rule_form=rule_form,
            ),
        )


class AppointmentMaterialUsageView(_SalonFinanceOperationMixin, View):
    template_name = "dashboards/appointment_material_usage.html"

    def _get_detail(self, salon, appointment_id):
        return get_object_or_404(
            OrderDetail.objects.select_related(
                "order",
                "order__customer__user",
                "service",
                "stylist__user",
                "salon",
            ),
            pk=appointment_id,
            salon=salon,
        )

    def _build_context(self, request, salon, detail, form=None):
        usages = (
            AppointmentMaterialUsage.objects.filter(order_detail=detail)
            .select_related("material", "recorded_by")
            .order_by("id")
        )

        templates = (
            ServiceMaterialTemplate.objects.filter(
                salon=salon,
                service=detail.service,
                is_active=True,
            )
            .select_related("material")
            .order_by("material__name")
        )

        snapshot = getattr(detail, "financial_snapshot", None)

        context = self.base_context(
            request,
            title="مواد مصرفی نوبت",
            sidebar_active="appointments",
        )
        context.update(
            {
                "salon": salon,
                "detail": detail,
                "order": detail.order,
                "usages": usages,
                "templates": templates,
                "usage_form": form
                or AppointmentMaterialUsageForm(
                    salon=salon,
                    order_detail=detail,
                ),
                "snapshot": snapshot,
                "material_total": detail.get_material_cost_total(),
                "is_financial_finalized": bool(
                    getattr(detail, "financial_finalized_at", None)
                ),
            }
        )
        return context

    def get(self, request, salon_id, appointment_id):
        salon = get_object_or_404(Salon, pk=salon_id, salon_manager__user=request.user)
        detail = self._get_detail(salon, appointment_id)
        return render(
            request, self.template_name, self._build_context(request, salon, detail)
        )

    def post(self, request, salon_id, appointment_id):
        salon = get_object_or_404(Salon, pk=salon_id, salon_manager__user=request.user)
        detail = self._get_detail(salon, appointment_id)
        action = (request.POST.get("action") or "").strip()

        if getattr(detail, "financial_finalized_at", None) and action not in {
            "finalize_detail_finance"
        }:
            messages.error(
                request, "بعد از نهایی شدن مالی، مواد مصرفی این خدمت قابل تغییر نیست."
            )
            return redirect(
                "dashboards:appointment_material_usage",
                salon_id=salon.id,
                appointment_id=detail.id,
            )

        if action == "create_usage":
            form = AppointmentMaterialUsageForm(
                request.POST,
                salon=salon,
                order_detail=detail,
            )
            if form.is_valid():
                usage = form.save(commit=False)
                usage.recorded_by = request.user
                usage.save()
                messages.success(request, "ماده مصرفی برای این نوبت ثبت شد.")
                return redirect(
                    "dashboards:appointment_material_usage",
                    salon_id=salon.id,
                    appointment_id=detail.id,
                )

            messages.error(request, "اطلاعات ماده مصرفی معتبر نیست.")
            return render(
                request,
                self.template_name,
                self._build_context(request, salon, detail, form=form),
            )

        if action == "generate_from_templates":
            created = detail.ensure_material_usage_from_template(
                recorded_by=request.user
            )
            messages.success(
                request,
                f"{len(created)} مورد از قالب مواد مصرفی خدمت به این نوبت اضافه شد.",
            )
            return redirect(
                "dashboards:appointment_material_usage",
                salon_id=salon.id,
                appointment_id=detail.id,
            )

        if action == "update_usage":
            usage = get_object_or_404(
                AppointmentMaterialUsage,
                pk=request.POST.get("usage_id"),
                order_detail=detail,
            )
            usage.quantity = _to_decimal(request.POST.get("quantity"), "0")
            usage.unit_cost = int(request.POST.get("unit_cost") or 0)
            usage.paid_by = request.POST.get("paid_by") or usage.paid_by
            usage.note = request.POST.get("note") or ""
            usage.recorded_by = request.user
            usage.save()
            messages.success(request, "مواد مصرفی بروزرسانی شد.")
            return redirect(
                "dashboards:appointment_material_usage",
                salon_id=salon.id,
                appointment_id=detail.id,
            )

        if action == "delete_usage":
            usage = get_object_or_404(
                AppointmentMaterialUsage,
                pk=request.POST.get("usage_id"),
                order_detail=detail,
            )
            usage.delete()
            messages.warning(request, "ماده مصرفی از این نوبت حذف شد.")
            return redirect(
                "dashboards:appointment_material_usage",
                salon_id=salon.id,
                appointment_id=detail.id,
            )

        if action == "finalize_detail_finance":
            try:
                snapshot = finalize_order_detail_financials(
                    detail,
                    recorded_by=request.user,
                    require_completed=True,
                )
                messages.success(
                    request,
                    f"محاسبات مالی این خدمت نهایی شد. سهم متخصص: {_money(snapshot.stylist_net_share)} | سهم مجموعه: {_money(snapshot.salon_net_share)}",
                )
            except ValidationError as exc:
                messages.error(request, str(exc))
            return redirect(
                "dashboards:appointment_material_usage",
                salon_id=salon.id,
                appointment_id=detail.id,
            )

        messages.error(request, "عملیات انتخاب‌شده معتبر نیست.")
        return redirect(
            "dashboards:appointment_material_usage",
            salon_id=salon.id,
            appointment_id=detail.id,
        )


class SalonProfitReportView(_SalonFinanceOperationMixin, View):
    template_name = "dashboards/finance_profit_report.html"

    def get(self, request):
        salon = self.get_salon(request)

        release_eligible_salon_wallet_funds_for_salon(salon)
        release_eligible_stylist_wallet_funds_for_salon(salon)

        snapshots = (
            OrderDetailFinancialSnapshot.objects.filter(salon=salon)
            .select_related(
                "order",
                "order_detail",
                "service",
                "stylist__user",
                "commission_rule",
            )
            .order_by("-finalized_at", "-created_at")
        )

        status = request.GET.get("status") or ""
        service_id = request.GET.get("service") or ""
        stylist_id = request.GET.get("stylist") or ""

        if status:
            snapshots = snapshots.filter(status=status)

        if service_id:
            snapshots = snapshots.filter(service_id=service_id)

        if stylist_id:
            snapshots = snapshots.filter(stylist_id=stylist_id)

        summary = snapshots.aggregate(
            count=Count("id"),
            gross=Sum("gross_amount"),
            discount=Sum("discount_allocated"),
            paid=Sum("paid_amount_allocated"),
            platform=Sum("platform_commission_allocated"),
            materials=Sum("material_cost_total"),
            materials_salon=Sum("material_cost_paid_by_salon"),
            materials_stylist=Sum("material_cost_paid_by_stylist"),
            stylist=Sum("stylist_net_share"),
            salon=Sum("salon_net_share"),
            profit=Sum("salon_net_profit"),
        )

        finalized_count = snapshots.filter(
            status=OrderDetailFinancialSnapshot.Status.FINALIZED
        ).count()
        draft_count = snapshots.filter(
            status=OrderDetailFinancialSnapshot.Status.DRAFT
        ).count()
        reversed_count = snapshots.filter(
            status=OrderDetailFinancialSnapshot.Status.REVERSED
        ).count()

        service_ids_for_rows = list(
            snapshots.exclude(service_id__isnull=True)
            .values_list("service_id", flat=True)
            .distinct()
        )
        service_ids_with_templates = set(
            ServiceMaterialTemplate.objects.filter(
                salon=salon,
                service_id__in=service_ids_for_rows,
                is_active=True,
            ).values_list("service_id", flat=True)
        )

        snapshot_rows = list(snapshots[:100])
        missing_material_review_count = 0
        for snapshot in snapshot_rows:
            material_status = _snapshot_material_status(
                snapshot, service_ids_with_templates
            )
            snapshot.material_status_label = material_status["label"]
            snapshot.material_status_tone = material_status["tone"]
            snapshot.material_status_hint = material_status["hint"]
            snapshot.material_requires_review = (
                material_status["tone"] == "warning"
                and snapshot.status == OrderDetailFinancialSnapshot.Status.FINALIZED
            )
            if snapshot.material_requires_review:
                missing_material_review_count += 1

        total_count = _safe_int(summary.get("count"))
        finalized_percent = _percent(finalized_count, total_count)

        finance_quality_cards = [
            {
                "label": "اسناد نهایی‌شده",
                "value": f"{finalized_count} از {total_count}",
                "hint": f"{finalized_percent}٪ اسناد این فیلتر نهایی شده‌اند.",
                "tone": "success" if draft_count == 0 else "warning",
            },
            {
                "label": "پیش‌نویس‌های مالی",
                "value": draft_count,
                "hint": "تا وقتی سند پیش‌نویس است، کیف پول و گزارش سود قطعی نیست.",
                "tone": "warning" if draft_count else "success",
            },
            {
                "label": "برگشت‌خورده",
                "value": reversed_count,
                "hint": "اسناد برگشت‌خورده در تصمیم مالی باید جداگانه بررسی شوند.",
                "tone": "danger" if reversed_count else "muted",
            },
            {
                "label": "نیازمند بررسی مواد",
                "value": missing_material_review_count,
                "hint": "برای بعضی خدمات قالب مواد وجود دارد اما در سند نهایی ماده‌ای ثبت نشده است.",
                "tone": "warning" if missing_material_review_count else "success",
            },
        ]

        formula_cards = [
            {
                "label": "مبنای فروش",
                "value": "قیمت خام - تخفیف + هزینه اضافه",
            },
            {
                "label": "خالص بعد کارمزد",
                "value": "دریافتی بعد تخفیف - کارمزد پلتفرم",
            },
            {
                "label": "هزینه مواد",
                "value": "براساس سیاست قانون سهم یا paid_by مواد",
            },
            {
                "label": "سود مجموعه",
                "value": "سهم مجموعه بعد از کسر مواد مربوط به مجموعه",
            },
        ]

        stylist_wallet_rows = []

        active_stylists = (
            salon.stylists.filter(is_active=True)
            .select_related("user")
            .order_by("user__name", "user__family")
        )

        wallets = (
            StylistWallet.objects.filter(stylist__in=active_stylists)
            .select_related("stylist__user")
        )
        wallet_map = {wallet.stylist_id: wallet for wallet in wallets}

        for stylist in active_stylists:
            wallet = wallet_map.get(stylist.user_id)

            stylist_wallet_rows.append(
                {
                    "stylist": stylist,
                    "pending_balance": wallet.pending_balance_for_salon(salon) if wallet else 0,
                    "available_balance": wallet.available_balance_for_salon(salon) if wallet else 0,
                    "total_balance": wallet.total_balance_for_salon(salon) if wallet else 0,
                }
            )

        services = (
            salon.services.filter(is_active=True).distinct().order_by("service_name")
        )

        stylists = (
            salon.stylists.filter(is_active=True)
            .select_related("user")
            .order_by("user__name", "user__family")
        )

        context = self.base_context(
            request,
            title="گزارش سود خالص",
        )
        context.update(
            {
                "salon": salon,
                "snapshots": snapshot_rows,
                "services": services,
                "stylists": stylists,
                "stylist_wallet_rows": stylist_wallet_rows,
                "filters": {
                    "status": status,
                    "service": str(service_id),
                    "stylist": str(stylist_id),
                },
                "finance_quality_cards": finance_quality_cards,
                "formula_cards": formula_cards,
                "summary_cards": [
                    {"label": "تعداد اسناد", "value": summary.get("count") or 0},
                    {"label": "فروش خام", "value": _money(summary.get("gross"))},
                    {"label": "تخفیف", "value": _money(summary.get("discount"))},
                    {
                        "label": "دریافتی بعد تخفیف",
                        "value": _money(summary.get("paid")),
                    },
                    {
                        "label": "کارمزد پلتفرم",
                        "value": _money(summary.get("platform")),
                    },
                    {"label": "هزینه مواد", "value": _money(summary.get("materials"))},
                    {
                        "label": "مواد با مجموعه",
                        "value": _money(summary.get("materials_salon")),
                    },
                    {
                        "label": "مواد با متخصص",
                        "value": _money(summary.get("materials_stylist")),
                    },
                    {"label": "سهم متخصصان", "value": _money(summary.get("stylist"))},
                    {"label": "سهم مجموعه", "value": _money(summary.get("salon"))},
                    {
                        "label": "سود خالص مجموعه",
                        "value": _money(summary.get("profit")),
                    },
                ],
            }
        )
        return render(request, self.template_name, context)


class SalonStylistWalletsView(_SalonFinanceOperationMixin, View):
    template_name = "dashboards/salon_stylist_wallets.html"

    def get(self, request):
        salon = self.get_salon(request)

        release_eligible_stylist_wallet_funds_for_salon(salon)

        stylists = (
            salon.stylists.filter(is_active=True)
            .select_related("user")
            .order_by("user__name", "user__family")
        )

        wallets = (
            StylistWallet.objects.filter(stylist__in=stylists)
            .select_related("stylist__user")
            .order_by("stylist__user__name", "stylist__user__family")
        )

        wallet_map = {wallet.stylist_id: wallet for wallet in wallets}

        rows = []

        for stylist in stylists:
            wallet = wallet_map.get(stylist.user.id)

            snapshots = OrderDetailFinancialSnapshot.objects.filter(
                salon=salon,
                stylist=stylist,
            )

            totals = snapshots.aggregate(
                services_count=Count("id"),
                gross=Sum("gross_amount"),
                material_cost=Sum("material_cost_total"),
                stylist_share=Sum("stylist_net_share"),
                salon_share=Sum("salon_net_share"),
            )

            rows.append(
                {
                    "stylist": stylist,
                    "wallet": wallet,
                    "services_count": totals.get("services_count") or 0,
                    "gross": totals.get("gross") or 0,
                    "material_cost": totals.get("material_cost") or 0,
                    "stylist_share": totals.get("stylist_share") or 0,
                    "salon_share": totals.get("salon_share") or 0,
                    "pending_balance": (
                        wallet.pending_balance_for_salon(salon) if wallet else 0
                    ),
                    "available_balance": (
                        wallet.available_balance_for_salon(salon) if wallet else 0
                    ),
                    "total_balance": (
                        wallet.total_balance_for_salon(salon) if wallet else 0
                    ),
                }
            )

        snapshots = (
            OrderDetailFinancialSnapshot.objects.filter(salon=salon)
            .select_related("stylist__user", "service", "order", "order_detail")
            .order_by("-finalized_at", "-created_at")[:100]
        )

        summary = OrderDetailFinancialSnapshot.objects.filter(salon=salon).aggregate(
            count=Count("id"),
            gross=Sum("gross_amount"),
            material_cost=Sum("material_cost_total"),
            material_cost_salon=Sum("material_cost_paid_by_salon"),
            material_cost_stylist=Sum("material_cost_paid_by_stylist"),
            stylist_share=Sum("stylist_net_share"),
            salon_share=Sum("salon_net_share"),
            profit=Sum("salon_net_profit"),
        )

        context = self.base_context(
            request,
            title="کیف پول و درآمد متخصصان",
            sidebar_active="finance",
        )
        context.update(
            {
                "salon": salon,
                "rows": rows,
                "snapshots": snapshots,
                "summary_cards": [
                    {"label": "تعداد سند مالی", "value": summary.get("count") or 0},
                    {"label": "فروش خام", "value": _money(summary.get("gross"))},
                    {
                        "label": "هزینه مواد",
                        "value": _money(summary.get("material_cost")),
                    },
                    {
                        "label": "مواد با مجموعه",
                        "value": _money(summary.get("material_cost_salon")),
                    },
                    {
                        "label": "مواد با متخصص",
                        "value": _money(summary.get("material_cost_stylist")),
                    },
                    {
                        "label": "سهم متخصصان",
                        "value": _money(summary.get("stylist_share")),
                    },
                    {
                        "label": "سهم مجموعه",
                        "value": _money(summary.get("salon_share")),
                    },
                    {
                        "label": "سود خالص مجموعه",
                        "value": _money(summary.get("profit")),
                    },
                ],
            }
        )
        return render(request, self.template_name, context)


class ManagerFinalizeAppointmentFinanceView(_SalonFinanceOperationMixin, View):
    def post(self, request, salon_id, appointment_id):
        salon = get_object_or_404(
            Salon,
            pk=salon_id,
            salon_manager__user=request.user,
        )

        detail = get_object_or_404(
            OrderDetail.objects.select_related("order", "salon"),
            pk=appointment_id,
            salon=salon,
        )

        action = (request.POST.get("action") or "").strip()

        try:
            if action == "finalize_detail":
                snapshot = finalize_order_detail_financials(
                    detail,
                    recorded_by=request.user,
                    require_completed=True,
                )
                messages.success(
                    request,
                    f"مالی این خدمت نهایی شد. سهم متخصص: {_money(snapshot.stylist_net_share)} | سهم مجموعه: {_money(snapshot.salon_net_share)}",
                )

            elif action == "finalize_order":
                snapshots = finalize_order_financials(
                    detail.order,
                    recorded_by=request.user,
                    require_all_completed=True,
                )
                messages.success(
                    request,
                    f"محاسبات مالی {len(snapshots)} خدمت این رزرو نهایی شد.",
                )

            else:
                messages.error(request, "عملیات مالی معتبر نیست.")

        except ValidationError as exc:
            messages.error(request, str(exc))

        return redirect(
            "dashboards:appointment_detail",
            salon_id=salon.id,
            appointment_id=detail.id,
        )
