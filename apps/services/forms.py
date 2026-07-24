from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import Stylist
from .models import ServiceFeature, ServicePrice, Services


_PERSIAN_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _normalize_number_input(value):
    if value in (None, ""):
        return value
    normalized = str(value).translate(_PERSIAN_DIGIT_MAP)
    normalized = (
        normalized.replace(",", "")
        .replace("٬", "")
        .replace(" ", "")
        .replace("تومان", "")
        .strip()
    )
    return normalized


class StylistServiceForm(forms.Form):
    """Manage a salon-specific copy of a platform catalog service.

    Managers must choose a service from the platform catalog. Editable fields are
    saved only on the salon-specific service instance, so changing duration,
    buffer, price or description for one salon never mutates the global catalog
    service or another salon's configuration.
    """

    catalog_service = forms.ModelChoiceField(
        queryset=Services.objects.none(),
        label="خدمت پایه",
        required=True,
        empty_label="یک خدمت از کاتالوگ انتخاب کن",
        error_messages={"required": "خدمت پایه را از کاتالوگ انتخاب کن."},
        widget=forms.Select(
            attrs={
                "class": "hidden",
                "data-catalog-service-select": "true",
                "aria-hidden": "true",
                "tabindex": "-1",
            }
        ),
    )
    duration_minutes = forms.IntegerField(
        label="مدت زمان خدمت (دقیقه)",
        min_value=1,
        required=True,
        error_messages={
            "required": "مدت زمان خدمت را وارد کن.",
            "invalid": "مدت زمان خدمت معتبر نیست.",
            "min_value": "مدت زمان باید حداقل یک دقیقه باشد.",
        },
        widget=forms.NumberInput(
            attrs={
                "class": "w-full rounded-2xl border border-loomera-borderSoft bg-white px-4 py-3 text-sm font-bold text-loomera-textPrimary outline-none transition focus:border-loomera-primary/40 focus:ring-4 focus:ring-loomera-primary/10",
                "placeholder": "مثلاً ۳۰",
                "inputmode": "numeric",
                "dir": "ltr",
                "min": "1",
            }
        ),
    )
    buffer_minutes = forms.IntegerField(
        label="بافر بعد از خدمت (دقیقه)",
        min_value=0,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "w-full rounded-2xl border border-loomera-borderSoft bg-white px-4 py-3 text-sm font-bold text-loomera-textPrimary outline-none transition focus:border-loomera-primary/40 focus:ring-4 focus:ring-loomera-primary/10",
                "placeholder": "اگر خالی بماند، ۱۰ دقیقه ثبت می‌شود",
                "inputmode": "numeric",
                "dir": "ltr",
                "min": "0",
            }
        ),
        error_messages={
            "invalid": "بافر بعد از خدمت معتبر نیست.",
            "min_value": "بافر بعد از خدمت نمی‌تواند منفی باشد.",
        },
    )
    base_price = forms.IntegerField(
        label="قیمت پایه مجموعه (تومان)",
        min_value=0,
        required=True,
        error_messages={
            "required": "قیمت پایه مجموعه را وارد کن.",
            "invalid": "قیمت پایه معتبر نیست.",
            "min_value": "قیمت پایه نمی‌تواند منفی باشد.",
        },
        widget=forms.NumberInput(
            attrs={
                "class": "w-full rounded-2xl border border-loomera-borderSoft bg-white px-4 py-3 text-left text-sm font-bold text-loomera-textPrimary outline-none transition focus:border-loomera-primary/40 focus:ring-4 focus:ring-loomera-primary/10",
                "placeholder": "مثلاً ۳۵۰۰۰۰",
                "inputmode": "numeric",
                "dir": "ltr",
                "min": "0",
                "data-base-price-input": "true",
            }
        ),
    )
    description = forms.CharField(
        label="توضیح کامل مجموعه برای این خدمت",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "w-full rounded-2xl border border-loomera-borderSoft bg-white px-4 py-3 text-sm font-bold leading-7 text-loomera-textPrimary outline-none transition focus:border-loomera-primary/40 focus:ring-4 focus:ring-loomera-primary/10",
                "rows": 8,
                "placeholder": "جزئیات اجرا، نکات مهم، مواد مصرفی یا تفاوت روش مجموعه خودت را بنویس",
            }
        ),
    )
    stylists = forms.ModelMultipleChoiceField(
        queryset=Stylist.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="اعضای تیم ارائه‌دهنده این خدمت",
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.salon = kwargs.pop("salon", None)
        self.instance = kwargs.pop("instance", None)
        super().__init__(*args, **kwargs)

        catalog_qs = Services.objects.filter(
            is_active=True,
            is_platform_catalog=True,
        ).prefetch_related("service_group").order_by("service_name", "id")
        self.fields["catalog_service"].queryset = catalog_qs

        if self.salon:
            stylists_qs = (
                self.salon.stylists.all()
                .select_related("user")
                .order_by("user__family", "user__name")
            )
            self.fields["stylists"].queryset = stylists_qs
        else:
            stylists_qs = Stylist.objects.none()

        for stylist in stylists_qs:
            field_name = f"price_for_stylist_{stylist.pk}"
            self.fields[field_name] = forms.IntegerField(
                required=False,
                label=f"قیمت برای {stylist.get_fullName()}",
                min_value=0,
                error_messages={
                    "invalid": "قیمت واردشده معتبر نیست.",
                    "min_value": "قیمت نمی‌تواند منفی باشد.",
                },
                widget=forms.NumberInput(
                    attrs={
                        "class": "w-full rounded-2xl border border-loomera-borderSoft bg-white px-4 py-3 text-left text-sm font-bold text-loomera-textPrimary outline-none transition focus:border-loomera-primary/40 focus:ring-4 focus:ring-loomera-primary/10",
                        "placeholder": "اگر خالی بماند، قیمت پایه مجموعه استفاده می‌شود",
                        "inputmode": "numeric",
                        "dir": "ltr",
                        "min": "0",
                        "data-stylist-price": "true",
                    }
                ),
            )

        if self.instance and self.instance.pk:
            source_service = self.instance.catalog_source or (
                self.instance if self.instance.is_platform_catalog else None
            )
            if source_service:
                self.fields["catalog_service"].initial = source_service.pk
            self.fields["catalog_service"].disabled = True
            self.fields["duration_minutes"].initial = self.instance.duration_minutes
            self.fields["buffer_minutes"].initial = self.instance.buffer_minutes
            self.fields["base_price"].initial = self.instance.base_price
            self.fields["description"].initial = self.instance.description
            self.fields["stylists"].initial = list(self.instance.stylists.values_list("pk", flat=True))

            for price_obj in self.instance.service_prices.all():
                field_name = f"price_for_stylist_{price_obj.stylist.pk}"
                if field_name in self.fields:
                    self.fields[field_name].initial = price_obj.price
        else:
            self.fields["buffer_minutes"].initial = 10

    def full_clean(self):
        if self.is_bound and hasattr(self.data, "copy"):
            mutable_data = self.data.copy()
            numeric_names = ["base_price", "duration_minutes", "buffer_minutes"]
            numeric_names.extend(
                name for name in self.fields.keys() if name.startswith("price_for_stylist_")
            )
            for name in numeric_names:
                if name in mutable_data:
                    mutable_data[name] = _normalize_number_input(mutable_data.get(name))
            self.data = mutable_data
        return super().full_clean()

    def clean_duration_minutes(self):
        value = _normalize_number_input(self.cleaned_data.get("duration_minutes"))
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValidationError("مدت زمان خدمت معتبر نیست.")
        if value <= 0:
            raise ValidationError("مدت زمان باید حداقل یک دقیقه باشد.")
        return value

    def clean_buffer_minutes(self):
        raw_value = self.data.get(self.add_prefix("buffer_minutes"), self.cleaned_data.get("buffer_minutes"))
        value = _normalize_number_input(raw_value)
        if value in (None, ""):
            return 10
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValidationError("بافر بعد از خدمت معتبر نیست.")
        if value < 0:
            raise ValidationError("بافر بعد از خدمت نمی‌تواند منفی باشد.")
        return value

    def clean_base_price(self):
        raw_value = self.data.get(self.add_prefix("base_price"), self.cleaned_data.get("base_price"))
        value = _normalize_number_input(raw_value)
        if value in (None, ""):
            raise ValidationError("قیمت پایه مجموعه را وارد کن.")
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValidationError("قیمت پایه معتبر نیست.")
        if value < 0:
            raise ValidationError("قیمت پایه نمی‌تواند منفی باشد.")
        return value

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()

    def clean(self):
        cleaned_data = super().clean()
        source_service = cleaned_data.get("catalog_service")
        selected_stylists = cleaned_data.get("stylists") or []
        base_price = cleaned_data.get("base_price")

        if self.salon and source_service and not (self.instance and self.instance.pk):
            duplicate_qs = self.salon.services.filter(
                Q(pk=source_service.pk) | Q(catalog_source=source_service) | Q(service_name=source_service.service_name)
            )
            if duplicate_qs.exists():
                self.add_error("catalog_service", "این خدمت قبلاً برای این مجموعه اضافه شده است. از صفحه منوی خدمات آن را ویرایش کن.")

        for stylist in selected_stylists:
            field_name = f"price_for_stylist_{stylist.pk}"
            if field_name not in self.fields:
                continue
            raw_price = self.data.get(self.add_prefix(field_name), cleaned_data.get(field_name))
            normalized = _normalize_number_input(raw_price)
            if normalized in (None, ""):
                cleaned_data[field_name] = base_price
                continue
            try:
                normalized = int(normalized)
            except (TypeError, ValueError):
                self.add_error(field_name, "قیمت واردشده معتبر نیست.")
                continue
            if normalized < 0:
                self.add_error(field_name, "قیمت نمی‌تواند منفی باشد.")
                continue
            cleaned_data[field_name] = normalized

        return cleaned_data

    def _copy_service_features(self, *, source_service, target_service):
        existing = set(
            ServiceFeature.objects.filter(service=target_service).values_list("feature_id", "filter_value_id", "value")
        )
        to_create = []
        for item in ServiceFeature.objects.filter(service=source_service):
            key = (item.feature_id, item.filter_value_id, item.value)
            if key in existing:
                continue
            to_create.append(
                ServiceFeature(
                    service=target_service,
                    feature=item.feature,
                    value=item.value,
                    filter_value=item.filter_value,
                )
            )
        if to_create:
            ServiceFeature.objects.bulk_create(to_create)

    @transaction.atomic
    def save(self, commit=True, salon=None):
        salon = salon or self.salon
        source_service = self.cleaned_data["catalog_service"]

        if self.instance and self.instance.pk:
            instance = self.instance
        else:
            instance = Services(
                service_name=source_service.service_name,
                summery_description=source_service.summery_description,
                service_image=source_service.service_image,
                is_active=True,
                allow_indexing=False,
                is_platform_catalog=False,
                catalog_source=source_service,
            )

        instance.duration_minutes = int(self.cleaned_data.get("duration_minutes") or source_service.duration_minutes or 30)
        instance.buffer_minutes = int(self.cleaned_data.get("buffer_minutes") or 10)
        instance.base_price = int(self.cleaned_data.get("base_price") or source_service.base_price or 0)
        instance.description = self.cleaned_data.get("description") or source_service.description or ""
        instance.is_platform_catalog = False
        if not instance.catalog_source_id:
            instance.catalog_source = source_service
        instance.allow_indexing = False

        if commit:
            instance.save()
            instance.service_group.set(source_service.service_group.all())
            self._copy_service_features(source_service=source_service, target_service=instance)

        if salon:
            instance.services_of_salon.add(salon)

        instance.stylists.set(self.cleaned_data.get("stylists") or [])
        instance.service_prices.all().delete()

        selected_stylists = self.cleaned_data.get("stylists") or []
        base_price = self.cleaned_data.get("base_price")
        prices_to_create = []
        for stylist in selected_stylists:
            price_field_name = f"price_for_stylist_{stylist.pk}"
            specific_price = self.cleaned_data.get(price_field_name)
            final_price = specific_price if specific_price not in (None, "") else base_price
            prices_to_create.append(ServicePrice(service=instance, stylist=stylist, price=int(final_price or 0)))
        if prices_to_create:
            ServicePrice.objects.bulk_create(prices_to_create)

        return instance
