from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.salons.models import Salon

from .finance_settings_forms import (
    MaterialItemForm,
    ServiceMaterialTemplateForm,
    StylistCommissionRuleForm,
)
from .layout import build_dashboard_context
from apps.services.models import (
    MaterialItem,
    ServiceMaterialTemplate,
    StylistCommissionRule,
)


def _money(value):
    return f"{int(value or 0):,} تومان"


def _rule_value_label(rule):
    percent = getattr(rule, "percent", None) or 0
    fixed_amount = getattr(rule, "fixed_amount", None) or 0

    if fixed_amount:
        return _money(fixed_amount)

    return f"{percent}%"


class SalonFinanceMaterialSettingsView(LoginRequiredMixin, View):
    template_name = "dashboards/salon_finance_settings.html"

    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, "salon_manager_profile"):
            if hasattr(request.user, "stylist"):
                messages.info(request, "این بخش فقط برای مدیر مجموعه در دسترس است.")
                return redirect("dashboards:stylist_dashboard")
            return redirect("accounts:login")
        return super().dispatch(request, *args, **kwargs)

    def _get_salon(self, request):
        return get_object_or_404(
            Salon.objects.prefetch_related("services", "stylists__user"),
            salon_manager__user=request.user,
        )

    def _context(
        self, request, salon, *, material_form=None, template_form=None, rule_form=None
    ):
        materials = list(
            MaterialItem.objects.filter(salon=salon).order_by("-is_active", "name")
        )
        templates = list(
            ServiceMaterialTemplate.objects.filter(salon=salon)
            .select_related("service", "material")
            .order_by("service__service_name", "material__name")
        )
        rules = list(
            StylistCommissionRule.objects.filter(salon=salon)
            .select_related("stylist__user", "service")
            .order_by("-is_active", "-updated_at")
        )
        active_templates = sum(1 for item in templates if item.is_active)
        active_rules = sum(1 for item in rules if item.is_active)
        material_total_default_cost = sum(
            item.default_unit_cost or 0 for item in materials if item.is_active
        )

        context = build_dashboard_context(
            request.user,
            nav_active="home",
            sidebar_active="settings",
            page_title="مواد و قوانین مالی مجموعه",
            request_path=request.path,
        )
        context.update(
            {
                "salon": salon,
                "material_form": material_form
                or MaterialItemForm(salon=salon, initial={"is_active": True}),
                "template_form": template_form
                or ServiceMaterialTemplateForm(
                    salon=salon, initial={"is_active": True}
                ),
                "rule_form": rule_form
                or StylistCommissionRuleForm(
                    salon=salon,
                    initial={"is_active": True},
                ),
                "materials": materials,
                "templates": templates,
                "rules": rules,
                "materials_count": len(materials),
                "active_materials_count": sum(
                    1 for item in materials if item.is_active
                ),
                "templates_count": len(templates),
                "active_templates_count": active_templates,
                "rules_count": len(rules),
                "active_rules_count": active_rules,
                "material_total_default_cost_label": _money(
                    material_total_default_cost
                ),
                "service_count": salon.services.filter(is_active=True).count(),
                "stylist_count": salon.stylists.filter(is_active=True).count(),
                "calendar_url": reverse(
                    "dashboards:appointment_calendar", kwargs={"salon_id": salon.id}
                ),
                "payout_url": reverse("dashboards:payout_settings"),
                "rule_value_label": _rule_value_label,
            }
        )
        return context

    def get(self, request):
        salon = self._get_salon(request)
        return render(request, self.template_name, self._context(request, salon))

    def post(self, request):
        salon = self._get_salon(request)
        action = request.POST.get("action")

        if action == "create_material":
            form = MaterialItemForm(request.POST, salon=salon)
            if form.is_valid():
                form.save()
                messages.success(request, "ماده اولیه مجموعه ثبت شد.")
                return redirect("dashboards:finance_materials")
            messages.error(request, "فرم ماده اولیه کامل نیست.")
            return render(
                request,
                self.template_name,
                self._context(request, salon, material_form=form),
            )

        if action == "toggle_material":
            material = get_object_or_404(
                MaterialItem, pk=request.POST.get("material_id"), salon=salon
            )
            material.is_active = not material.is_active
            material.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "وضعیت ماده اولیه تغییر کرد.")
            return redirect("dashboards:finance_materials")

        if action == "create_template":
            form = ServiceMaterialTemplateForm(request.POST, salon=salon)
            if form.is_valid():
                form.save()
                messages.success(request, "قالب مواد مصرفی خدمت ثبت شد.")
                return redirect("dashboards:finance_materials")
            messages.error(request, "فرم قالب خدمت کامل نیست.")
            return render(
                request,
                self.template_name,
                self._context(request, salon, template_form=form),
            )

        if action == "delete_template":
            template = get_object_or_404(
                ServiceMaterialTemplate, pk=request.POST.get("template_id"), salon=salon
            )
            template.delete()
            messages.success(request, "قالب مواد مصرفی حذف شد.")
            return redirect("dashboards:finance_materials")

        if action == "create_rule":
            form = StylistCommissionRuleForm(request.POST, salon=salon)
            if form.is_valid():
                form.save()
                messages.success(request, "قانون سهم متخصص ثبت شد.")
                return redirect("dashboards:finance_materials")
            messages.error(request, "فرم قانون سهم متخصص کامل نیست.")
            return render(
                request,
                self.template_name,
                self._context(request, salon, rule_form=form),
            )

        if action == "toggle_rule":
            rule = get_object_or_404(
                StylistCommissionRule, pk=request.POST.get("rule_id"), salon=salon
            )
            rule.is_active = not rule.is_active
            rule.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "وضعیت قانون سهم تغییر کرد.")
            return redirect("dashboards:finance_materials")

        if action == "delete_rule":
            rule = get_object_or_404(
                StylistCommissionRule, pk=request.POST.get("rule_id"), salon=salon
            )
            rule.delete()
            messages.success(request, "قانون سهم متخصص حذف شد.")
            return redirect("dashboards:finance_materials")

        messages.error(request, "درخواست نامعتبر است.")
        return redirect("dashboards:finance_materials")
