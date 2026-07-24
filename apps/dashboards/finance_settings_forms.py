from decimal import Decimal

from django import forms

from apps.services.models import (
    MaterialItem,
    ServiceMaterialTemplate,
    StylistCommissionRule,
    Services,
)


BASE_INPUT_CLASS = (
    "w-full rounded-2xl border border-loomera-borderSoft bg-white px-4 py-3 "
    "text-sm font-medium text-loomera-textPrimary shadow-sm outline-none transition "
    "placeholder:text-loomera-textMuted focus:border-loomera-primary/50 "
    "focus:ring-4 focus:ring-loomera-primary/10"
)


class MaterialItemForm(forms.ModelForm):
    class Meta:
        model = MaterialItem
        fields = ["name", "unit", "default_unit_cost", "is_active"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": BASE_INPUT_CLASS,
                    "placeholder": "مثلاً رنگ مو، اکسیدان، شامپو",
                }
            ),
            "unit": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "default_unit_cost": forms.NumberInput(
                attrs={"class": BASE_INPUT_CLASS, "min": "0", "placeholder": "تومان"}
            ),
            "is_active": forms.CheckboxInput(
                attrs={
                    "class": "h-5 w-5 rounded border-loomera-border text-loomera-primary focus:ring-loomera-primary/20"
                }
            ),
        }

    def __init__(self, *args, salon=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.salon is not None:
            instance.salon = self.salon
        if commit:
            instance.save()
        return instance


class ServiceMaterialTemplateForm(forms.ModelForm):
    class Meta:
        model = ServiceMaterialTemplate
        fields = ["service", "material", "default_quantity", "is_active"]
        widgets = {
            "service": forms.Select(
                attrs={
                    "class": BASE_INPUT_CLASS,
                }
            ),
            "material": forms.Select(
                attrs={
                    "class": BASE_INPUT_CLASS,
                }
            ),
            "default_quantity": forms.NumberInput(
                attrs={
                    "class": BASE_INPUT_CLASS,
                    "step": "0.001",
                    "min": "0.001",
                    "placeholder": "مقدار پیش‌فرض مصرف",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={
                    "class": "h-5 w-5 rounded border-loomera-borderSoft text-loomera-primary focus:ring-loomera-primary/20",
                }
            ),
        }

    def __init__(self, *args, salon=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon

        if salon:
            self.fields["service"].queryset = salon.services.filter(
                is_active=True
            ).order_by("service_name")

            self.fields["material"].queryset = MaterialItem.objects.filter(
                salon=salon
            ).order_by("name")
        else:
            self.fields["service"].queryset = Services.objects.none()
            self.fields["material"].queryset = MaterialItem.objects.none()
            
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
            "percent",
            "fixed_amount",
            "is_active",
        ]
        widgets = {
            "stylist": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "service": forms.Select(attrs={"class": BASE_INPUT_CLASS}),
            "percent": forms.NumberInput(
                attrs={
                    "class": BASE_INPUT_CLASS,
                    "step": "0.01",
                    "min": "0",
                    "max": "100",
                    "placeholder": "مثلاً 40",
                }
            ),
            "fixed_amount": forms.NumberInput(
                attrs={
                    "class": BASE_INPUT_CLASS,
                    "min": "0",
                    "placeholder": "در صورت مبلغ ثابت، مقدار را وارد کن",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={
                    "class": "h-5 w-5 rounded border-loomera-border text-loomera-primary focus:ring-loomera-primary/20"
                }
            ),
        }

    def __init__(self, *args, salon=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon

        self.fields["stylist"].required = False
        self.fields["service"].required = False
        self.fields["stylist"].empty_label = "همه آرایشگران"
        self.fields["service"].empty_label = "همه خدمات"

        if salon is not None:
            self.fields["stylist"].queryset = (
                salon.stylists.filter(is_active=True)
                .select_related("user")
                .order_by("user__family", "user__name")
            )
            self.fields["service"].queryset = salon.services.filter(
                is_active=True
            ).order_by("service_name")
        else:
            self.fields["stylist"].queryset = self.fields["stylist"].queryset.none()
            self.fields["service"].queryset = self.fields["service"].queryset.none()

    def clean_percent(self):
        value = self.cleaned_data.get("percent") or Decimal("0")
        if value < 0 or value > 100:
            raise forms.ValidationError("درصد سهم باید بین ۰ تا ۱۰۰ باشد.")
        return value

    def clean(self):
        cleaned_data = super().clean()
        percent = cleaned_data.get("percent") or Decimal("0")
        fixed_amount = cleaned_data.get("fixed_amount") or 0

        if percent <= 0 and fixed_amount <= 0:
            raise forms.ValidationError(
                "برای قانون سهم آرایشگر، درصد سهم یا مبلغ ثابت را وارد کن."
            )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)

        if self.salon is not None:
            instance.salon = self.salon

        if commit:
            instance.full_clean()
            instance.save()

        return instance
