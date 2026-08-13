from __future__ import annotations

from datetime import datetime, time

from django import forms
from django.db.models import Q
from django.utils import timezone

from apps.dashboards.jalali_utils import (
    format_jalali_numeric,
    parse_jalali_input,
    to_english_digits,
)

from .models import Coupon, DiscountBasket, DiscountBasketDetails, DiscountCampaign


def _build_jalali_date_widget(placeholder: str):
    return forms.TextInput(
        attrs={
            "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-loomera-primary focus:outline-none",
            "placeholder": placeholder,
            "data-jdp": "",
            "data-jdp-only-date": "true",
            "autocomplete": "off",
            "inputmode": "numeric",
        }
    )


def _parse_jalali_datetime(value: str, *, end_of_day: bool = False):
    raw = to_english_digits(value or "").strip()
    if not raw:
        raise forms.ValidationError("این فیلد الزامی است.")

    parts = raw.split()
    date_value = parse_jalali_input(parts[0])
    if not date_value:
        raise forms.ValidationError(
            "تاریخ را به‌صورت شمسی و معتبر وارد کنید؛ مثل ۱۴۰۵/۰۱/۲۰."
        )

    time_value = time(23, 59, 59) if end_of_day else time(0, 0, 0)
    if len(parts) > 1:
        try:
            hh, mm = map(int, parts[1].split(":"))
            time_value = time(hh, mm, 59 if end_of_day else 0)
        except Exception:
            raise forms.ValidationError(
                "بخش ساعت معتبر نیست. نمونه درست: ۱۴۰۵/۰۱/۲۰ 18:30"
            )

    result = datetime.combine(date_value, time_value)
    if timezone.is_naive(result):
        result = timezone.make_aware(result, timezone.get_current_timezone())
    return result


class CouponForm(forms.Form):
    coupon_code = forms.CharField(
        label="",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-purple-500 focus:outline-none",
                "placeholder": "کد تخفیف ",
            }
        ),
    )


class SalonCouponForm(forms.ModelForm):
    start_date = forms.CharField(
        label="شروع اعتبار",
        widget=_build_jalali_date_widget("مثلاً ۱۴۰۵/۰۲/۰۱"),
        help_text="شروع اعتبار از ابتدای این روز شمسی محاسبه می‌شود.",
    )
    end_date = forms.CharField(
        label="پایان اعتبار",
        widget=_build_jalali_date_widget("مثلاً ۱۴۰۵/۰۲/۱۵"),
        help_text="پایان اعتبار تا انتهای این روز شمسی محاسبه می‌شود.",
    )

    def __init__(self, *args, salon=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon
        if self.instance.pk:
            if self.instance.start_date:
                jalali_start = format_jalali_numeric(self.instance.start_date)
                self.initial["start_date"] = jalali_start
                self.fields["start_date"].initial = jalali_start
                self.fields["start_date"].widget.attrs["value"] = jalali_start
            if self.instance.end_date:
                jalali_end = format_jalali_numeric(self.instance.end_date)
                self.initial["end_date"] = jalali_end
                self.fields["end_date"].initial = jalali_end
                self.fields["end_date"].widget.attrs["value"] = jalali_end

    class Meta:
        model = Coupon
        fields = [
            "coupon_code",
            "discount",
            "max_discount_amount",
            "start_date",
            "end_date",
            "is_active",
            "description",
        ]
        widgets = {
            "coupon_code": forms.TextInput(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm uppercase tracking-wide focus:border-loomera-primary focus:outline-none",
                    "placeholder": "مثلاً FIRSTVISIT20",
                    "dir": "ltr",
                }
            ),
            "discount": forms.NumberInput(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-loomera-primary focus:outline-none",
                    "placeholder": "مثلاً 20",
                    "min": "1",
                    "max": "100",
                }
            ),
            "max_discount_amount": forms.NumberInput(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-loomera-primary focus:outline-none",
                    "placeholder": "مثلاً 100000",
                    "min": "0",
                    "step": "1000",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={
                    "class": "h-5 w-5 rounded border-slate-300 text-loomera-primary focus:ring-loomera-primary"
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-7 focus:border-loomera-primary focus:outline-none",
                    "rows": 3,
                    "placeholder": "این کد برای چه کمپینی است و چه قاعده‌ای دارد؟",
                }
            ),
        }
        labels = {
            "coupon_code": "کد تخفیف",
            "discount": "درصد تخفیف",
            "max_discount_amount": "سقف مبلغ تخفیف",
            "is_active": "فعال باشد",
            "description": "توضیحات داخلی",
        }
        help_texts = {
            "max_discount_amount": "مثلاً ۱۰۰۰۰۰ یعنی درصد تخفیف بیش از ۱۰۰ هزار تومان نشود. مقدار صفر یعنی بدون سقف.",
        }

    def clean_coupon_code(self):
        value = (self.cleaned_data.get("coupon_code") or "").strip().upper()
        if (
            self.salon
            and Coupon.objects.filter(salon=self.salon, coupon_code=value)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError(
                "این کد تخفیف قبلاً برای همین مجموعه ثبت شده است."
            )
        return value

    def clean_start_date(self):
        return _parse_jalali_datetime(
            self.cleaned_data.get("start_date") or "", end_of_day=False
        )

    def clean_end_date(self):
        return _parse_jalali_datetime(
            self.cleaned_data.get("end_date") or "", end_of_day=True
        )

    def clean(self):
        cleaned = super().clean()
        start_date = cleaned.get("start_date")
        end_date = cleaned.get("end_date")
        if start_date and end_date and end_date <= start_date:
            raise forms.ValidationError("تاریخ پایان باید بعد از تاریخ شروع باشد.")
        return cleaned


class SalonDiscountBasketForm(forms.ModelForm):
    start_date = forms.CharField(
        label="شروع اعتبار",
        widget=_build_jalali_date_widget("مثلاً ۱۴۰۵/۰۲/۰۱"),
        help_text="شروع اعتبار از ابتدای این روز محاسبه می‌شود.",
    )
    end_date = forms.CharField(
        label="پایان اعتبار",
        widget=_build_jalali_date_widget("مثلاً ۱۴۰۵/۰۲/۱۵"),
        help_text="پایان اعتبار تا انتهای این روز محاسبه می‌شود.",
    )
    services = forms.ModelMultipleChoiceField(
        queryset=None,
        label="خدمات شامل تخفیف",
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="این تخفیف روی هرکدام از خدمات انتخاب‌شده قابل اعمال است؛ مشتری لازم نیست همه خدمات را با هم رزرو کند.",
    )

    class Meta:
        model = DiscountBasket
        fields = [
            "discount_title",
            "discount",
            "max_discount_amount",
            "start_date",
            "end_date",
            "is_active",
            "description",
            "services",
        ]
        widgets = {
            "discount_title": forms.TextInput(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-loomera-primary focus:outline-none",
                    "placeholder": "مثلاً کمپین عروس هفته",
                }
            ),
            "discount": forms.NumberInput(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-loomera-primary focus:outline-none",
                    "placeholder": "مثلاً 15",
                    "min": "1",
                    "max": "100",
                }
            ),
            "max_discount_amount": forms.NumberInput(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-loomera-primary focus:outline-none",
                    "placeholder": "مثلاً 150000",
                    "min": "0",
                    "step": "1000",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={
                    "class": "h-5 w-5 rounded border-slate-300 text-loomera-primary focus:ring-loomera-primary"
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-7 focus:border-loomera-primary focus:outline-none",
                    "rows": 3,
                    "placeholder": "این پیشنهاد برای چه خدماتی و با چه هدفی ساخته شده است؟",
                }
            ),
        }
        labels = {
            "discount_title": "عنوان پیشنهاد",
            "discount": "درصد تخفیف",
            "max_discount_amount": "سقف مبلغ تخفیف",
            "is_active": "فعال باشد",
            "description": "توضیحات داخلی",
        }
        help_texts = {
            "max_discount_amount": "برای نمایش شفاف کمپین و جلوگیری از تخفیف بیش‌ازحد، می‌توانی سقف مبلغی تعیین کنی.",
        }

    def __init__(self, *args, salon=None, **kwargs):
        super().__init__(*args, **kwargs)
        service_manager = getattr(salon, "services", None)
        empty_qs = DiscountBasketDetails._meta.get_field(
            "service"
        ).remote_field.model.objects.none()
        if service_manager is None:
            service_qs = empty_qs
        else:
            service_qs = service_manager.all()
            if self.instance.pk:
                selected_ids = list(
                    self.instance.discount_basket_details1.values_list(
                        "service_id", flat=True
                    )
                )
                service_qs = service_qs.filter(
                    Q(is_active=True) | Q(pk__in=selected_ids)
                ).distinct()
            else:
                service_qs = service_qs.filter(is_active=True)
        self.fields["services"].queryset = service_qs.order_by("service_name")
        if self.instance.pk:
            self.fields["services"].initial = (
                self.instance.discount_basket_details1.values_list(
                    "service_id", flat=True
                )
            )
            if self.instance.start_date:
                jalali_start = format_jalali_numeric(self.instance.start_date)
                self.initial["start_date"] = jalali_start
                self.fields["start_date"].initial = jalali_start
                self.fields["start_date"].widget.attrs["value"] = jalali_start
            if self.instance.end_date:
                jalali_end = format_jalali_numeric(self.instance.end_date)
                self.initial["end_date"] = jalali_end
                self.fields["end_date"].initial = jalali_end
                self.fields["end_date"].widget.attrs["value"] = jalali_end

    def clean_start_date(self):
        return _parse_jalali_datetime(
            self.cleaned_data.get("start_date") or "", end_of_day=False
        )

    def clean_end_date(self):
        return _parse_jalali_datetime(
            self.cleaned_data.get("end_date") or "", end_of_day=True
        )

    def clean(self):
        cleaned = super().clean()
        start_date = cleaned.get("start_date")
        end_date = cleaned.get("end_date")
        services = cleaned.get("services")

        if start_date and end_date and end_date <= start_date:
            raise forms.ValidationError("تاریخ پایان باید بعد از تاریخ شروع باشد.")

        if services is None or not services.exists():
            raise forms.ValidationError(
                "برای ساخت پیشنهاد خدمات، حداقل یک خدمت را انتخاب کن."
            )

        return cleaned

    def save(self, commit=True):
        services = list(self.cleaned_data.get("services") or [])
        instance = super().save(commit=False)
        if commit:
            instance.save()
            selected_ids = {service.id for service in services}
            instance.discount_basket_details1.exclude(
                service_id__in=selected_ids
            ).delete()
            existing = set(
                instance.discount_basket_details1.values_list("service_id", flat=True)
            )
            for service in services:
                if service.id not in existing:
                    DiscountBasketDetails.objects.create(
                        discount_basket=instance, service=service
                    )
        return instance


class SalonDiscountCampaignForm(forms.ModelForm):
    start_date = forms.CharField(
        label="شروع کمپین",
        widget=_build_jalali_date_widget("مثلاً ۱۴۰۵/۰۲/۰۱"),
        help_text="شروع کمپین از ابتدای این روز شمسی محاسبه می‌شود.",
    )
    end_date = forms.CharField(
        label="پایان کمپین",
        widget=_build_jalali_date_widget("مثلاً ۱۴۰۵/۰۲/۱۵"),
        help_text="پایان کمپین تا انتهای این روز شمسی محاسبه می‌شود.",
    )

    class Meta:
        model = DiscountCampaign
        fields = [
            "title",
            "start_date",
            "end_date",
            "coupons",
            "baskets",
            "is_active",
            "description",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-loomera-primary focus:outline-none",
                    "placeholder": "مثلاً کمپین نوروزی رنگ و مراقبت",
                }
            ),
            "coupons": forms.CheckboxSelectMultiple,
            "baskets": forms.CheckboxSelectMultiple,
            "is_active": forms.CheckboxInput(
                attrs={
                    "class": "h-5 w-5 rounded border-slate-300 text-loomera-primary focus:ring-loomera-primary"
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-7 focus:border-loomera-primary focus:outline-none",
                    "rows": 3,
                    "placeholder": "هدف کمپین، کانال تبلیغ، قوانین داخلی یا یادداشت تیم را بنویس.",
                }
            ),
        }
        labels = {
            "title": "عنوان کمپین",
            "coupons": "کدهای تخفیف",
            "baskets": "پیشنهادهای خدمات",
            "is_active": "فعال باشد",
            "description": "توضیحات داخلی",
        }

    def __init__(self, *args, salon=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon
        self.fields["coupons"].queryset = (
            Coupon.objects.filter(salon=salon, is_archived=False).order_by(
                "-is_active", "-start_date", "coupon_code"
            )
            if salon
            else Coupon.objects.none()
        )
        self.fields["baskets"].queryset = (
            DiscountBasket.objects.filter(salon=salon, is_archived=False).order_by(
                "-is_active", "-start_date", "discount_title"
            )
            if salon
            else DiscountBasket.objects.none()
        )
        if self.instance.pk:
            if self.instance.start_date:
                jalali_start = format_jalali_numeric(self.instance.start_date)
                self.initial["start_date"] = jalali_start
                self.fields["start_date"].initial = jalali_start
                self.fields["start_date"].widget.attrs["value"] = jalali_start
            if self.instance.end_date:
                jalali_end = format_jalali_numeric(self.instance.end_date)
                self.initial["end_date"] = jalali_end
                self.fields["end_date"].initial = jalali_end
                self.fields["end_date"].widget.attrs["value"] = jalali_end

    def clean_title(self):
        value = (self.cleaned_data.get("title") or "").strip()
        if (
            self.salon
            and DiscountCampaign.objects.filter(
                salon=self.salon, title=value, is_archived=False
            )
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError(
                "کمپینی با این عنوان برای همین مجموعه وجود دارد."
            )
        return value

    def clean_start_date(self):
        return _parse_jalali_datetime(
            self.cleaned_data.get("start_date") or "", end_of_day=False
        )

    def clean_end_date(self):
        return _parse_jalali_datetime(
            self.cleaned_data.get("end_date") or "", end_of_day=True
        )

    def clean(self):
        cleaned = super().clean()
        start_date = cleaned.get("start_date")
        end_date = cleaned.get("end_date")
        coupons = cleaned.get("coupons")
        baskets = cleaned.get("baskets")
        if start_date and end_date and end_date <= start_date:
            raise forms.ValidationError("تاریخ پایان باید بعد از تاریخ شروع باشد.")
        if not coupons and not baskets:
            raise forms.ValidationError(
                "حداقل یک کد تخفیف یا یک پیشنهاد خدمات به کمپین اضافه کن."
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        coupons = self.cleaned_data.get("coupons")
        baskets = self.cleaned_data.get("baskets")
        has_coupons = bool(coupons and coupons.exists())
        has_baskets = bool(baskets and baskets.exists())
        if has_coupons and has_baskets:
            instance.campaign_type = DiscountCampaign.CampaignType.MIXED
        elif has_coupons:
            instance.campaign_type = DiscountCampaign.CampaignType.COUPON
        elif has_baskets:
            instance.campaign_type = DiscountCampaign.CampaignType.BASKET
        if commit:
            instance.save()
            self.save_m2m()
        return instance
