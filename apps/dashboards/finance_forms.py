from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.dashboards.jalali_utils import format_jalali_numeric, parse_jalali_input

from apps.orders.models import AppointmentMaterialUsage
from apps.services.models import (
    MaterialItem,
    ServiceMaterialTemplate,
    StylistCommissionRule,
    Services,
)


BASE_INPUT = (
    "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm "
    "text-slate-800 outline-none transition focus:border-loomera-primary/30 "
    "focus:ring-2 focus:ring-loomera-primary/10"
)


class MaterialItemForm(forms.ModelForm):
    class Meta:
        model = MaterialItem
        fields = [
            "name",
            "unit",
            "default_unit_cost",
            "sku",
            "description",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": BASE_INPUT,
                    "placeholder": "مثلاً رنگ مو، شامپو، روغن ماساژ",
                }
            ),
            "unit": forms.Select(attrs={"class": BASE_INPUT}),
            "default_unit_cost": forms.NumberInput(
                attrs={"class": BASE_INPUT, "min": 0, "placeholder": "مثلاً 50000"}
            ),
            "sku": forms.TextInput(
                attrs={"class": BASE_INPUT, "placeholder": "اختیاری"}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": BASE_INPUT,
                    "rows": 3,
                    "placeholder": "توضیح کوتاه درباره ماده مصرفی",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-slate-300 text-loomera-primary"}
            ),
        }

    def __init__(self, *args, salon=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon
        self.fields["name"].label = "نام ماده"
        self.fields["unit"].label = "واحد مصرف"
        self.fields["default_unit_cost"].label = "هزینه هر واحد"
        self.fields["default_unit_cost"].help_text = "مبلغ معمول خرید یا مصرف هر واحد به تومان."
        self.fields["sku"].label = "کد داخلی (اختیاری)"
        self.fields["description"].label = "یادداشت (اختیاری)"
        self.fields["is_active"].label = "فعال باشد"

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise ValidationError("نام ماده مصرفی الزامی است.")

        qs = MaterialItem.objects.filter(salon=self.salon, name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if self.salon and qs.exists():
            raise ValidationError("این ماده مصرفی قبلاً برای همین سالن ثبت شده است.")

        return name

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.salon:
            instance.salon = self.salon
        if commit:
            instance.save()
        return instance


class ServiceMaterialTemplateForm(forms.ModelForm):
    class Meta:
        model = ServiceMaterialTemplate
        fields = [
            "service",
            "material",
            "default_quantity",
            "unit_cost",
            "paid_by",
            "is_active",
        ]
        widgets = {
            "service": forms.Select(attrs={"class": BASE_INPUT}),
            "material": forms.Select(attrs={"class": BASE_INPUT}),
            "default_quantity": forms.NumberInput(
                attrs={"class": BASE_INPUT, "step": "0.01", "min": 0}
            ),
            "unit_cost": forms.NumberInput(
                attrs={
                    "class": BASE_INPUT,
                    "min": 0,
                    "placeholder": "اگر خالی/صفر باشد از هزینه پیش‌فرض ماده استفاده می‌شود",
                }
            ),
            "paid_by": forms.Select(attrs={"class": BASE_INPUT}),
            "is_active": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-slate-300 text-loomera-primary"}
            ),
        }

    def __init__(self, *args, salon=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon
        self.fields["service"].label = "خدمت"
        self.fields["material"].label = "ماده مصرفی"
        self.fields["default_quantity"].label = "مقدار مصرف معمول"
        self.fields["default_quantity"].help_text = "مقداری که معمولاً برای یک نوبت از این خدمت مصرف می‌شود."
        self.fields["unit_cost"].label = "هزینه هر واحد در این خدمت"
        self.fields["unit_cost"].help_text = "اگر خالی یا صفر باشد، هزینه پیش‌فرض همان ماده استفاده می‌شود."
        self.fields["paid_by"].label = "اگر قانون سهمی نباشد، هزینه مواد با چه کسی است؟"
        self.fields["paid_by"].choices = [
            ("salon", "مجموعه می‌پردازد"),
            ("stylist", "متخصص می‌پردازد"),
            ("shared", "بین مجموعه و متخصص نصف می‌شود"),
        ]
        self.fields["is_active"].label = "فعال باشد"

        if salon:
            service_filter = Q(is_active=True)
            material_filter = Q(is_active=True)
            if self.instance and self.instance.pk:
                if self.instance.service_id:
                    service_filter |= Q(pk=self.instance.service_id)
                if self.instance.material_id:
                    material_filter |= Q(pk=self.instance.material_id)

            self.fields["service"].queryset = (
                Services.objects.filter(services_of_salon=salon)
                .filter(service_filter)
                .distinct()
                .order_by("service_name")
            )
            self.fields["material"].queryset = MaterialItem.objects.filter(
                Q(salon=salon) & material_filter
            ).order_by("name")
        else:
            self.fields["service"].queryset = Services.objects.none()
            self.fields["material"].queryset = MaterialItem.objects.none()


    def clean(self):
        cleaned_data = super().clean()
        service = cleaned_data.get("service")
        material = cleaned_data.get("material")

        if self.salon and service and material:
            qs = ServiceMaterialTemplate.objects.filter(
                salon=self.salon,
                service=service,
                material=material,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise ValidationError(
                    "برای این خدمت، این ماده مصرفی قبلاً در قالب مواد ثبت شده است."
                )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.salon:
            instance.salon = self.salon
        if commit:
            instance.save()
        return instance


class StylistCommissionRuleForm(forms.ModelForm):
    class Meta:
        model = StylistCommissionRule
        fields = [
            "stylist",
            "service",
            "commission_type",
            "percent",
            "fixed_amount",
            "share_base",
            "material_cost_policy",
            "stylist_material_cost_percent",
            "effective_from",
            "effective_to",
            "is_active",
            "note",
        ]
        widgets = {
            "stylist": forms.Select(attrs={"class": BASE_INPUT}),
            "service": forms.Select(attrs={"class": BASE_INPUT}),
            "commission_type": forms.Select(attrs={"class": BASE_INPUT}),
            "percent": forms.NumberInput(
                attrs={"class": BASE_INPUT, "step": "0.01", "min": 0, "max": 100}
            ),
            "fixed_amount": forms.NumberInput(attrs={"class": BASE_INPUT, "min": 0}),
            "share_base": forms.Select(attrs={"class": BASE_INPUT}),
            "material_cost_policy": forms.Select(attrs={"class": BASE_INPUT}),
            "stylist_material_cost_percent": forms.NumberInput(
                attrs={"class": BASE_INPUT, "step": "0.01", "min": 0, "max": 100}
            ),
            "effective_from": forms.TextInput(
                attrs={
                    "class": BASE_INPUT,
                    "data-jdp": "",
                    "data-jalali-date": "",
                    "autocomplete": "off",
                    "inputmode": "numeric",
                    "placeholder": "مثلاً ۱۴۰۵/۰۱/۰۱",
                }
            ),
            "effective_to": forms.TextInput(
                attrs={
                    "class": BASE_INPUT,
                    "data-jdp": "",
                    "data-jalali-date": "",
                    "autocomplete": "off",
                    "inputmode": "numeric",
                    "placeholder": "مثلاً ۱۴۰۵/۰۱/۳۱",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-slate-300 text-loomera-primary"}
            ),
            "note": forms.Textarea(attrs={"class": BASE_INPUT, "rows": 3}),
        }

    def __init__(self, *args, salon=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon
        self.fields["stylist"].label = "متخصص"
        self.fields["service"].label = "خدمت"
        self.fields["commission_type"].label = "روش محاسبه سهم"
        self.fields["commission_type"].choices = [
            ("percent", "درصد از مبلغ"),
            ("fixed", "مبلغ ثابت"),
        ]
        self.fields["percent"].label = "درصد سهم متخصص"
        self.fields["fixed_amount"].label = "مبلغ ثابت سهم متخصص"
        self.fields["share_base"].label = "سهم از چه مبلغی محاسبه شود؟"
        self.fields["share_base"].choices = [
            ("gross_after_discount", "مبلغ خدمت بعد از تخفیف"),
            ("after_platform_commission", "بعد از کسر کارمزد لومرا"),
            ("net_after_materials", "بعد از کسر هزینه مواد"),
        ]
        self.fields["material_cost_policy"].label = "هزینه مواد این متخصص چگونه تقسیم شود؟"
        self.fields["material_cost_policy"].choices = [
            ("salon_pays", "تمام هزینه مواد با مجموعه"),
            ("stylist_pays", "تمام هزینه مواد با متخصص"),
            ("split", "هزینه مواد بین مجموعه و متخصص تقسیم شود"),
        ]
        self.fields["stylist_material_cost_percent"].label = "درصد هزینه مواد با متخصص"
        self.fields["stylist_material_cost_percent"].help_text = "فقط وقتی هزینه مواد مشترک است استفاده می‌شود."
        self.fields["effective_from"].label = "شروع اعتبار (اختیاری)"
        self.fields["effective_to"].label = "پایان اعتبار (اختیاری)"
        self.fields["note"].label = "یادداشت (اختیاری)"
        self.fields["is_active"].label = "فعال باشد"

        for field_name in ("effective_from", "effective_to"):
            current_value = getattr(self.instance, field_name, None)
            if current_value:
                self.initial[field_name] = format_jalali_numeric(current_value)

        if salon:
            stylist_filter = Q(is_active=True)
            service_filter = Q(is_active=True)
            if self.instance and self.instance.pk:
                if self.instance.stylist_id:
                    stylist_filter |= Q(pk=self.instance.stylist_id)
                if self.instance.service_id:
                    service_filter |= Q(pk=self.instance.service_id)

            self.fields["stylist"].queryset = (
                salon.stylists.filter(stylist_filter)
                .select_related("user")
                .order_by("user__name", "user__family")
            )
            self.fields["service"].queryset = (
                Services.objects.filter(services_of_salon=salon)
                .filter(service_filter)
                .distinct()
                .order_by("service_name")
            )
        else:
            self.fields["stylist"].queryset = self.fields["stylist"].queryset.none()
            self.fields["service"].queryset = Services.objects.none()




    def _clean_jalali_date_field(self, field_name):
        raw_value = self.cleaned_data.get(field_name)
        if not raw_value:
            return None
        parsed = parse_jalali_input(raw_value)
        if not parsed:
            raise ValidationError("تاریخ واردشده معتبر نیست.")
        return parsed

    def clean_effective_from(self):
        return self._clean_jalali_date_field("effective_from")

    def clean_effective_to(self):
        return self._clean_jalali_date_field("effective_to")

    def clean(self):
        cleaned_data = super().clean()

        commission_type = cleaned_data.get("commission_type")
        percent = cleaned_data.get("percent") or Decimal("0.00")
        fixed_amount = cleaned_data.get("fixed_amount") or 0
        stylist = cleaned_data.get("stylist")
        service = cleaned_data.get("service")

        if (
            commission_type == StylistCommissionRule.CommissionType.PERCENT
            and percent <= 0
        ):
            raise ValidationError(
                "برای سهم درصدی، درصد سهم متخصص باید بیشتر از صفر باشد."
            )

        if (
            commission_type == StylistCommissionRule.CommissionType.FIXED
            and fixed_amount <= 0
        ):
            raise ValidationError(
                "برای سهم ثابت، مبلغ سهم متخصص باید بیشتر از صفر باشد."
            )

        if stylist and service and not service.stylists.filter(pk=stylist.pk).exists():
            raise ValidationError("این متخصص ارائه‌دهنده این خدمت نیست.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.salon:
            instance.salon = self.salon
        if commit:
            instance.save()
        return instance


class AppointmentMaterialUsageForm(forms.ModelForm):
    class Meta:
        model = AppointmentMaterialUsage
        fields = [
            "material",
            "quantity",
            "unit_cost",
            "paid_by",
            "note",
        ]
        widgets = {
            "material": forms.Select(attrs={"class": BASE_INPUT}),
            "quantity": forms.NumberInput(
                attrs={"class": BASE_INPUT, "step": "0.01", "min": 0}
            ),
            "unit_cost": forms.NumberInput(attrs={"class": BASE_INPUT, "min": 0}),
            "paid_by": forms.Select(attrs={"class": BASE_INPUT}),
            "note": forms.Textarea(attrs={"class": BASE_INPUT, "rows": 3}),
        }

    def __init__(self, *args, salon=None, order_detail=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon
        self.order_detail = order_detail

        if salon:
            self.fields["material"].queryset = MaterialItem.objects.filter(
                salon=salon, is_active=True
            ).order_by("name")
        else:
            self.fields["material"].queryset = MaterialItem.objects.none()


    def clean(self):
        cleaned_data = super().clean()
        material = cleaned_data.get("material")

        if self.order_detail and getattr(
            self.order_detail, "financial_finalized_at", None
        ):
            raise ValidationError(
                "بعد از نهایی شدن مالی، مواد مصرفی این خدمت قابل تغییر نیست."
            )

        if self.order_detail and material:
            qs = AppointmentMaterialUsage.objects.filter(
                order_detail=self.order_detail,
                material=material,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise ValidationError(
                    "این ماده مصرفی برای این آیتم رزرو قبلاً ثبت شده است."
                )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.order_detail:
            instance.order_detail = self.order_detail
        if commit:
            instance.save()
        return instance
