from apps.main.ui_feedback import user_error_message
import datetime
import re
from io import BytesIO
from pathlib import Path

import khayyam
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.validators import validate_email
from PIL import Image, ImageSequence, UnidentifiedImageError

from apps.accounts.models import CustomUser, Stylist, WorkSamples
from apps.salons.models import Salon
from apps.services.models import Services
from .models import EmergencyInfo, JobDetails, StylistSchedule, StylistTimeOff

DASHBOARD_INPUT_CLASS = (
    "w-full rounded-2xl border border-loomera-borderSoft bg-white px-4 py-3 "
    "text-sm font-bold text-loomera-textPrimary outline-none transition "
    "placeholder:text-loomera-textMuted/60 focus:border-loomera-primary/40 "
    "focus:ring-4 focus:ring-loomera-primary/10"
)

DASHBOARD_TEXTAREA_CLASS = (
    "w-full min-h-28 rounded-2xl border border-loomera-borderSoft bg-white px-4 py-3 "
    "text-sm font-bold leading-7 text-loomera-textPrimary outline-none transition "
    "placeholder:text-loomera-textMuted/60 focus:border-loomera-primary/40 "
    "focus:ring-4 focus:ring-loomera-primary/10"
)

DASHBOARD_SELECT_CLASS = (
    "w-full rounded-2xl border border-loomera-borderSoft bg-white px-4 py-3 "
    "text-sm font-black text-loomera-textPrimary outline-none transition "
    "focus:border-loomera-primary/40 focus:ring-4 focus:ring-loomera-primary/10"
)

DASHBOARD_FILE_CLASS = (
    "w-full rounded-2xl border border-dashed border-loomera-borderSoft bg-loomera-bgSubtle px-4 py-4 "
    "text-sm font-bold text-loomera-textSecondary outline-none transition "
    "file:ml-3 file:rounded-full file:border-0 file:bg-loomera-primarySoft "
    "file:px-4 file:py-2 file:text-xs file:font-black file:text-loomera-primaryText "
    "hover:border-loomera-primary/30 focus:border-loomera-primary/40 focus:ring-4 focus:ring-loomera-primary/10"
)

WORK_SAMPLE_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
WORK_SAMPLE_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}
WORK_SAMPLE_ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}

WORK_SAMPLE_BLOCKED_FILENAME_PARTS = {
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


def _work_sample_image_max_size_bytes():
    return max(
        int(
            getattr(settings, "WORK_SAMPLE_IMAGE_MAX_SIZE_BYTES", 2 * 1024 * 1024) or 1
        ),
        1,
    )


def _work_sample_image_max_dimension():
    return max(
        int(getattr(settings, "WORK_SAMPLE_IMAGE_MAX_DIMENSION", 2500) or 1),
        1,
    )


def _work_sample_image_max_pixels():
    return max(
        int(getattr(settings, "WORK_SAMPLE_IMAGE_MAX_PIXELS", 4_000_000) or 1),
        1,
    )


def _work_sample_image_is_animated(image):
    if getattr(image, "is_animated", False):
        return True

    try:
        return sum(1 for _frame in ImageSequence.Iterator(image)) > 1
    except Exception:
        return False


def validate_work_sample_image_upload(uploaded_file, *, declared_content_type=None):
    if not uploaded_file:
        return uploaded_file

    if uploaded_file.size > _work_sample_image_max_size_bytes():
        raise ValidationError("حجم تصویر نباید بیشتر از حد مجاز باشد.")

    original_name = Path(uploaded_file.name or "").name.lower()
    ext = Path(original_name).suffix.lower()

    if ext not in WORK_SAMPLE_ALLOWED_EXTENSIONS:
        raise ValidationError(
            "پسوند تصویر مجاز نیست. فقط جی‌پی‌جی، پی‌اِن‌جی یا وِب‌پی قابل قبول است."
        )

    name_without_last_ext = original_name[: -len(ext)] if ext else original_name
    if any(
        blocked in name_without_last_ext
        for blocked in WORK_SAMPLE_BLOCKED_FILENAME_PARTS
    ):
        raise ValidationError("نام یا پسوند فایل مجاز نیست.")

    content_type = (
        declared_content_type
        if declared_content_type is not None
        else getattr(uploaded_file, "content_type", "")
    )
    content_type = str(content_type or "").split(";")[0].strip().lower()

    if content_type not in WORK_SAMPLE_ALLOWED_CONTENT_TYPES:
        raise ValidationError(
            "فرمت فایل مجاز نیست. فقط جی‌پی‌جی، پی‌اِن‌جی یا وِب‌پی قابل قبول است."
        )

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)

        if image.format not in WORK_SAMPLE_ALLOWED_IMAGE_FORMATS:
            raise ValidationError("فرمت واقعی تصویر مجاز نیست.")

        if _work_sample_image_is_animated(image):
            raise ValidationError("تصویر متحرک برای نمونه‌کار مجاز نیست.")

        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValidationError("ابعاد تصویر معتبر نیست.")

        max_dimension = _work_sample_image_max_dimension()
        if width > max_dimension or height > max_dimension:
            raise ValidationError("ابعاد تصویر بیش از حد مجاز است.")

        if width * height > _work_sample_image_max_pixels():
            raise ValidationError("تعداد پیکسل‌های تصویر بیش از حد مجاز است.")

        uploaded_file.seek(0)
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError("فایل ارسال‌شده تصویر معتبر نیست.")

    return uploaded_file


def apply_dashboard_form_styles(form):
    for field_name, field in form.fields.items():
        widget = field.widget

        if isinstance(widget, forms.HiddenInput):
            continue

        if isinstance(widget, forms.Textarea):
            widget.attrs["class"] = DASHBOARD_TEXTAREA_CLASS
        elif isinstance(widget, forms.Select):
            widget.attrs["class"] = DASHBOARD_SELECT_CLASS
        elif isinstance(widget, forms.ClearableFileInput) or isinstance(
            widget, forms.FileInput
        ):
            widget.attrs["class"] = DASHBOARD_FILE_CLASS
        else:
            widget.attrs["class"] = DASHBOARD_INPUT_CLASS

        widget.attrs.setdefault("autocomplete", "off")

    return form


class StylistScheduleForm(forms.ModelForm):
    class Meta:
        model = StylistSchedule
        fields = ["salon", "date", "service", "start_time", "end_time"]
        widgets = {
            "salon": forms.Select(attrs={"class": "form-control"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "service": forms.Select(attrs={"class": "form-control"}),
            "start_time": forms.TimeInput(
                attrs={"class": "form-control", "type": "time"}
            ),
            "end_time": forms.TimeInput(
                attrs={"class": "form-control", "type": "time"}
            ),
        }

    def __init__(self, *args, **kwargs):
        stylist = kwargs.pop("stylist", None)
        super().__init__(*args, **kwargs)

        if stylist:
            self.fields["salon"].queryset = Salon.objects.filter(stylists=stylist)
            self.fields["service"].queryset = Services.objects.filter(stylists=stylist)

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")

        if start_time and end_time and start_time >= end_time:
            raise ValidationError("زمان پایان باید بعد از زمان شروع باشد.")

        return cleaned_data

    def save(self, commit=True, stylist=None):
        schedule_instance = super().save(commit=False)

        if stylist:
            schedule_instance.stylist = stylist

        if StylistSchedule.objects.filter(
            stylist=schedule_instance.stylist,
            date=schedule_instance.date,
            start_time=schedule_instance.start_time,
            service=schedule_instance.service,
        ).exists():
            raise ValidationError("برنامه مشابهی از قبل وجود دارد.")

        if commit:
            schedule_instance.save()

        return schedule_instance


class StylistTimeOffForm(forms.ModelForm):
    TIME_OFF_TYPES = [
        ("", "انتخاب نوع"),
        ("مرخصی سالانه", "مرخصی سالانه"),
        ("مرخصی استعلاجی", "مرخصی استعلاجی"),
        ("مرخصی بدون حقوق", "مرخصی بدون حقوق"),
        ("سایر موارد", "سایر موارد"),
    ]

    reason_choice = forms.ChoiceField(
        choices=TIME_OFF_TYPES,
        required=True,
        label="نوع مرخصی",
    )
    start_time = forms.ChoiceField(choices=[], required=False, label="ساعت شروع")
    end_time = forms.ChoiceField(choices=[], required=False, label="ساعت پایان")

    class Meta:
        model = StylistTimeOff
        fields = ["stylist", "date"]
        widgets = {
            "stylist": forms.HiddenInput(),
            "date": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        time_options = kwargs.pop("time_options", [])
        super().__init__(*args, **kwargs)

        choices = [("", "--")] + [(opt, opt) for opt in time_options]
        self.fields["start_time"].choices = choices
        self.fields["end_time"].choices = choices

    def clean_start_time(self):
        time_str = self.cleaned_data.get("start_time")
        if time_str:
            return datetime.datetime.strptime(time_str, "%H:%M").time()
        return None

    def clean_end_time(self):
        time_str = self.cleaned_data.get("end_time")
        if time_str:
            return datetime.datetime.strptime(time_str, "%H:%M").time()
        return None

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")

        if (start_time and not end_time) or (end_time and not start_time):
            raise ValidationError(
                "برای مرخصی ساعتی باید ساعت شروع و پایان را با هم وارد کنی."
            )

        if start_time and end_time and end_time <= start_time:
            raise ValidationError("ساعت پایان باید بعد از ساعت شروع باشد.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.reason = (self.cleaned_data.get("reason_choice") or "").strip()
        instance.start_time = self.cleaned_data.get("start_time")
        instance.end_time = self.cleaned_data.get("end_time")

        if commit:
            instance.save()
        return instance


class WorkSamplesForm(forms.ModelForm):
    class Meta:
        model = WorkSamples
        fields = ["service", "sample_image", "description"]
        widgets = {
            "service": forms.Select(attrs={"class": "form-control"}),
            "sample_image": forms.FileInput(
                attrs={
                    "class": "form-control",
                    "accept": "image/jpeg,image/png,image/webp",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "توضیح کوتاهی درباره نمونه‌کار بنویسید",
                }
            ),
        }
        labels = {
            "service": "خدمت مرتبط",
            "sample_image": "تصویر نمونه‌کار",
            "description": "توضیح نمونه‌کار",
        }

    def __init__(self, *args, **kwargs):
        self.stylist = kwargs.pop("stylist", None)
        self.user = kwargs.pop("user", None)
        self.salon = kwargs.pop("salon", None)

        files = kwargs.get("files")
        if files is None and len(args) > 1:
            files = args[1]

        raw_sample_image = files.get("sample_image") if files else None
        self._raw_sample_image_content_type = (
            getattr(raw_sample_image, "content_type", "") or ""
        )

        super().__init__(*args, **kwargs)

        if self.stylist is not None:
            self.fields["service"].queryset = Services.objects.filter(
                stylists=self.stylist,
                is_active=True,
            ).distinct()

        self.fields["sample_image"].widget.attrs.update(
            {"accept": "image/jpeg,image/png,image/webp"}
        )

    def clean(self):
        cleaned_data = super().clean()
        sample_image = cleaned_data.get("sample_image")

        if sample_image is None and not self.instance.pk:
            raise ValidationError("لطفاً یک تصویر برای نمونه‌کار انتخاب کنید.")

        if sample_image:
            cleaned_data["sample_image"] = validate_work_sample_image_upload(
                sample_image,
                declared_content_type=self._raw_sample_image_content_type or None,
            )

        return cleaned_data

    def save(self, commit=True, stylist=None, salon=None):
        sample_instance = super().save(commit=False)

        target_stylist = stylist or self.stylist
        target_salon = salon or self.salon
        if target_stylist:
            sample_instance.stylist = target_stylist
        if target_salon:
            sample_instance.salon = target_salon

        sample_instance.is_active = True
        sample_instance.is_public = True
        sample_instance.review_status = "published"

        uploaded = self.cleaned_data.get("sample_image")
        if uploaded:
            uploaded.seek(0)
            img = Image.open(uploaded)
            output = BytesIO()
            img = img.convert("RGB")
            img.save(output, format="JPEG", quality=85)
            output.seek(0)

            original_name = Path(uploaded.name or "work-sample.jpg")
            safe_stem = original_name.stem or "work-sample"
            normalized_name = f"{safe_stem}.jpg"

            sample_instance.sample_image = InMemoryUploadedFile(
                output,
                "sample_image",
                normalized_name,
                "image/jpeg",
                output.getbuffer().nbytes,
                None,
            )

        if commit:
            sample_instance.save()

        return sample_instance


class StylistUserForm(forms.ModelForm):
    def __init__(self, *args, allow_existing_mobile=False, allow_mobile_edit=True, **kwargs):
        self.allow_existing_mobile = allow_existing_mobile
        self.allow_mobile_edit = allow_mobile_edit
        super().__init__(*args, **kwargs)

        if not allow_mobile_edit:
            self.fields.pop("mobile_number", None)

        apply_dashboard_form_styles(self)

        self.fields["name"].widget.attrs.update(
            {
                "placeholder": "نام",
                "autocomplete": "given-name",
            }
        )
        self.fields["family"].widget.attrs.update(
            {
                "placeholder": "نام خانوادگی",
                "autocomplete": "family-name",
            }
        )
        self.fields["email"].widget.attrs.update(
            {
                "placeholder": "example@email.com",
                "autocomplete": "email",
                "dir": "ltr",
            }
        )
        if "mobile_number" in self.fields:
            self.fields["mobile_number"].widget.attrs.update(
                {
                    "placeholder": "09xxxxxxxxx",
                    "dir": "ltr",
                    "inputmode": "numeric",
                    "autocomplete": "tel",
                }
            )

    class Meta:
        model = CustomUser
        fields = ["name", "family", "email", "mobile_number"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "نام"}
            ),
            "family": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "نام خانوادگی"}
            ),
            "email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "ایمیل"}
            ),
            "mobile_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "شماره موبایل",
                    "dir": "ltr",
                    "inputmode": "numeric",
                }
            ),
        }

    def _normalize_digits(self, value):
        return (value or "").translate(
            str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        )

    def clean_name(self):
        value = (self.cleaned_data.get("name") or "").strip()
        if not value:
            raise ValidationError("نام را وارد کنید.")
        return value

    def clean_family(self):
        value = (self.cleaned_data.get("family") or "").strip()
        if not value:
            raise ValidationError("نام خانوادگی را وارد کنید.")
        return value

    def clean_email(self):
        value = (self.cleaned_data.get("email") or "").strip().lower()
        if not value:
            return ""

        try:
            validate_email(value)
        except ValidationError:
            raise ValidationError("ایمیل واردشده معتبر نیست.")

        return value

    def clean_mobile_number(self):
        value = self._normalize_digits(self.cleaned_data.get("mobile_number"))
        digits = "".join(ch for ch in value if ch.isdigit())

        if len(digits) != 11:
            raise ValidationError("شماره موبایل باید ۱۱ رقم باشد.")

        qs = CustomUser.objects.filter(mobile_number=digits)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists() and not self.allow_existing_mobile:
            raise ValidationError("این شماره موبایل قبلاً ثبت شده است.")

        return digits

    def validate_unique(self):
        """Allow attaching an existing user when the team form explicitly permits it.

        clean_mobile_number() already validates the mobile format and rejects
        duplicates for normal edit flows. Django's ModelForm unique validation runs
        after field cleaning and would still reject CustomUser.mobile_number even
        when allow_existing_mobile=True. For the salon team invite/attach flow we
        exclude only mobile_number from the model-level unique check so the view
        can resolve the existing user and create a SalonMembership instead of a
        duplicate account.
        """
        if not self.allow_existing_mobile:
            return super().validate_unique()

        exclude = self._get_validation_exclusions()
        exclude.add("mobile_number")
        try:
            self.instance.validate_unique(exclude=exclude)
        except ValidationError as error:
            self._update_errors(error)


STYLIST_PROFILE_IMAGE_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
STYLIST_PROFILE_IMAGE_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}
STYLIST_PROFILE_IMAGE_ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

STYLIST_PROFILE_IMAGE_BLOCKED_FILENAME_PARTS = {
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


def _stylist_profile_image_max_size_bytes():
    return max(
        int(
            getattr(
                settings,
                "STYLIST_PROFILE_IMAGE_MAX_SIZE_BYTES",
                2 * 1024 * 1024,
            )
            or 1
        ),
        1,
    )


def _stylist_profile_image_max_dimension():
    return max(
        int(getattr(settings, "STYLIST_PROFILE_IMAGE_MAX_DIMENSION", 5000) or 1),
        1,
    )


def _stylist_profile_image_max_pixels():
    return max(
        int(getattr(settings, "STYLIST_PROFILE_IMAGE_MAX_PIXELS", 10_000_000) or 1),
        1,
    )


def _stylist_profile_image_is_animated(image):
    if getattr(image, "is_animated", False):
        return True

    try:
        return sum(1 for _frame in ImageSequence.Iterator(image)) > 1
    except Exception:
        return False


def validate_stylist_profile_image_upload(uploaded_file, *, declared_content_type=None):
    if not uploaded_file:
        return uploaded_file

    if uploaded_file.size > _stylist_profile_image_max_size_bytes():
        raise ValidationError("حجم تصویر پروفایل متخصص بیش از حد مجاز است.")

    original_name = Path(uploaded_file.name or "").name.lower()
    ext = Path(original_name).suffix.lower()

    if ext not in STYLIST_PROFILE_IMAGE_ALLOWED_EXTENSIONS:
        raise ValidationError(
            "پسوند تصویر مجاز نیست. فقط جی‌پی‌جی، پی‌اِن‌جی یا وِب‌پی قابل قبول است."
        )

    name_without_last_ext = original_name[: -len(ext)] if ext else original_name
    if any(
        blocked in name_without_last_ext
        for blocked in STYLIST_PROFILE_IMAGE_BLOCKED_FILENAME_PARTS
    ):
        raise ValidationError("نام یا پسوند فایل مجاز نیست.")

    content_type = (
        declared_content_type
        if declared_content_type is not None
        else getattr(uploaded_file, "content_type", "")
    )
    content_type = str(content_type or "").split(";")[0].strip().lower()

    if content_type not in STYLIST_PROFILE_IMAGE_ALLOWED_CONTENT_TYPES:
        raise ValidationError(
            "فرمت فایل مجاز نیست. فقط جی‌پی‌جی، پی‌اِن‌جی یا وِب‌پی قابل قبول است."
        )

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)

        if image.format not in STYLIST_PROFILE_IMAGE_ALLOWED_FORMATS:
            raise ValidationError("فرمت واقعی تصویر مجاز نیست.")

        if _stylist_profile_image_is_animated(image):
            raise ValidationError("تصویر متحرک برای پروفایل متخصص مجاز نیست.")

        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValidationError("ابعاد تصویر معتبر نیست.")

        max_dimension = _stylist_profile_image_max_dimension()
        if width > max_dimension or height > max_dimension:
            raise ValidationError("ابعاد تصویر بیش از حد مجاز است.")

        if width * height > _stylist_profile_image_max_pixels():
            raise ValidationError("تعداد پیکسل‌های تصویر بیش از حد مجاز است.")

        uploaded_file.seek(0)
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError("فایل ارسال‌شده تصویر معتبر نیست.")

    return uploaded_file


class StylistProfileForm(forms.ModelForm):
    class Meta:
        model = Stylist
        fields = [
            "display_name",
            "resume_headline",
            "resume_summary",
            "expert",
            "description",
            "started_working_year",
            "public_visibility",
            "address",
            "linkedin_link",
            "insta_link",
            "telegram_link",
            "calendar_color",
            "profile_image",
        ]
        widgets = {
            "display_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "نام نمایشی حرفه‌ای"}
            ),
            "resume_headline": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "مثلاً متخصص رنگ، لایت و کراتین",
                }
            ),
            "resume_summary": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "خلاصه‌ای حرفه‌ای برای رزومه عمومی خود بنویسید...",
                }
            ),
            "expert": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "تخصص"}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "توضیح کوتاهی درباره تخصص و سبک کاری خودت بنویس...",
                }
            ),
            "started_working_year": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "مثلاً ۱۳۹۸"}
            ),
            "public_visibility": forms.Select(attrs={"class": "form-control"}),
            "address": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "آدرس یا توضیح محل حضور",
                }
            ),
            "linkedin_link": forms.URLInput(
                attrs={"class": "form-control", "placeholder": "لینک لینکدین"}
            ),
            "insta_link": forms.URLInput(
                attrs={"class": "form-control", "placeholder": "لینک اینستاگرام"}
            ),
            "telegram_link": forms.URLInput(
                attrs={"class": "form-control", "placeholder": "لینک تلگرام"}
            ),
            "calendar_color": forms.HiddenInput(),
            "profile_image": forms.ClearableFileInput(
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

        raw_profile_image = files.get("profile_image") if files else None
        self._raw_profile_image_content_type = (
            getattr(raw_profile_image, "content_type", "") or ""
        )

        super().__init__(*args, **kwargs)

        for field_name in [
            "display_name",
            "resume_headline",
            "resume_summary",
            "expert",
            "description",
            "started_working_year",
            "public_visibility",
            "address",
            "linkedin_link",
            "insta_link",
            "telegram_link",
            "profile_image",
        ]:
            self.fields[field_name].required = False

        apply_dashboard_form_styles(self)

        self.fields["display_name"].widget.attrs.update(
            {"placeholder": "مثلاً نگین محمدی"}
        )
        self.fields["resume_headline"].widget.attrs.update(
            {"placeholder": "مثلاً متخصص رنگ، لایت و احیای مو"}
        )
        self.fields["resume_summary"].widget.attrs.update(
            {
                "placeholder": "خلاصه‌ای حرفه‌ای برای نمایش در پروفایل عمومی بنویس...",
                "rows": 4,
            }
        )
        self.fields["expert"].widget.attrs.update(
            {"placeholder": "مثلاً ناخن، پوست، ماساژ، رنگ مو"}
        )
        self.fields["description"].widget.attrs.update(
            {
                "placeholder": "درباره سبک کاری، تجربه و مهارت‌های خودت بنویس...",
                "rows": 4,
            }
        )
        self.fields["started_working_year"].widget.attrs.update(
            {
                "placeholder": "مثلاً ۱۳۹۸",
                "inputmode": "numeric",
            }
        )
        self.fields["address"].widget.attrs.update(
            {
                "placeholder": "آدرس یا توضیح محل حضور، در صورت نیاز",
                "rows": 3,
            }
        )
        self.fields["linkedin_link"].widget.attrs.update(
            {
                "placeholder": "https://linkedin.com/in/...",
                "dir": "ltr",
            }
        )
        self.fields["insta_link"].widget.attrs.update(
            {
                "placeholder": "https://instagram.com/...",
                "dir": "ltr",
            }
        )
        self.fields["telegram_link"].widget.attrs.update(
            {
                "placeholder": "https://t.me/...",
                "dir": "ltr",
            }
        )
        self.fields["profile_image"].widget.attrs.update(
            {
                "accept": "image/jpeg,image/png,image/webp",
            }
        )

    def clean_profile_image(self):
        profile_image = self.cleaned_data.get("profile_image")
        return validate_stylist_profile_image_upload(
            profile_image,
            declared_content_type=self._raw_profile_image_content_type or None,
        )


class JobDetailsForm(forms.ModelForm):
    start_date = forms.CharField(
        required=False,
        label="تاریخ شروع",
        widget=forms.TextInput(
            attrs={
                "class": "form-control datepicker",
                "placeholder": "مثلاً ۱۴۰۵/۰۱/۱۷",
                "autocomplete": "off",
            }
        ),
    )
    end_date = forms.CharField(
        required=False,
        label="تاریخ پایان",
        widget=forms.TextInput(
            attrs={
                "class": "form-control datepicker",
                "placeholder": "اختیاری",
                "autocomplete": "off",
            }
        ),
    )

    class Meta:
        model = JobDetails
        fields = ["start_date", "end_date", "employment_type"]
        widgets = {
            "employment_type": forms.Select(
                attrs={"class": "form-control"},
                choices=[
                    ("", "یک گزینه را انتخاب کنید"),
                    ("full_time", "تمام وقت"),
                    ("part_time", "پاره وقت"),
                    ("contract", "قراردادی"),
                    ("project", "پروژه‌ای"),
                ],
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employment_type"].required = False

        if self.instance and self.instance.pk:
            self.fields["start_date"].initial = self._format_date_for_input(
                self.instance.start_date
            )
            self.fields["end_date"].initial = self._format_date_for_input(
                self.instance.end_date
            )

    def _format_date_for_input(self, value):
        if not value:
            return ""

        if isinstance(value, datetime.datetime):
            value = value.date()

        if isinstance(value, datetime.date):
            jalali_date = khayyam.JalaliDate(value)
            return (
                f"{jalali_date.year:04d}/{jalali_date.month:02d}/{jalali_date.day:02d}"
            )

        return str(value)

    def persian_to_english_numbers(self, text):
        if not text:
            return text

        persian_digits = "۰۱۲۳۴۵۶۷۸۹"
        english_digits = "0123456789"
        arabic_digits = "٠١٢٣٤٥٦٧٨٩"

        for persian, english in zip(persian_digits, english_digits):
            text = text.replace(persian, english)

        for arabic, english in zip(arabic_digits, english_digits):
            text = text.replace(arabic, english)

        return text

    def parse_jalali_date(self, date_str):
        if not date_str:
            return None

        if isinstance(date_str, datetime.datetime):
            return date_str.date()

        if isinstance(date_str, datetime.date):
            return date_str

        try:
            clean_date = self.persian_to_english_numbers(str(date_str).strip())

            patterns = [
                r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})",
                r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})",
            ]

            year, month, day = None, None, None

            for pattern in patterns:
                match = re.match(pattern, clean_date)
                if match:
                    if len(match.group(1)) == 4:
                        year, month, day = (
                            int(match.group(1)),
                            int(match.group(2)),
                            int(match.group(3)),
                        )
                    else:
                        day, month, year = (
                            int(match.group(1)),
                            int(match.group(2)),
                            int(match.group(3)),
                        )
                    break

            if not all([year, month, day]):
                raise ValueError("فرمت تاریخ نامعتبر است.")

            # اگر به هر دلیل مقدار میلادی مثل 2026-05-23 وارد شد، فرم خطا ندهد.
            # نمایش همچنان در UI شمسی خواهد بود.
            if 1900 <= year <= 2200:
                return datetime.date(year, month, day)

            if year < 1300 or year > 1500:
                raise ValueError("سال واردشده معتبر نیست.")
            if month < 1 or month > 12:
                raise ValueError("ماه واردشده معتبر نیست.")
            if day < 1 or day > 31:
                raise ValueError("روز واردشده معتبر نیست.")

            jalali_date = khayyam.JalaliDate(year, month, day)
            return jalali_date.todate()

        except ValueError as exc:
            raise ValidationError(user_error_message(exc, "تاریخ واردشده معتبر نیست."))
        except Exception:
            raise ValidationError("تاریخ واردشده معتبر نیست.")

    def clean_start_date(self):
        value = self.cleaned_data.get("start_date")

        if isinstance(value, datetime.datetime):
            return value.date()

        if isinstance(value, datetime.date):
            return value

        value = (value or "").strip()
        if not value:
            return (
                self.instance.start_date if self.instance and self.instance.pk else None
            )

        return self.parse_jalali_date(value)

    def clean_end_date(self):
        value = (self.cleaned_data.get("end_date") or "").strip()
        if not value:
            return None
        return self.parse_jalali_date(value)

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and start_date > end_date:
            raise ValidationError(
                "تاریخ پایان کار نمی‌تواند قبل از تاریخ شروع کار باشد."
            )

        return cleaned_data


class EmergencyInfoForm(forms.ModelForm):
    emergency_contact_name = forms.CharField(
        label="نام",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    emergency_contact_family = forms.CharField(
        label="نام خانوادگی",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    emergency_phone = forms.CharField(
        label="شماره تلفن",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
    )

    class Meta:
        model = EmergencyInfo
        fields = ["relationship"]
        widgets = {
            "relationship": forms.Select(
                attrs={"class": "form-control"},
                choices=[
                    ("", "انتخاب کنید"),
                    ("spouse", "همسر"),
                    ("parents", "والدین"),
                    ("child", "فرزند"),
                    ("friend", "دوست"),
                    ("other", "سایر"),
                ],
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["relationship"].required = False

        apply_dashboard_form_styles(self)

        self.fields["emergency_contact_name"].widget.attrs.update(
            {"placeholder": "نام تماس اضطراری"}
        )
        self.fields["emergency_contact_family"].widget.attrs.update(
            {"placeholder": "نام خانوادگی تماس اضطراری"}
        )
        self.fields["emergency_phone"].widget.attrs.update(
            {
                "placeholder": "09xxxxxxxxx",
                "dir": "ltr",
                "inputmode": "numeric",
                "autocomplete": "tel",
            }
        )

        if self.instance and self.instance.pk:
            full_name = (self.instance.full_name or "").strip()
            name_parts = full_name.split(" ", 1)

            self.fields["emergency_contact_name"].initial = (
                name_parts[0] if name_parts else ""
            )
            self.fields["emergency_contact_family"].initial = (
                name_parts[1] if len(name_parts) > 1 else ""
            )
            self.fields["emergency_phone"].initial = (
                self.instance.emergency_contact or ""
            )

    def clean_emergency_phone(self):
        value = (self.cleaned_data.get("emergency_phone") or "").strip()
        value = value.translate(
            str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        )
        digits = "".join(ch for ch in value if ch.isdigit())
        return digits

    def clean(self):
        cleaned_data = super().clean()

        emergency_name = (cleaned_data.get("emergency_contact_name") or "").strip()
        emergency_family = (cleaned_data.get("emergency_contact_family") or "").strip()
        emergency_phone = (cleaned_data.get("emergency_phone") or "").strip()
        relationship = (cleaned_data.get("relationship") or "").strip()

        # Beta UX: emergency contact is optional. If the manager starts filling
        # this section, keep the complete-data validation below.
        if not any([emergency_name, emergency_family, emergency_phone, relationship]):
            return cleaned_data

        if not emergency_name:
            self.add_error("emergency_contact_name", "نام تماس اضطراری را وارد کن.")

        if not emergency_family:
            self.add_error(
                "emergency_contact_family", "نام خانوادگی تماس اضطراری را وارد کن."
            )

        if not relationship:
            self.add_error("relationship", "نسبت تماس اضطراری را انتخاب کن.")

        if not emergency_phone:
            self.add_error("emergency_phone", "شماره تماس اضطراری را وارد کن.")
        elif len(emergency_phone) not in (10, 11):
            self.add_error(
                "emergency_phone",
                "شماره تماس اضطراری باید ۱۰ یا ۱۱ رقم باشد.",
            )

        return cleaned_data
