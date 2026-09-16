import os
import re
from datetime import time as dt_time

from django import forms
from django.conf import settings
from PIL import Image, ImageSequence, UnidentifiedImageError

from apps.salons.models import Salon, SalonsGallery, SupplementaryInfoView

_PERSIAN_ARABIC_DIGITS_TRANS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)

SALON_GALLERY_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SALON_GALLERY_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}
SALON_GALLERY_ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}

SALON_GALLERY_BLOCKED_FILENAME_PARTS = {
    ".php",
    ".phtml",
    ".php3",
    ".php4",
    ".php5",
    ".asp",
    ".aspx",
    ".jsp",
    ".cgi",
    ".pl",
    ".py",
    ".rb",
    ".htm",
    ".html",
    ".js",
    ".svg",
    ".xml",
    ".exe",
    ".sh",
    ".bat",
    ".cmd",
    ".gif",
}


def _salon_gallery_image_max_size_bytes():
    return max(
        int(
            getattr(settings, "SALON_GALLERY_IMAGE_MAX_SIZE_BYTES", 4 * 1024 * 1024)
            or 1
        ),
        1,
    )


def _salon_gallery_image_max_dimension():
    return max(
        int(getattr(settings, "SALON_GALLERY_IMAGE_MAX_DIMENSION", 7000) or 1),
        1,
    )


def _salon_gallery_image_max_pixels():
    return max(
        int(getattr(settings, "SALON_GALLERY_IMAGE_MAX_PIXELS", 20_000_000) or 1),
        1,
    )


def _salon_gallery_image_is_animated(image):
    if getattr(image, "is_animated", False):
        return True

    try:
        return sum(1 for _frame in ImageSequence.Iterator(image)) > 1
    except Exception:
        return False


def validate_salon_gallery_image_upload(uploaded_file, *, declared_content_type=None):
    if not uploaded_file:
        return uploaded_file

    if uploaded_file.size > _salon_gallery_image_max_size_bytes():
        raise forms.ValidationError("حجم تصویر گالری بیش از حد مجاز است.")

    original_name = os.path.basename(uploaded_file.name or "").lower()
    _, ext = os.path.splitext(original_name)

    if ext not in SALON_GALLERY_ALLOWED_EXTENSIONS:
        raise forms.ValidationError(
            "پسوند تصویر مجاز نیست. فقط جی‌پی‌جی، پی‌اِن‌جی یا وِب‌پی قابل قبول است."
        )

    name_without_last_ext = original_name[: -len(ext)] if ext else original_name
    if any(
        blocked in name_without_last_ext
        for blocked in SALON_GALLERY_BLOCKED_FILENAME_PARTS
    ):
        raise forms.ValidationError("نام یا پسوند فایل مجاز نیست.")

    content_type = (
        declared_content_type
        if declared_content_type is not None
        else getattr(uploaded_file, "content_type", "")
    )
    content_type = str(content_type or "").split(";")[0].strip().lower()

    if content_type not in SALON_GALLERY_ALLOWED_CONTENT_TYPES:
        raise forms.ValidationError(
            "فرمت فایل مجاز نیست. فقط جی‌پی‌جی، پی‌اِن‌جی یا وِب‌پی قابل قبول است."
        )

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)

        if image.format not in SALON_GALLERY_ALLOWED_IMAGE_FORMATS:
            raise forms.ValidationError("فرمت واقعی تصویر مجاز نیست.")

        if _salon_gallery_image_is_animated(image):
            raise forms.ValidationError("تصویر متحرک برای گالری مجموعه مجاز نیست.")

        width, height = image.size
        if width <= 0 or height <= 0:
            raise forms.ValidationError("ابعاد تصویر معتبر نیست.")

        max_dimension = _salon_gallery_image_max_dimension()
        if width > max_dimension or height > max_dimension:
            raise forms.ValidationError("ابعاد تصویر بیش از حد مجاز است.")

        if width * height > _salon_gallery_image_max_pixels():
            raise forms.ValidationError("تعداد پیکسل‌های تصویر بیش از حد مجاز است.")

        uploaded_file.seek(0)
    except forms.ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise forms.ValidationError("فایل ارسال‌شده تصویر معتبر نیست.")

    return uploaded_file


def normalize_digits(value):
    return (value or "").translate(_PERSIAN_ARABIC_DIGITS_TRANS)


def normalize_iban(value):
    value = normalize_digits(value)
    value = re.sub(r"[\s\-\u200c_]+", "", value or "")
    return value.upper()


def is_valid_iban_checksum(value):
    """
    اعتبارسنجی checksum استاندارد IBAN.
    برای شبا ایران مقدار معتبر باید IR + 24 رقم و mod97 برابر 1 باشد.
    """
    if not value or len(value) < 4:
        return False

    rearranged = value[4:] + value[:4]
    numeric = ""

    for char in rearranged:
        if char.isdigit():
            numeric += char
        elif "A" <= char <= "Z":
            numeric += str(ord(char) - 55)
        else:
            return False

    remainder = 0
    for char in numeric:
        remainder = (remainder * 10 + int(char)) % 97

    return remainder == 1


# -----------------------------------------------------------------
class SalonProfileStep1Form(forms.ModelForm):
    class Meta:
        model = Salon
        fields = ["salon_name", "mobile_phone", "landline_phone"]
        widgets = {
            "salon_name": forms.TextInput(attrs={"class": "form-control", "autocomplete": "organization"}),
            "mobile_phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "inputmode": "numeric",
                    "autocomplete": "tel",
                    "placeholder": "مثال: 09123456789",
                }
            ),
            "landline_phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "inputmode": "numeric",
                    "autocomplete": "tel",
                    "placeholder": "مثال: 02112345678",
                }
            ),
        }
        labels = {
            "salon_name": "نام مجموعه",
            "mobile_phone": "شماره همراه مجموعه",
            "landline_phone": "شماره ثابت با کد شهر",
        }

    @staticmethod
    def _normalize_iran_phone(value):
        digits = re.sub(r"\D+", "", (value or "").strip())
        if digits.startswith("0098"):
            digits = "0" + digits[4:]
        elif digits.startswith("98"):
            digits = "0" + digits[2:]
        return digits

    def clean_mobile_phone(self):
        digits = self._normalize_iran_phone(self.cleaned_data.get("mobile_phone"))
        if len(digits) == 10 and digits.startswith("9"):
            digits = "0" + digits
        if not re.fullmatch(r"09\d{9}", digits):
            raise forms.ValidationError("شماره همراه را به‌صورت معتبر وارد کنید؛ مثال 09123456789.")
        return digits

    def clean_landline_phone(self):
        digits = self._normalize_iran_phone(self.cleaned_data.get("landline_phone"))
        if not re.fullmatch(r"0(?!9)\d{10}", digits):
            raise forms.ValidationError("شماره ثابت را همراه با کد شهر وارد کنید؛ مثال 02112345678.")
        return digits

    def save(self, commit=True):
        salon = super().save(commit=False)
        # Keep the legacy public contact field populated while old consumers
        # are migrated gradually to the explicit mobile/landline fields.
        salon.phone_number = self.cleaned_data.get("mobile_phone") or self.cleaned_data.get("landline_phone")
        if commit:
            salon.save()
            self.save_m2m()
        return salon


# -----------------------------------------------------------------
class SalonProfileStep2Form(forms.ModelForm):
    latitude = forms.FloatField(required=False, widget=forms.HiddenInput())
    longitude = forms.FloatField(required=False, widget=forms.HiddenInput())
    neighborhood_name = forms.CharField(required=False, widget=forms.HiddenInput())
    zone_label = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Salon
        fields = [
            "zone",
            "neighborhood",
            "address",
            "address_plaque",
            "address_unit",
            "latitude",
            "longitude",
        ]
        widgets = {
            "zone": forms.HiddenInput(),
            "neighborhood": forms.HiddenInput(),
            "address": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "آدرس خیابان و کوچه را وارد کنید",
                }
            ),
            "address_plaque": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "پلاک", "autocomplete": "off"}
            ),
            "address_unit": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "واحد", "autocomplete": "off"}
            ),
        }
        labels = {
            "zone": "منطقه",
            "neighborhood": "محله",
            "address": "آدرس دقیق",
            "address_plaque": "پلاک",
            "address_unit": "واحد",
        }
        help_texts = {
            "address": "آدرس خیابان و کوچه را بررسی کنید؛ پلاک و واحد جداگانه ثبت می‌شوند.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["zone"].required = False
        self.fields["neighborhood"].required = False
        self.fields["address"].required = True
        self.fields["address_plaque"].required = True
        self.fields["address_unit"].required = True
        self.fields["latitude"].required = False
        self.fields["longitude"].required = False

        instance = getattr(self, "instance", None)
        if instance and getattr(instance, "pk", None):
            if getattr(instance, "neighborhood_id", None):
                self.fields["neighborhood_name"].initial = instance.neighborhood.name
            if getattr(instance, "zone", None):
                self.fields["zone_label"].initial = f"منطقه {instance.zone}"

        self.fields["address"].error_messages.update({"required": "وارد کردن آدرس دقیق الزامی است."})
        self.fields["address_plaque"].error_messages.update({"required": "وارد کردن پلاک الزامی است."})
        self.fields["address_unit"].error_messages.update({"required": "وارد کردن واحد الزامی است."})

    def clean_neighborhood_name(self):
        return (self.cleaned_data.get("neighborhood_name") or "").strip()

    def clean_zone_label(self):
        return (self.cleaned_data.get("zone_label") or "").strip()

    def clean_address_plaque(self):
        return (self.cleaned_data.get("address_plaque") or "").strip()

    def clean_address_unit(self):
        return (self.cleaned_data.get("address_unit") or "").strip()

    def clean(self):
        cleaned_data = super().clean()
        latitude = cleaned_data.get("latitude")
        longitude = cleaned_data.get("longitude")

        if latitude is None or longitude is None:
            raise forms.ValidationError("لطفاً موقعیت مجموعه را روی نقشه انتخاب کنید.")

        return cleaned_data


# -----------------------------------------------------------------
class SalonOpeningHoursForm(forms.Form):
    days = [
        (1, "شنبه"),
        (2, "یکشنبه"),
        (3, "دوشنبه"),
        (4, "سه‌شنبه"),
        (5, "چهارشنبه"),
        (6, "پنج‌شنبه"),
        (7, "جمعه"),
    ]

    @staticmethod
    def _time_widget():
        return forms.TextInput(
            attrs={
                "class": "working-hours-time-input",
                "placeholder": "10:00",
                "inputmode": "numeric",
                "autocomplete": "off",
                "dir": "ltr",
                "data-time-input": "true",
            }
        )

    day_1_active = forms.BooleanField(required=False, initial=True, label="شنبه")
    day_1_open_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        widget=_time_widget.__func__(),
        initial=dt_time(10, 0),
        label="ساعت شروع",
    )
    day_1_close_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        widget=_time_widget.__func__(),
        initial=dt_time(19, 0),
        label="ساعت پایان",
    )

    day_2_active = forms.BooleanField(required=False, initial=True, label="یکشنبه")
    day_2_open_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        widget=_time_widget.__func__(),
        initial=dt_time(10, 0),
        label="ساعت شروع",
    )
    day_2_close_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        widget=_time_widget.__func__(),
        initial=dt_time(19, 0),
        label="ساعت پایان",
    )

    day_3_active = forms.BooleanField(required=False, initial=True, label="دوشنبه")
    day_3_open_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        widget=_time_widget.__func__(),
        initial=dt_time(10, 0),
        label="ساعت شروع",
    )
    day_3_close_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        widget=_time_widget.__func__(),
        initial=dt_time(19, 0),
        label="ساعت پایان",
    )

    day_4_active = forms.BooleanField(required=False, initial=True, label="سه‌شنبه")
    day_4_open_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        widget=_time_widget.__func__(),
        initial=dt_time(10, 0),
        label="ساعت شروع",
    )
    day_4_close_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        widget=_time_widget.__func__(),
        initial=dt_time(19, 0),
        label="ساعت پایان",
    )

    day_5_active = forms.BooleanField(required=False, initial=True, label="چهارشنبه")
    day_5_open_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        widget=_time_widget.__func__(),
        initial=dt_time(10, 0),
        label="ساعت شروع",
    )
    day_5_close_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        widget=_time_widget.__func__(),
        initial=dt_time(19, 0),
        label="ساعت پایان",
    )

    day_6_active = forms.BooleanField(required=False, initial=True, label="پنج‌شنبه")
    day_6_open_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        widget=_time_widget.__func__(),
        initial=dt_time(10, 0),
        label="ساعت شروع",
    )
    day_6_close_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        widget=_time_widget.__func__(),
        initial=dt_time(19, 0),
        label="ساعت پایان",
    )

    day_7_active = forms.BooleanField(required=False, initial=False, label="جمعه")
    day_7_open_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        widget=_time_widget.__func__(),
        initial=dt_time(10, 0),
        label="ساعت شروع",
    )
    day_7_close_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        widget=_time_widget.__func__(),
        initial=dt_time(17, 0),
        label="ساعت پایان",
    )

    def clean(self):
        cleaned_data = super().clean()

        for day_num, day_name in self.days:
            is_active = cleaned_data.get(f"day_{day_num}_active")
            open_time = cleaned_data.get(f"day_{day_num}_open_time")
            close_time = cleaned_data.get(f"day_{day_num}_close_time")

            if is_active:
                if not open_time:
                    self.add_error(
                        f"day_{day_num}_open_time",
                        f"ساعت شروع {day_name} را مشخص کنید.",
                    )
                if not close_time:
                    self.add_error(
                        f"day_{day_num}_close_time",
                        f"ساعت پایان {day_name} را مشخص کنید.",
                    )
                if open_time and close_time and close_time <= open_time:
                    self.add_error(
                        f"day_{day_num}_close_time",
                        f"ساعت پایان {day_name} باید بعد از ساعت شروع باشد.",
                    )

        return cleaned_data


# -----------------------------------------------------------------
class SalonsGalleryForm(forms.ModelForm):
    class Meta:
        model = SalonsGallery
        fields = ["salon_image"]
        labels = {
            "salon_image": "تصویر مجموعه",
        }
        widgets = {
            "salon": forms.Select(attrs={"class": "form-control"}),
            "salon_image": forms.FileInput(
                attrs={
                    "class": "form-control",
                    "accept": "image/jpeg,image/png,image/webp",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        files = kwargs.get("files")
        if files is None and len(args) > 1:
            files = args[1]

        raw_salon_image = files.get("salon_image") if files else None
        self._raw_salon_image_content_type = (
            getattr(raw_salon_image, "content_type", "") or ""
        )

        super().__init__(*args, **kwargs)

    def clean_salon_image(self):
        salon_image = self.cleaned_data.get("salon_image")
        return validate_salon_gallery_image_upload(
            salon_image,
            declared_content_type=self._raw_salon_image_content_type or None,
        )

    # def __init__(self, *args, **kwargs):
    #     super(SalonsGalleryForm, self).__init__(*args, **kwargs)
    #     # اگر نیاز به سفارشی‌سازی بیشتر است، می‌توانید اینجا اضافه کنید
    #     # مثال: محدود کردن مجموعه‌ها بر اساس کاربر
    #     # self.fields['salon'].queryset = Salon.objects.filter(user=user)


# -----------------------------------------------------------------
class SupplementaryInfoForm(forms.ModelForm):
    class Meta:
        model = SupplementaryInfoView
        fields = ["title", "description", "icon_class", "is_active"]
        widgets = {
            "title": forms.HiddenInput(),
            "icon_class": forms.HiddenInput(),
        }


# --------------------------------------------------------------------
class SalonDescriptionForm(forms.ModelForm):
    description = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "description-input",
                "maxlength": "600",
                "placeholder": "توضیحات مجموعه خود را وارد کنید...",
            }
        ),
        required=True,
        max_length=600,
    )

    class Meta:
        model = Salon
        fields = ["description"]

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()


class SalonPayoutSettingsForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                "class",
                "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-loomera-primary/30 focus:ring-2 focus:ring-loomera-primary/10",
            )

    class Meta:
        model = Salon
        fields = [
            "payout_account_holder_name",
            "payout_iban",
            "payout_bank_name",
            "payout_contact_mobile",
            "cancellation_window_hours",
            "cancellation_refund_percent",
            "payout_delay_days",
            "cancellation_policy_note",
        ]
        widgets = {
            "payout_account_holder_name": forms.TextInput(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-loomera-primary focus:outline-none",
                    "placeholder": "نام صاحب حساب مطابق شبا",
                }
            ),
            "payout_iban": forms.TextInput(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm uppercase tracking-wide focus:border-loomera-primary focus:outline-none",
                    "placeholder": "IRxxxxxxxxxxxxxxxxxxxxxxxx",
                    "dir": "ltr",
                }
            ),
            "payout_bank_name": forms.TextInput(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-loomera-primary focus:outline-none",
                    "placeholder": "مثلاً ملت، ملی، سامان",
                }
            ),
            "payout_contact_mobile": forms.TextInput(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-loomera-primary focus:outline-none",
                    "placeholder": "09xxxxxxxxx",
                    "dir": "ltr",
                }
            ),
            "cancellation_window_hours": forms.NumberInput(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-loomera-primary focus:outline-none",
                    "min": 1,
                    "max": 168,
                    "placeholder": "مثلاً 24",
                }
            ),
            "cancellation_refund_percent": forms.NumberInput(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-loomera-primary focus:outline-none",
                    "min": 0,
                    "max": 100,
                    "placeholder": "مثلاً 100",
                }
            ),
            "payout_delay_days": forms.NumberInput(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-loomera-primary focus:outline-none",
                    "min": 0,
                    "max": 30,
                    "placeholder": "مثلاً 2",
                }
            ),
            "cancellation_policy_note": forms.Textarea(
                attrs={
                    "class": "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-7 focus:border-loomera-primary focus:outline-none",
                    "rows": 5,
                    "placeholder": "قوانین تکمیلی لغو، تاخیر، عدم حضور، شرایط بازگشت وجه و مواردی که مشتری باید بداند را اینجا بنویسید.",
                }
            ),
        }
        labels = {
            "payout_account_holder_name": "نام صاحب حساب",
            "payout_iban": "شماره شبا",
            "payout_bank_name": "نام بانک",
            "payout_contact_mobile": "شماره موبایل مسئول امور مالی",
            "cancellation_window_hours": "مهلت لغو آنلاین (ساعت)",
            "cancellation_refund_percent": "درصد بازگشت وجه به کیف پول",
            "payout_delay_days": "تاخیر آزاد شدن موجودی قابل برداشت (روز)",
            "cancellation_policy_note": "توضیحات سیاست لغو",
        }
        help_texts = {
            "payout_account_holder_name": "نامی را وارد کن که دقیقاً با صاحب شبا هم‌خوان باشد تا خطای تسویه کمتر شود.",
            "payout_iban": "شبا باید با IR شروع شود و مقصد اصلی برداشت‌های مجموعه باشد.",
            "payout_bank_name": "برای پیگیری سریع‌تر و کاهش خطای تیم مالی مفید است.",
            "payout_contact_mobile": "شماره‌ای که پاسخ‌گوی هماهنگی‌های امور مالی مجموعه باشد.",
            "cancellation_window_hours": "بعد از این بازه، لغو آنلاین برای مشتری بسته می‌شود.",
            "cancellation_refund_percent": "این درصد فقط برای رزروهای دیجیتال اعمال می‌شود و به کیف پول مشتری برمی‌گردد.",
            "payout_delay_days": "بعد از این تعداد روز، سهم مجموعه از موجودی در انتظار به موجودی قابل برداشت منتقل می‌شود.",
            "cancellation_policy_note": "هم برای تیم خودت و هم برای جلوگیری از اختلافات آینده، سیاست لغو را شفاف بنویس.",
        }

    def clean_payout_iban(self):
        value = normalize_iban(self.cleaned_data.get("payout_iban"))

        if not value:
            return ""

        if not value.startswith("IR"):
            raise forms.ValidationError("شماره شبا باید با «آی‌آر» شروع شود.")

        if len(value) != 26 or not value[2:].isdigit():
            raise forms.ValidationError(
                "شماره شبا باید با «آی‌آر» شروع شود و بعد از آن دقیقاً ۲۴ رقم داشته باشد."
            )

        if not is_valid_iban_checksum(value):
            raise forms.ValidationError(
                "شماره شبا معتبر نیست. لطفاً شبا را بدون فاصله و مطابق اطلاعات بانکی وارد کنید."
            )

        return value

    def clean_payout_contact_mobile(self):
        value = "".join(
            ch
            for ch in normalize_digits(self.cleaned_data.get("payout_contact_mobile"))
            if ch.isdigit()
        )

        if value.startswith("98") and len(value) == 12:
            value = "0" + value[2:]

        if not value:
            return ""

        if len(value) != 11 or not value.startswith("09"):
            raise forms.ValidationError(
                "شماره موبایل تسویه باید با 09 شروع شود و ۱۱ رقم باشد."
            )

        return value

    def clean_cancellation_window_hours(self):
        value = int(self.cleaned_data.get("cancellation_window_hours") or 0)
        if value < 1 or value > 168:
            raise forms.ValidationError("مهلت لغو باید بین ۱ تا ۱۶۸ ساعت باشد.")
        return value

    def clean_cancellation_refund_percent(self):
        value = int(self.cleaned_data.get("cancellation_refund_percent") or 0)
        if value < 0 or value > 100:
            raise forms.ValidationError("درصد بازگشت وجه باید بین ۰ تا ۱۰۰ باشد.")
        return value

    def clean_payout_delay_days(self):
        value = int(self.cleaned_data.get("payout_delay_days") or 0)
        if value < 0 or value > 30:
            raise forms.ValidationError("تاخیر تسویه باید بین ۰ تا ۳۰ روز باشد.")
        return value
