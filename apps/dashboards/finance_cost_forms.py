from decimal import Decimal

from django import forms

from apps.orders.models import AppointmentMaterialUsage
from apps.services.models import MaterialItem


BASE_INPUT_CLASS = (
    "w-full rounded-2xl border border-loomera-borderSoft bg-white px-4 py-3 "
    "text-sm font-medium text-loomera-textPrimary shadow-sm outline-none transition "
    "placeholder:text-loomera-textMuted focus:border-loomera-primary/50 "
    "focus:ring-4 focus:ring-loomera-primary/10"
)


class AppointmentMaterialUsageForm(forms.Form):
    material = forms.ModelChoiceField(
        queryset=MaterialItem.objects.none(),
        required=False,
        label="ماده مصرفی موجود",
        empty_label="انتخاب از مواد ثبت‌شده",
        widget=forms.Select(attrs={"class": BASE_INPUT_CLASS, "data-material-select": "true"}),
    )
    material_name = forms.CharField(
        required=False,
        max_length=120,
        label="یا نام ماده جدید",
        widget=forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "مثلاً رنگ مو، اکسیدان، شامپو..."}),
    )
    unit = forms.ChoiceField(
        required=False,
        choices=MaterialItem.Unit.choices,
        label="واحد",
        widget=forms.Select(attrs={"class": BASE_INPUT_CLASS}),
    )
    quantity = forms.DecimalField(
        min_value=Decimal("0.001"),
        max_digits=9,
        decimal_places=3,
        label="مقدار مصرف",
        widget=forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "step": "0.001", "min": "0.001", "placeholder": "مثلاً 30"}),
    )
    unit_cost = forms.IntegerField(
        min_value=0,
        label="هزینه هر واحد",
        widget=forms.NumberInput(attrs={"class": BASE_INPUT_CLASS, "min": "0", "placeholder": "تومان"}),
    )
    paid_by = forms.ChoiceField(
        choices=AppointmentMaterialUsage.PaidBy.choices,
        label="هزینه با",
        widget=forms.Select(attrs={"class": BASE_INPUT_CLASS}),
    )
    note = forms.CharField(
        required=False,
        max_length=255,
        label="یادداشت",
        widget=forms.TextInput(attrs={"class": BASE_INPUT_CLASS, "placeholder": "اختیاری"}),
    )

    def __init__(self, *args, salon=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon
        if salon:
            self.fields["material"].queryset = MaterialItem.objects.filter(salon=salon, is_active=True).order_by("name")

    def clean(self):
        cleaned = super().clean()
        material = cleaned.get("material")
        material_name = (cleaned.get("material_name") or "").strip()
        if not material and not material_name:
            raise forms.ValidationError("یک ماده مصرفی موجود را انتخاب کن یا نام ماده جدید را بنویس.")
        return cleaned

    def save(self, *, order_detail=None, appointment=None):
        # `appointment` is kept as a backward-compatible alias for older callers;
        # the current data model stores usages against OrderDetail.
        detail = order_detail or appointment
        if detail is None:
            raise ValueError("AppointmentMaterialUsageForm.save() requires order_detail.")

        material = self.cleaned_data.get("material")
        material_name = (self.cleaned_data.get("material_name") or "").strip()
        unit = self.cleaned_data.get("unit") or MaterialItem.Unit.OTHER
        unit_cost = int(self.cleaned_data.get("unit_cost") or 0)
        if material is None:
            material, _ = MaterialItem.objects.get_or_create(
                salon=detail.salon,
                name=material_name,
                defaults={"unit": unit, "default_unit_cost": unit_cost, "is_active": True},
            )
        elif unit_cost and material.default_unit_cost != unit_cost:
            material.default_unit_cost = unit_cost
            material.save(update_fields=["default_unit_cost", "updated_at"])

        return AppointmentMaterialUsage.objects.create(
            order_detail=detail,
            material=material,
            quantity=self.cleaned_data["quantity"],
            unit_cost=unit_cost,
            paid_by=self.cleaned_data["paid_by"],
            note=(self.cleaned_data.get("note") or "").strip(),
        )
