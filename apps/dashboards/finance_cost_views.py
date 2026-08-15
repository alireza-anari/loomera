from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.accounts.models import Stylist

from apps.dashboards.finance_forms import (
    AppointmentMaterialUsageForm,
    MaterialItemForm,
    ServiceMaterialTemplateForm,
    StylistCommissionRuleForm,
)
from apps.dashboards.jalali_utils import format_jalali_numeric, parse_jalali_input
from apps.dashboards.layout import build_dashboard_context
from apps.orders.models import AppointmentMaterialUsage, OrderDetail
from apps.payments.finance import (
    finalize_order_detail_financials,
    finalize_order_financials,
    release_eligible_salon_wallet_funds_for_salon,
    release_eligible_stylist_wallet_funds_for_salon,
)
from apps.payments.models import (
    OrderDetailFinancialSnapshot,
    StylistWallet,
    StylistWalletTransaction,
    StylistWalletWithdrawalRequest,
)
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

        material_total = materials.count()
        material_active = materials.filter(is_active=True).count()
        template_total = templates.count()
        template_active = templates.filter(is_active=True).count()
        rule_total = rules.count()
        rule_active = rules.filter(is_active=True).count()
        inactive_total = (
            material_total
            - material_active
            + template_total
            - template_active
            + rule_total
            - rule_active
        )

        context = self.base_context(
            request,
            title="هزینه و سهم",
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
                "finance_counts": {
                    "materials": material_total,
                    "materials_active": material_active,
                    "templates": template_total,
                    "templates_active": template_active,
                    "rules": rule_total,
                    "rules_active": rule_active,
                    "inactive": inactive_total,
                },
                "setup_cards": [
                    {
                        "label": "مواد فعال",
                        "value": f"{material_active} از {material_total}",
                        "hint": "مواد پایه برای ثبت مصرف",
                    },
                    {
                        "label": "هزینه‌های خدمت فعال",
                        "value": f"{template_active} از {template_total}",
                        "hint": "مواد متصل به خدمات",
                    },
                    {
                        "label": "قوانین سهم فعال",
                        "value": f"{rule_active} از {rule_total}",
                        "hint": "سهم متخصص برای خدمات",
                    },
                    {
                        "label": "موارد غیرفعال",
                        "value": inactive_total,
                        "hint": "برای سابقه نگه داشته شده‌اند",
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

    UI_STATUS_LABELS = {
        OrderDetailFinancialSnapshot.Status.DRAFT: "در حال تکمیل",
        OrderDetailFinancialSnapshot.Status.FINALIZED: "قطعی",
        OrderDetailFinancialSnapshot.Status.REVERSED: "برگشت‌خورده",
    }

    def _enrich_snapshot(self, snapshot, service_ids_with_templates):
        material_status = _snapshot_material_status(snapshot, service_ids_with_templates)
        snapshot.material_status_label = material_status["label"]
        snapshot.material_status_tone = material_status["tone"]
        snapshot.material_status_hint = material_status["hint"]
        snapshot.material_requires_review = (
            material_status["tone"] == "warning"
            and snapshot.status == OrderDetailFinancialSnapshot.Status.FINALIZED
        )
        snapshot.status_ui_label = self.UI_STATUS_LABELS.get(
            snapshot.status,
            snapshot.get_status_display(),
        )
        snapshot.needs_finance_action = (
            snapshot.status == OrderDetailFinancialSnapshot.Status.DRAFT
            or snapshot.material_requires_review
        )
        if snapshot.status == OrderDetailFinancialSnapshot.Status.DRAFT:
            snapshot.finance_action_reason = "محاسبه مالی این خدمت هنوز قطعی نشده است."
        elif snapshot.material_requires_review:
            snapshot.finance_action_reason = (
                "برای این خدمت الگوی مواد داری، اما در سند قطعی ماده‌ای ثبت نشده است."
            )
        else:
            snapshot.finance_action_reason = ""
        return snapshot

    def get(self, request):
        salon = self.get_salon(request)

        release_eligible_salon_wallet_funds_for_salon(salon)
        release_eligible_stylist_wallet_funds_for_salon(salon)

        base_snapshots = (
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

        raw_status = request.GET.get("status")
        status = (
            OrderDetailFinancialSnapshot.Status.FINALIZED
            if raw_status is None or raw_status == ""
            else raw_status
        )
        valid_statuses = {
            "all",
            OrderDetailFinancialSnapshot.Status.DRAFT,
            OrderDetailFinancialSnapshot.Status.FINALIZED,
            OrderDetailFinancialSnapshot.Status.REVERSED,
        }
        if status not in valid_statuses:
            status = OrderDetailFinancialSnapshot.Status.FINALIZED
        service_id = request.GET.get("service") or ""
        stylist_id = request.GET.get("stylist") or ""
        start_date = parse_jalali_input(request.GET.get("start"))
        end_date = parse_jalali_input(request.GET.get("end"))
        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date

        if service_id:
            base_snapshots = base_snapshots.filter(service_id=service_id)
        if stylist_id:
            base_snapshots = base_snapshots.filter(stylist_id=stylist_id)
        if start_date:
            base_snapshots = base_snapshots.filter(order_detail__date__gte=start_date)
        if end_date:
            base_snapshots = base_snapshots.filter(order_detail__date__lte=end_date)

        finalized_count = base_snapshots.filter(
            status=OrderDetailFinancialSnapshot.Status.FINALIZED
        ).count()
        draft_count = base_snapshots.filter(
            status=OrderDetailFinancialSnapshot.Status.DRAFT
        ).count()
        reversed_count = base_snapshots.filter(
            status=OrderDetailFinancialSnapshot.Status.REVERSED
        ).count()
        scope_total_count = finalized_count + draft_count + reversed_count

        snapshots = base_snapshots
        if status != "all":
            snapshots = snapshots.filter(status=status)

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

        service_ids_for_scope = list(
            base_snapshots.exclude(service_id__isnull=True)
            .values_list("service_id", flat=True)
            .distinct()
        )
        service_ids_with_templates = set(
            ServiceMaterialTemplate.objects.filter(
                salon=salon,
                service_id__in=service_ids_for_scope,
                is_active=True,
            ).values_list("service_id", flat=True)
        )

        snapshot_rows = [
            self._enrich_snapshot(snapshot, service_ids_with_templates)
            for snapshot in list(snapshots[:100])
        ]

        draft_review_rows = [
            self._enrich_snapshot(snapshot, service_ids_with_templates)
            for snapshot in list(
                base_snapshots.filter(
                    status=OrderDetailFinancialSnapshot.Status.DRAFT
                )[:30]
            )
        ]
        recent_finalized_rows = [
            self._enrich_snapshot(snapshot, service_ids_with_templates)
            for snapshot in list(
                base_snapshots.filter(
                    status=OrderDetailFinancialSnapshot.Status.FINALIZED
                )[:100]
            )
        ]
        material_review_rows = [
            snapshot
            for snapshot in recent_finalized_rows
            if snapshot.material_requires_review
        ][:30]
        missing_material_review_count = len(
            [snapshot for snapshot in recent_finalized_rows if snapshot.material_requires_review]
        )

        selected_count = _safe_int(summary.get("count"))
        finalized_percent = _percent(finalized_count, scope_total_count)
        active_filter_count = sum(
            bool(value)
            for value in (
                service_id,
                stylist_id,
                start_date,
                end_date,
                status not in (OrderDetailFinancialSnapshot.Status.FINALIZED, ""),
            )
        )

        finance_status_cards = [
            {
                "label": "قطعی",
                "value": finalized_count,
                "hint": f"{finalized_percent}٪ خدمات این محدوده محاسبه قطعی دارند.",
                "tone": "success",
            },
            {
                "label": "در حال تکمیل",
                "value": draft_count,
                "hint": "این خدمات هنوز نباید جزو سود قطعی حساب شوند.",
                "tone": "warning" if draft_count else "muted",
            },
            {
                "label": "برگشت‌خورده",
                "value": reversed_count,
                "hint": "این اسناد از سود قطعی کنار گذاشته شده‌اند.",
                "tone": "danger" if reversed_count else "muted",
            },
            {
                "label": "بررسی مواد",
                "value": missing_material_review_count,
                "hint": "در ۱۰۰ خدمت قطعی اخیر، الگوی مواد وجود دارد ولی مصرفی ثبت نشده است.",
                "tone": "warning" if missing_material_review_count else "success",
            },
        ]

        # Historical reports must remain filterable even when a service or team
        # member is currently inactive. Creating/editing rules still uses active
        # records; this list is read-only reporting scope.
        services = salon.services.all().distinct().order_by("service_name")
        stylists = (
            salon.stylists.all()
            .select_related("user")
            .order_by("user__name", "user__family")
        )

        if status == "all":
            selected_status_label = "همه وضعیت‌ها"
        else:
            selected_status_label = self.UI_STATUS_LABELS.get(status, "وضعیت انتخاب‌شده")

        context = self.base_context(
            request,
            title="سود خالص",
        )
        context.update(
            {
                "salon": salon,
                "snapshots": snapshot_rows,
                "services": services,
                "stylists": stylists,
                "draft_review_rows": draft_review_rows,
                "material_review_rows": material_review_rows,
                "filters": {
                    "status": status,
                    "service": str(service_id),
                    "stylist": str(stylist_id),
                    "start": format_jalali_numeric(start_date) if start_date else "",
                    "end": format_jalali_numeric(end_date) if end_date else "",
                },
                "active_filter_count": active_filter_count,
                "finance_status_cards": finance_status_cards,
                "profit_scope": {
                    "selected_count": selected_count,
                    "status_label": selected_status_label,
                    "total_count": scope_total_count,
                },
                "profit_overview": {
                    "received": _money(summary.get("paid")),
                    "platform": _money(summary.get("platform")),
                    "materials": _money(summary.get("materials")),
                    "salon_materials": _money(summary.get("materials_salon")),
                    "team_materials": _money(summary.get("materials_stylist")),
                    "team_share": _money(summary.get("stylist")),
                    "profit": _money(summary.get("profit")),
                    "discount": _money(summary.get("discount")),
                },
            }
        )
        return render(request, self.template_name, context)


class SalonStylistWalletsView(_SalonFinanceOperationMixin, View):
    template_name = "dashboards/salon_stylist_wallets.html"

    def get(self, request):
        salon = self.get_salon(request)

        release_eligible_stylist_wallet_funds_for_salon(salon)

        # Finance history must remain visible even if a specialist is later
        # deactivated or removed from the current team. Operational pages may hide
        # former members; finance must preserve their historical money trail.
        current_stylist_ids = set(salon.stylists.values_list("pk", flat=True))

        finalized_snapshots = OrderDetailFinancialSnapshot.objects.filter(
            salon=salon,
            status=OrderDetailFinancialSnapshot.Status.FINALIZED,
        )
        transaction_stylist_ids = set(
            StylistWalletTransaction.objects.filter(salon=salon).values_list(
                "wallet__stylist_id", flat=True
            )
        )
        pending_withdrawals = StylistWalletWithdrawalRequest.objects.filter(
            salon=salon,
            status=StylistWalletWithdrawalRequest.Status.PENDING,
        )
        financial_stylist_ids = (
            current_stylist_ids
            | set(finalized_snapshots.values_list("stylist_id", flat=True))
            | transaction_stylist_ids
            | set(pending_withdrawals.values_list("wallet__stylist_id", flat=True))
        )
        stylists = list(
            Stylist.objects.filter(pk__in=financial_stylist_ids)
            .select_related("user")
            .order_by("user__name", "user__family")
        )
        stylist_ids = [stylist.pk for stylist in stylists]
        earnings_map = {
            row["stylist_id"]: row
            for row in finalized_snapshots.values("stylist_id").annotate(
                services_count=Count("id"),
                stylist_share=Sum("stylist_net_share"),
            )
        }

        balance_map = {
            row["wallet__stylist_id"]: row
            for row in StylistWalletTransaction.objects.filter(
                salon=salon,
                wallet__stylist_id__in=stylist_ids,
            )
            .values("wallet__stylist_id")
            .annotate(
                pending_balance=Sum("pending_delta"),
                available_balance=Sum("available_delta"),
            )
        }

        withdrawal_map = {
            row["wallet__stylist_id"]: row
            for row in pending_withdrawals.values("wallet__stylist_id").annotate(
                pending_withdrawal_count=Count("id"),
                pending_withdrawal_amount=Sum("amount"),
            )
        }

        rows = []
        for stylist in stylists:
            earnings = earnings_map.get(stylist.pk, {})
            balances = balance_map.get(stylist.pk, {})
            withdrawal = withdrawal_map.get(stylist.pk, {})

            available_balance = int(balances.get("available_balance") or 0)
            pending_balance = int(balances.get("pending_balance") or 0)
            pending_withdrawal_amount = int(
                withdrawal.get("pending_withdrawal_amount") or 0
            )

            rows.append(
                {
                    "stylist": stylist,
                    "is_active": stylist.is_active,
                    "is_current_member": stylist.pk in current_stylist_ids,
                    "services_count": earnings.get("services_count") or 0,
                    "stylist_share": earnings.get("stylist_share") or 0,
                    "pending_balance": pending_balance,
                    "available_balance": available_balance,
                    "current_balance": available_balance + pending_balance,
                    "pending_withdrawal_count": withdrawal.get(
                        "pending_withdrawal_count"
                    )
                    or 0,
                    "pending_withdrawal_amount": pending_withdrawal_amount,
                }
            )

        total_available = sum(row["available_balance"] for row in rows)
        total_pending = sum(row["pending_balance"] for row in rows)
        total_earned = sum(int(row["stylist_share"] or 0) for row in rows)
        pending_withdrawal_amount = sum(
            row["pending_withdrawal_amount"] for row in rows
        )
        pending_withdrawal_count = sum(
            row["pending_withdrawal_count"] for row in rows
        )

        context = self.base_context(
            request,
            title="درآمد متخصصان",
            sidebar_active="finance",
        )
        context.update(
            {
                "salon": salon,
                "rows": rows,
                "team_finance_summary": {
                    "earned": _money(total_earned),
                    "available": _money(total_available),
                    "pending": _money(total_pending),
                    "withdrawal_amount": _money(pending_withdrawal_amount),
                    "withdrawal_count": pending_withdrawal_count,
                },
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
