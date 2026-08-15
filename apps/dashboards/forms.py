from datetime import datetime, timedelta, time as dt_time
from apps.dashboards.jalali_utils import (
    format_jalali_numeric,
    format_time_fa,
    parse_jalali_input,
)
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Customer, Stylist
from apps.orders.models import OrderDetail
from apps.orders.booking_utils import (
    get_service_buffer_minutes,
    get_service_duration_minutes,
    slot_is_available,
)
from apps.services.models import Services
from apps.stylists.models import StylistSchedule, StylistTimeOff
from apps.stylists.dashboard_services import validate_stylist_time_window


DASHBOARD_FIELD_CLASS = (
    "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 "
    "text-sm font-bold text-slate-800 outline-none transition "
    "placeholder:text-slate-400 focus:border-loomera-primary/30 "
    "focus:ring-2 focus:ring-loomera-primary/10"
)


def _dashboard_time_choices(
    *, include_blank=False, start_hour=6, end_hour=23, step_minutes=15
):
    choices = [("", "انتخاب نشده")] if include_blank else []
    current = datetime.combine(timezone.localdate(), dt_time(start_hour, 0))
    end = datetime.combine(timezone.localdate(), dt_time(end_hour, 59))

    while current <= end:
        value = current.strftime("%H:%M")
        choices.append((value, format_time_fa(value)))
        current += timedelta(minutes=step_minutes)

    if choices and choices[-1][0] != "23:59":
        choices.append(("23:59", format_time_fa("23:59")))

    return choices


class JalaliDateField(forms.DateField):
    widget = forms.TextInput(
        attrs={
            "data-jdp": "",
            "data-jalali-date": "",
            "data-jdp-only-date": "true",
            "autocomplete": "off",
            "inputmode": "numeric",
            "placeholder": "مثلاً ۱۴۰۵/۰۱/۰۱",
            "class": DASHBOARD_FIELD_CLASS,
        }
    )

    def to_python(self, value):
        if value in self.empty_values:
            return None

        if hasattr(value, "date"):
            return value.date()

        parsed = parse_jalali_input(value)
        if not parsed:
            raise ValidationError("تاریخ واردشده معتبر نیست.")
        return parsed

    def prepare_value(self, value):
        if not value:
            return ""
        return format_jalali_numeric(value) or value


class DashboardManualBookingForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), label="مشتری")
    service = forms.ModelChoiceField(queryset=Services.objects.none(), label="خدمت")
    stylist = forms.ModelChoiceField(queryset=Stylist.objects.none(), label="متخصص")
    appointment_date = JalaliDateField(label="تاریخ رزرو")
    start_time = forms.TimeField(
        label="ساعت شروع",
        input_formats=["%H:%M"],
        widget=forms.Select(choices=_dashboard_time_choices()),
    )
    notes = forms.CharField(
        required=False,
        label="یادداشت داخلی",
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def __init__(self, *args, salon=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon
        field_class = DASHBOARD_FIELD_CLASS

        self.fields["notes"].widget.attrs.update(
            {
                "class": "min-h-28 w-full rounded-[24px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-loomera-primary/30 focus:ring-2 focus:ring-loomera-primary/10",
                "placeholder": "مثلاً توضیح کوتاه برای تیم یا پذیرش",
            }
        )

        if salon is None:
            return

        self.fields["customer"].queryset = (
            Customer.objects.filter(Q(added_by_salon=salon) | Q(orders__salon=salon))
            .select_related("user")
            .distinct()
            .order_by("user__name", "user__family", "user__mobile_number")
        )
        self.fields["service"].queryset = (
            Services.objects.filter(services_of_salon=salon, is_active=True)
            .distinct()
            .order_by("service_name")
        )
        self.fields["stylist"].queryset = (
            salon.stylists.filter(is_active=True)
            .select_related("user")
            .distinct()
            .order_by("user__name", "user__family")
        )
        self.fields["appointment_date"].widget.attrs.update(
            {
                "class": field_class,
                "data-jdp": "",
                "data-jalali-date": "",
                "data-jdp-only-date": "true",
                "autocomplete": "off",
                "inputmode": "numeric",
                "placeholder": "۱۴۰۵/۰۱/۰۱",
            }
        )
        self.fields["start_time"].widget.attrs.update({"class": field_class})
        

    def clean(self):
        cleaned_data = super().clean()
        salon = self.salon
        customer = cleaned_data.get("customer")
        service = cleaned_data.get("service")
        stylist = cleaned_data.get("stylist")
        appointment_date = cleaned_data.get("appointment_date")
        start_time = cleaned_data.get("start_time")

        if not salon or not all(
            [customer, service, stylist, appointment_date, start_time]
        ):
            return cleaned_data

        if appointment_date < timezone.localdate():
            raise ValidationError("برای رزرو دستی، تاریخ نمی‌تواند در گذشته باشد.")

        if (
            not service.stylists.filter(pk=stylist.pk).exists()
            or not stylist.stylists_of_salon.filter(pk=salon.pk).exists()
        ):
            raise ValidationError(
                "متخصص انتخاب‌شده این خدمت را در این مجموعه ارائه نمی‌دهد."
            )

        price = stylist.get_price_for_service(service)
        if price in (None, ""):
            raise ValidationError("برای این خدمت نزد این متخصص قیمت ثبت نشده است.")

        duration = get_service_duration_minutes(service)
        buffer_minutes = get_service_buffer_minutes(service)
        start_dt = datetime.combine(appointment_date, start_time)
        end_dt = start_dt + timedelta(minutes=duration)
        end_time = end_dt.time()

        if not slot_is_available(
            salon=salon,
            stylist=stylist,
            service=service,
            date_value=appointment_date,
            start_time=start_time,
            duration_minutes=duration,
            buffer_minutes=buffer_minutes,
        ):
            raise ValidationError(
                "این زمان دیگر آزاد نیست یا خارج از برنامه کاری متخصص است. "
                "لطفاً یکی از زمان‌های آزاد نمایش‌داده‌شده را انتخاب کن."
            )

        cleaned_data["resolved_price"] = int(price or 0)
        cleaned_data["resolved_duration"] = duration
        cleaned_data["resolved_end_time"] = end_time
        return cleaned_data


class StylistSelfTimeOffForm(forms.Form):
    date = JalaliDateField(label="تاریخ")
    start_time = forms.TimeField(
        required=False,
        label="ساعت شروع",
        input_formats=["%H:%M"],
        widget=forms.Select(choices=_dashboard_time_choices(include_blank=True)),
    )
    end_time = forms.TimeField(
        required=False,
        label="ساعت پایان",
        input_formats=["%H:%M"],
        widget=forms.Select(choices=_dashboard_time_choices(include_blank=True)),
    )
    reason = forms.CharField(
        required=False,
        label="دلیل / توضیح",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": "form-control",
                "placeholder": "مثلاً مرخصی شخصی یا عدم حضور",
            }
        ),
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["date"].widget.attrs.update(
            {
                "class": DASHBOARD_FIELD_CLASS,
                "data-jdp": "",
                "data-jalali-date": "",
                "data-jdp-only-date": "true",
                "autocomplete": "off",
                "inputmode": "numeric",
                "placeholder": "۱۴۰۵/۰۱/۰۱",
            }
        )
        self.fields["start_time"].widget.attrs.update({"class": DASHBOARD_FIELD_CLASS})
        self.fields["end_time"].widget.attrs.update({"class": DASHBOARD_FIELD_CLASS})
        self.fields["reason"].widget.attrs.update(
            {
                "class": DASHBOARD_FIELD_CLASS + " min-h-28",
                "placeholder": "مثلاً مرخصی شخصی یا عدم حضور",
            }
        )

    def clean(self):
        cleaned_data = super().clean()
        date_value = cleaned_data.get("date")
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")

        if date_value and date_value < timezone.localdate():
            raise ValidationError("تاریخ مرخصی نمی‌تواند در گذشته باشد.")

        if (start_time and not end_time) or (end_time and not start_time):
            raise ValidationError(
                "برای مرخصی ساعتی باید ساعت شروع و پایان را با هم وارد کنید."
            )

        if start_time and end_time and end_time <= start_time:
            raise ValidationError("ساعت پایان باید بعد از ساعت شروع باشد.")

        return cleaned_data


class StylistSelfScheduleForm(forms.Form):
    service = forms.ModelChoiceField(
        queryset=Services.objects.none(),
        required=False,
        label="خدمت مرتبط",
    )
    date = JalaliDateField(label="تاریخ برنامه")
    start_time = forms.TimeField(
        label="ساعت شروع",
        input_formats=["%H:%M"],
        widget=forms.Select(choices=_dashboard_time_choices()),
    )
    end_time = forms.TimeField(
        label="ساعت پایان",
        input_formats=["%H:%M"],
        widget=forms.Select(choices=_dashboard_time_choices()),
    )
    note = forms.CharField(
        required=False,
        label="توضیح برای مدیر",
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, salon=None, stylist=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon
        self.stylist = stylist

        field_class = DASHBOARD_FIELD_CLASS

        self.fields["service"].widget.attrs.update({"class": field_class})
        self.fields["date"].widget.attrs.update(
            {
                "class": field_class,
                "data-jdp": "",
                "data-jalali-date": "",
                "data-jdp-only-date": "true",
                "autocomplete": "off",
                "inputmode": "numeric",
                "placeholder": "۱۴۰۵/۰۱/۰۱",
            }
        )
        self.fields["start_time"].widget.attrs.update({"class": field_class})
        self.fields["end_time"].widget.attrs.update({"class": field_class})

        if "note" in self.fields:
            self.fields["note"].widget.attrs.update(
                {
                    "class": field_class + " min-h-28",
                    "placeholder": "مثلاً: امکان حضور در این بازه را دارم.",
                }
            )
        self.fields["note"].widget.attrs.update(
            {
                "class": field_class,
                "placeholder": "مثلاً: امکان حضور در این بازه را دارم.",
            }
        )

        if salon is not None and stylist is not None:
            self.fields["service"].queryset = (
                Services.objects.filter(
                    services_of_salon=salon, stylists=stylist, is_active=True
                )
                .distinct()
                .order_by("service_name")
            )

    def clean(self):
        cleaned_data = super().clean()
        salon = self.salon
        stylist = self.stylist
        service = cleaned_data.get("service")
        date_value = cleaned_data.get("date")
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")

        if not salon or not stylist or not all([date_value, start_time, end_time]):
            return cleaned_data

        if date_value < timezone.localdate():
            raise ValidationError("تاریخ برنامه نمی‌تواند در گذشته باشد.")

        if end_time <= start_time:
            raise ValidationError("ساعت پایان باید بعد از ساعت شروع باشد.")

        if (
            service
            and not Services.objects.filter(
                pk=service.pk, services_of_salon=salon, stylists=stylist, is_active=True
            ).exists()
        ):
            raise ValidationError(
                "خدمت انتخاب‌شده در پوشش فعال شما برای این مجموعه نیست."
            )

        validate_stylist_time_window(
            stylist=stylist,
            salon=salon,
            date_value=date_value,
            start_time=start_time,
            end_time=end_time,
        )

        return cleaned_data


class StylistSelfBookingForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), label="مشتری")
    service = forms.ModelChoiceField(queryset=Services.objects.none(), label="خدمت")
    appointment_date = JalaliDateField(label="تاریخ رزرو")
    start_time = forms.TimeField(
        label="ساعت شروع",
        input_formats=["%H:%M"],
        widget=forms.Select(choices=_dashboard_time_choices()),
    )
    notes = forms.CharField(
        required=False,
        label="یادداشت داخلی",
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def __init__(self, *args, salon=None, stylist=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon
        self.stylist = stylist

        field_class = "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-loomera-primary/30 focus:ring-2 focus:ring-loomera-primary/10"
        self.fields["customer"].widget.attrs.update({"class": field_class})
        self.fields["service"].widget.attrs.update({"class": field_class})
        self.fields["appointment_date"].widget.attrs.update(
            {
                "class": field_class,
                "data-jdp": "",
                "data-jalali-date": "",
                "data-jdp-only-date": "true",
                "autocomplete": "off",
                "inputmode": "numeric",
                "placeholder": "۱۴۰۵/۰۱/۰۱",
            }
        )
        self.fields["start_time"].widget.attrs.update({"class": field_class})
        self.fields["notes"].widget.attrs.update(
            {
                "class": "min-h-28 w-full rounded-[24px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-loomera-primary/30 focus:ring-2 focus:ring-loomera-primary/10",
                "placeholder": "مثلاً توضیح کوتاه برای خودت یا پذیرش",
            }
        )

        if salon is None or stylist is None:
            return

        self.fields["customer"].queryset = (
            Customer.objects.filter(Q(added_by_salon=salon) | Q(orders__salon=salon))
            .select_related("user")
            .distinct()
            .order_by("user__name", "user__family", "user__mobile_number")
        )
        self.fields["service"].queryset = (
            Services.objects.filter(
                services_of_salon=salon, stylists=stylist, is_active=True
            )
            .distinct()
            .order_by("service_name")
        )

    def clean(self):
        cleaned_data = super().clean()
        salon = self.salon
        stylist = self.stylist
        customer = cleaned_data.get("customer")
        service = cleaned_data.get("service")
        appointment_date = cleaned_data.get("appointment_date")
        start_time = cleaned_data.get("start_time")

        if (
            not salon
            or not stylist
            or not all([customer, service, appointment_date, start_time])
        ):
            return cleaned_data

        if appointment_date < timezone.localdate():
            raise ValidationError("برای ثبت نوبت، تاریخ نمی‌تواند در گذشته باشد.")

        if not Services.objects.filter(
            pk=service.pk, services_of_salon=salon, stylists=stylist, is_active=True
        ).exists():
            raise ValidationError("این خدمت در scope فعال شما برای این مجموعه نیست.")

        price = stylist.get_price_for_service(service)
        if price in (None, ""):
            raise ValidationError("برای این خدمت نزد شما قیمت ثبت نشده است.")

        duration = int(getattr(service, "duration_minutes", 0) or 60)
        start_dt = datetime.combine(appointment_date, start_time)
        end_dt = start_dt + timedelta(minutes=duration)
        end_time = end_dt.time()

        validate_stylist_time_window(
            stylist=stylist,
            salon=salon,
            date_value=appointment_date,
            start_time=start_time,
            end_time=end_time,
        )

        cleaned_data["resolved_price"] = int(price or 0)
        cleaned_data["resolved_duration"] = duration
        cleaned_data["resolved_end_time"] = end_time
        return cleaned_data
