from __future__ import annotations

from django import forms

from apps.main.models import DisputeCase, PlatformSetting, SupportTicket, SuspensionRecord
from apps.salons.models import SalonVerificationStatus


_PLATFORM_FIELD_CLASS = (
    "w-full rounded-2xl border border-loomera-borderSoft bg-white px-4 py-2.5 "
    "text-sm text-loomera-textPrimary outline-none transition "
    "focus:border-loomera-primary/50 focus:ring-2 focus:ring-loomera-primary/10"
)
_PLATFORM_TEXTAREA_CLASS = (
    "w-full rounded-2xl border border-loomera-borderSoft bg-white px-4 py-3 "
    "text-sm leading-7 text-loomera-textPrimary outline-none transition "
    "focus:border-loomera-primary/50 focus:ring-2 focus:ring-loomera-primary/10"
)
_PLATFORM_CHECKBOX_CLASS = "h-5 w-5 rounded border-loomera-borderSoft text-loomera-primary focus:ring-loomera-primary/20"


class PlatformStyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            existing = widget.attrs.get("class", "")
            if isinstance(widget, forms.CheckboxInput):
                style = _PLATFORM_CHECKBOX_CLASS
            elif isinstance(widget, forms.Textarea):
                style = _PLATFORM_TEXTAREA_CLASS
            else:
                style = _PLATFORM_FIELD_CLASS
            widget.attrs["class"] = f"{existing} {style}".strip()


class SalonVerificationActionForm(PlatformStyledFormMixin, forms.Form):
    status = forms.ChoiceField(label="وضعیت احراز", choices=SalonVerificationStatus.choices)
    reason = forms.CharField(label="یادداشت/دلیل", required=False, widget=forms.Textarea(attrs={"rows": 3}))


class ModerationActionForm(PlatformStyledFormMixin, forms.Form):
    action = forms.ChoiceField(
        label="عملیات",
        choices=[
            ("accept", "پذیرش گزارش و تعلیق محتوا"),
            ("reject", "رد گزارش"),
            ("remove", "حذف توسط Loomera"),
            ("suspend", "تعلیق تا بررسی"),
        ],
    )
    note = forms.CharField(label="یادداشت", required=False, widget=forms.Textarea(attrs={"rows": 3}))


class SupportStatusForm(PlatformStyledFormMixin, forms.Form):
    status = forms.ChoiceField(label="وضعیت", choices=SupportTicket.STATUS_CHOICES)
    priority = forms.ChoiceField(label="اولویت", choices=SupportTicket.PRIORITY_CHOICES, required=False)
    assigned_team = forms.ChoiceField(label="تیم", choices=SupportTicket.TEAM_CHOICES, required=False)
    admin_reply = forms.CharField(label="پاسخ", required=False, widget=forms.Textarea(attrs={"rows": 4}))
    internal_note = forms.CharField(label="یادداشت داخلی", required=False, widget=forms.Textarea(attrs={"rows": 3}))


class DisputeActionForm(PlatformStyledFormMixin, forms.Form):
    status = forms.ChoiceField(label="وضعیت", choices=DisputeCase.STATUS_CHOICES)
    priority = forms.ChoiceField(label="اولویت", choices=DisputeCase.PRIORITY_CHOICES, required=False)
    resolution = forms.CharField(label="نتیجه", required=False, max_length=255)
    resolution_note = forms.CharField(label="یادداشت نتیجه", required=False, widget=forms.Textarea(attrs={"rows": 3}))


class SuspensionActionForm(PlatformStyledFormMixin, forms.Form):
    reason = forms.CharField(label="دلیل", max_length=255)
    user_facing_reason = forms.CharField(label="دلیل قابل نمایش", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    expires_at = forms.DateTimeField(label="تاریخ پایان", required=False)
    internal_note = forms.CharField(label="یادداشت داخلی", required=False, widget=forms.Textarea(attrs={"rows": 3}))


class PlatformSettingForm(PlatformStyledFormMixin, forms.ModelForm):
    class Meta:
        model = PlatformSetting
        fields = ["key", "value", "value_type", "description", "is_sensitive", "is_runtime_editable"]
        widgets = {
            "value": forms.Textarea(attrs={"rows": 4, "dir": "ltr"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }
