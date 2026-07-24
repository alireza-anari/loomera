from django import forms
from django.core.exceptions import ValidationError
from apps.dashboards.jalali_utils import to_english_digits
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageSequence, UnidentifiedImageError

SUPPORT_ATTACHMENT_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
SUPPORT_ATTACHMENT_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "application/pdf",
}
SUPPORT_ATTACHMENT_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png"}
SUPPORT_ATTACHMENT_IMAGE_FORMATS = {"JPEG", "PNG"}

SUPPORT_ATTACHMENT_BLOCKED_FILENAME_PARTS = {
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
    ".webp",
}


def _support_attachment_max_size_bytes():
    return max(
        int(
            getattr(settings, "SUPPORT_ATTACHMENT_MAX_SIZE_BYTES", 5 * 1024 * 1024) or 1
        ),
        1,
    )


def _support_attachment_image_max_dimension():
    return max(
        int(getattr(settings, "SUPPORT_ATTACHMENT_IMAGE_MAX_DIMENSION", 7000) or 1),
        1,
    )


def _support_attachment_image_max_pixels():
    return max(
        int(getattr(settings, "SUPPORT_ATTACHMENT_IMAGE_MAX_PIXELS", 20_000_000) or 1),
        1,
    )


def _support_attachment_image_is_animated(image):
    if getattr(image, "is_animated", False):
        return True

    try:
        return sum(1 for _frame in ImageSequence.Iterator(image)) > 1
    except Exception:
        return False


def _validate_support_attachment_image(uploaded_file):
    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)

        if image.format not in SUPPORT_ATTACHMENT_IMAGE_FORMATS:
            raise ValidationError("فرمت واقعی تصویر پیوست مجاز نیست.")

        if _support_attachment_image_is_animated(image):
            raise ValidationError("تصویر متحرک برای پیوست پشتیبانی مجاز نیست.")

        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValidationError("ابعاد تصویر پیوست معتبر نیست.")

        max_dimension = _support_attachment_image_max_dimension()
        if width > max_dimension or height > max_dimension:
            raise ValidationError("ابعاد تصویر پیوست بیش از حد مجاز است.")

        if width * height > _support_attachment_image_max_pixels():
            raise ValidationError("تعداد پیکسل‌های تصویر پیوست بیش از حد مجاز است.")

        uploaded_file.seek(0)
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError("فایل پیوست تصویر معتبر نیست.")


def _validate_support_attachment_pdf(uploaded_file):
    uploaded_file.seek(0)
    header = uploaded_file.read(8)
    uploaded_file.seek(0)

    if not header.startswith(b"%PDF-"):
        raise ValidationError("فایل PDF پیوست معتبر نیست.")


def validate_support_attachment_upload(uploaded_file):
    if not uploaded_file:
        return uploaded_file

    if uploaded_file.size > _support_attachment_max_size_bytes():
        raise ValidationError("حجم پیوست بیش از حد مجاز است.")

    original_name = Path(uploaded_file.name or "").name.lower()
    ext = Path(original_name).suffix.lower()

    if ext not in SUPPORT_ATTACHMENT_ALLOWED_EXTENSIONS:
        raise ValidationError(
            "پسوند پیوست مجاز نیست. فقط JPG، PNG یا PDF قابل قبول است."
        )

    name_without_last_ext = original_name[: -len(ext)] if ext else original_name
    if any(
        blocked in name_without_last_ext
        for blocked in SUPPORT_ATTACHMENT_BLOCKED_FILENAME_PARTS
    ):
        raise ValidationError("نام یا پسوند فایل پیوست مجاز نیست.")

    content_type = str(getattr(uploaded_file, "content_type", "") or "")
    content_type = content_type.split(";")[0].strip().lower()

    if content_type not in SUPPORT_ATTACHMENT_ALLOWED_CONTENT_TYPES:
        raise ValidationError(
            "فرمت پیوست مجاز نیست. فقط JPG، PNG یا PDF قابل قبول است."
        )

    if ext == ".pdf":
        if content_type != "application/pdf":
            raise ValidationError("فرمت PDF پیوست معتبر نیست.")
        _validate_support_attachment_pdf(uploaded_file)
        return uploaded_file

    if content_type not in SUPPORT_ATTACHMENT_IMAGE_CONTENT_TYPES:
        raise ValidationError("فرمت تصویر پیوست معتبر نیست.")

    _validate_support_attachment_image(uploaded_file)
    return uploaded_file


class SupportForm(forms.Form):
    ISSUE_TYPE_CHOICES = [
        ("", "چطور می‌توانیم کمک کنیم؟ *"),
        ("account_existing", "من از قبل حساب کاربری دارم و نیاز به پشتیبانی دارم"),
        ("account_join", "می‌خواهم کسب‌وکارم را در Loomera معرفی کنم"),
        ("appointment", "برای یکی از نوبت‌هایم در Loomera به راهنمایی نیاز دارم"),
        ("other", "سایر سؤالات"),
    ]

    SUPPORT_REASON_CHOICES = [
        ("", "موضوع را انتخاب کنید"),
        ("appointments", "نوبت‌های من"),
        ("payments", "پرداخت‌ها و کیف پول"),
        ("reviews", "دیدگاه‌ها و امتیازها"),
        ("notifications", "اعلان‌های ایمیل و پیامک"),
        ("delete_account", "حذف حساب کاربری من"),
        ("other", "سایر"),
    ]

    issue_type = forms.ChoiceField(
        label="موضوع",
        choices=ISSUE_TYPE_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "issue-type-radio"}),
    )

    email = forms.EmailField(
        label="ایمیل *",
        required=True,
        error_messages={
            "required": "ایمیل را وارد کنید.",
            "invalid": "ایمیل واردشده معتبر نیست.",
        },
        widget=forms.EmailInput(
            attrs={
                "class": "w-full px-4 py-2.5 rounded-2xl border border-gray-200 text-gray-900",
                "placeholder": "ایمیل حساب خود را وارد کنید",
            }
        ),
    )

    full_name = forms.CharField(
        label="نام کامل *",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "w-full px-4 py-2.5 rounded-2xl border border-gray-200 text-gray-900",
                "placeholder": "نام کامل خود را وارد کنید",
            }
        ),
    )

    city = forms.CharField(
        label="شهر *",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "w-full px-4 py-2.5 rounded-2xl border border-gray-200 text-gray-900",
                "placeholder": "شهر یا محدوده موردنظر را وارد کنید",
            }
        ),
    )

    mobile = forms.CharField(
        label="شماره موبایل *",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "w-full px-4 py-2.5 rounded-2xl border border-gray-200 text-gray-900",
                "placeholder": "شماره موبایل خود را وارد کنید",
                "inputmode": "tel",
            }
        ),
    )

    support_reason = forms.ChoiceField(
        label="موضوع درخواست *",
        choices=SUPPORT_REASON_CHOICES,
        required=False,
        widget=forms.Select(
            attrs={
                "class": "w-full px-4 py-2.5 rounded-2xl border border-gray-200 text-gray-900",
            }
        ),
    )

    description = forms.CharField(
        label="شرح درخواست *",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "w-full px-4 py-2.5 rounded-2xl border border-gray-200 text-gray-900",
                "rows": 5,
                "maxlength": 2000,
                "placeholder": "موضوع را کوتاه و روشن شرح دهید",
            }
        ),
    )

    attachment = forms.FileField(
        label="پیوست",
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": "hidden",
                "accept": "image/jpeg,image/png,application/pdf",
            }
        ),
    )

    def clean_attachment(self):
        attachment = self.cleaned_data.get("attachment")
        return validate_support_attachment_upload(attachment)

    def clean_email(self):
        value = (self.cleaned_data.get("email") or "").strip().lower()
        if not value:
            raise ValidationError("ایمیل را وارد کنید.")
        return value

    def clean_mobile(self):
        value = to_english_digits(self.cleaned_data.get("mobile") or "").strip()
        if not value:
            return ""

        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) not in (10, 11):
            raise ValidationError("شماره موبایل باید فقط شامل عدد و ۱۰ یا ۱۱ رقم باشد.")
        return digits

    def clean(self):
        cleaned_data = super().clean()
        issue_type = cleaned_data.get("issue_type")

        if issue_type in {"account_existing", "appointment"}:
            if not cleaned_data.get("support_reason"):
                self.add_error("support_reason", "موضوع درخواست را انتخاب کنید.")
            if not cleaned_data.get("description"):
                self.add_error("description", "شرح درخواست را وارد کنید.")

        if issue_type in {"account_join", "other"}:
            for field_name in ["full_name", "city", "mobile", "description"]:
                if not cleaned_data.get(field_name):
                    self.add_error(field_name, "تکمیل این فیلد الزامی است.")

        return cleaned_data


from .models import DisputeCase, SupportAttachment, SupportTicket, SupportTicketMessage


class SupportTicketReplyForm(forms.Form):
    body = forms.CharField(
        label="پیام",
        widget=forms.Textarea(
            attrs={
                "class": "w-full rounded-2xl border border-loomera-borderSoft bg-loomera-bgSubtle px-4 py-3 text-sm leading-7 text-loomera-textPrimary outline-none focus:border-loomera-primary focus:bg-white focus:ring-4 focus:ring-loomera-focusRing/25",
                "rows": 4,
                "placeholder": "پیام خود را بنویسید...",
            }
        ),
    )
    attachment = forms.FileField(
        label="پیوست",
        required=False,
        widget=forms.FileInput(
            attrs={"class": "hidden", "accept": "image/jpeg,image/png,application/pdf"}
        ),
    )

    def clean_attachment(self):
        attachment = self.cleaned_data.get("attachment")
        return validate_support_attachment_upload(attachment)

    def clean_body(self):
        value = (self.cleaned_data.get("body") or "").strip()
        if not value:
            raise ValidationError("متن پیام را وارد کنید.")
        if len(value) > 3000:
            raise ValidationError("متن پیام نباید بیشتر از ۳۰۰۰ کاراکتر باشد.")
        return value


class SupportTicketUpdateForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ["status", "priority", "assigned_team", "assigned_to", "admin_reply"]
        widgets = {
            "status": forms.Select(
                attrs={
                    "class": "w-full rounded-2xl border border-loomera-borderSoft px-3 py-2 text-sm"
                }
            ),
            "priority": forms.Select(
                attrs={
                    "class": "w-full rounded-2xl border border-loomera-borderSoft px-3 py-2 text-sm"
                }
            ),
            "assigned_team": forms.Select(
                attrs={
                    "class": "w-full rounded-2xl border border-loomera-borderSoft px-3 py-2 text-sm"
                }
            ),
            "assigned_to": forms.Select(
                attrs={
                    "class": "w-full rounded-2xl border border-loomera-borderSoft px-3 py-2 text-sm"
                }
            ),
            "admin_reply": forms.Textarea(
                attrs={
                    "rows": 4,
                    "class": "w-full rounded-2xl border border-loomera-borderSoft px-3 py-2 text-sm",
                }
            ),
        }


class DisputeCaseForm(forms.ModelForm):
    class Meta:
        model = DisputeCase
        fields = [
            "dispute_type",
            "priority",
            "subject",
            "description",
            "order",
            "order_detail",
            "salon",
            "stylist",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }
