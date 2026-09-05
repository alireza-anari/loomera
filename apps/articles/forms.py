from pathlib import Path

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, ImageSequence, UnidentifiedImageError

from .models import Article, SalonStory, StaffContentSubmission, ContentReport

ARTICLE_COVER_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ARTICLE_COVER_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}
ARTICLE_COVER_ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

ARTICLE_COVER_BLOCKED_FILENAME_PARTS = {
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


def _article_cover_image_max_size_bytes():
    return max(
        int(
            getattr(settings, "ARTICLE_COVER_IMAGE_MAX_SIZE_BYTES", 4 * 1024 * 1024)
            or 1
        ),
        1,
    )


def _article_cover_image_max_dimension():
    return max(
        int(getattr(settings, "ARTICLE_COVER_IMAGE_MAX_DIMENSION", 7000) or 1),
        1,
    )


def _article_cover_image_max_pixels():
    return max(
        int(getattr(settings, "ARTICLE_COVER_IMAGE_MAX_PIXELS", 20_000_000) or 1),
        1,
    )


def _article_cover_image_is_animated(image):
    if getattr(image, "is_animated", False):
        return True

    try:
        return sum(1 for _frame in ImageSequence.Iterator(image)) > 1
    except Exception:
        return False


def validate_article_cover_image_upload(uploaded_file, *, declared_content_type=None):
    if not uploaded_file:
        return uploaded_file

    if uploaded_file.size > _article_cover_image_max_size_bytes():
        raise ValidationError("حجم تصویر شاخص بیش از حد مجاز است.")

    original_name = Path(uploaded_file.name or "").name.lower()
    ext = Path(original_name).suffix.lower()

    if ext not in ARTICLE_COVER_ALLOWED_EXTENSIONS:
        raise ValidationError(
            "پسوند تصویر مجاز نیست. فقط جی‌پی‌جی، پی‌اِن‌جی یا وِب‌پی قابل قبول است."
        )

    name_without_last_ext = original_name[: -len(ext)] if ext else original_name
    if any(
        blocked in name_without_last_ext
        for blocked in ARTICLE_COVER_BLOCKED_FILENAME_PARTS
    ):
        raise ValidationError("نام یا پسوند فایل مجاز نیست.")

    content_type = (
        declared_content_type
        if declared_content_type is not None
        else getattr(uploaded_file, "content_type", "")
    )
    content_type = str(content_type or "").split(";")[0].strip().lower()

    if content_type not in ARTICLE_COVER_ALLOWED_CONTENT_TYPES:
        raise ValidationError(
            "فرمت فایل مجاز نیست. فقط جی‌پی‌جی، پی‌اِن‌جی یا وِب‌پی قابل قبول است."
        )

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)

        if image.format not in ARTICLE_COVER_ALLOWED_FORMATS:
            raise ValidationError("فرمت واقعی تصویر مجاز نیست.")

        if _article_cover_image_is_animated(image):
            raise ValidationError("تصویر متحرک برای تصویر شاخص مجاز نیست.")

        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValidationError("ابعاد تصویر معتبر نیست.")

        max_dimension = _article_cover_image_max_dimension()
        if width > max_dimension or height > max_dimension:
            raise ValidationError("ابعاد تصویر بیش از حد مجاز است.")

        if width * height > _article_cover_image_max_pixels():
            raise ValidationError("تعداد پیکسل‌های تصویر بیش از حد مجاز است.")

        uploaded_file.seek(0)
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError("فایل ارسال‌شده تصویر معتبر نیست.")

    return uploaded_file


class ArticleDraftForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        files = kwargs.get("files")
        if files is None and len(args) > 1:
            files = args[1]

        raw_cover_image = files.get("cover_image") if files else None
        self._raw_cover_image_content_type = (
            getattr(raw_cover_image, "content_type", "") or ""
        )

        super().__init__(*args, **kwargs)

        self.fields["cover_image"].widget.attrs.update(
            {"accept": "image/jpeg,image/png,image/webp"}
        )

    class Meta:
        model = Article
        fields = [
            "title",
            "summary",
            "content",
            "cover_image",
            "content_type",
            "category",
            "tags",
            "related_services",
            "related_service_groups",
            "seo_title",
            "seo_description",
            "contains_identifiable_client",
            "client_consent_status",
            "professional_confirmed_responsibility",
        ]

    def clean_cover_image(self):
        cover_image = self.cleaned_data.get("cover_image")
        return validate_article_cover_image_upload(
            cover_image,
            declared_content_type=self._raw_cover_image_content_type or None,
        )


class SalonStoryDraftForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        files = kwargs.get("files")
        if files is None and len(args) > 1:
            files = args[1]

        raw_cover_image = files.get("cover_image") if files else None
        self._raw_cover_image_content_type = (
            getattr(raw_cover_image, "content_type", "") or ""
        )

        super().__init__(*args, **kwargs)

        self.fields["cover_image"].widget.attrs.update(
            {"accept": "image/jpeg,image/png,image/webp"}
        )

    class Meta:
        model = SalonStory
        fields = [
            "salon",
            "stylist",
            "title",
            "summary",
            "cover_image",
            "visibility",
            "expires_at",
            "cta_type",
            "cta_label",
            "cta_url",
            "related_article",
            "related_service",
            "related_service_group",
            "contains_identifiable_client",
            "client_consent_status",
            "professional_confirmed_responsibility",
        ]

    def clean_cover_image(self):
        cover_image = self.cleaned_data.get("cover_image")
        return validate_article_cover_image_upload(
            cover_image,
            declared_content_type=self._raw_cover_image_content_type or None,
        )


STAFF_CONTENT_MEDIA_ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".mp4",
}

STAFF_CONTENT_MEDIA_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "video/mp4",
}

STAFF_CONTENT_MEDIA_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

STAFF_CONTENT_MEDIA_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}

STAFF_CONTENT_MEDIA_BLOCKED_FILENAME_PARTS = {
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
    ".pdf",
}


def _staff_content_media_max_size_bytes():
    return max(
        int(
            getattr(
                settings,
                "STAFF_CONTENT_MEDIA_MAX_SIZE_BYTES",
                25 * 1024 * 1024,
            )
            or 1
        ),
        1,
    )


def _staff_content_media_image_max_dimension():
    return max(
        int(
            getattr(
                settings,
                "STAFF_CONTENT_MEDIA_IMAGE_MAX_DIMENSION",
                7000,
            )
            or 1
        ),
        1,
    )


def _staff_content_media_image_max_pixels():
    return max(
        int(
            getattr(
                settings,
                "STAFF_CONTENT_MEDIA_IMAGE_MAX_PIXELS",
                20_000_000,
            )
            or 1
        ),
        1,
    )


def _staff_content_media_image_is_animated(image):
    if getattr(image, "is_animated", False):
        return True

    try:
        return sum(1 for _frame in ImageSequence.Iterator(image)) > 1
    except Exception:
        return False


def _validate_staff_content_media_image(uploaded_file):
    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)

        if image.format not in STAFF_CONTENT_MEDIA_IMAGE_FORMATS:
            raise ValidationError("فرمت واقعی تصویر محتوا مجاز نیست.")

        if _staff_content_media_image_is_animated(image):
            raise ValidationError("تصویر متحرک برای محتوای پیشنهادی مجاز نیست.")

        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValidationError("ابعاد تصویر محتوا معتبر نیست.")

        max_dimension = _staff_content_media_image_max_dimension()
        if width > max_dimension or height > max_dimension:
            raise ValidationError("ابعاد تصویر محتوا بیش از حد مجاز است.")

        if width * height > _staff_content_media_image_max_pixels():
            raise ValidationError("تعداد پیکسل‌های تصویر محتوا بیش از حد مجاز است.")

        uploaded_file.seek(0)
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError("فایل محتوای تصویری معتبر نیست.")


def _validate_staff_content_media_mp4(uploaded_file):
    uploaded_file.seek(0)
    header = uploaded_file.read(64)
    uploaded_file.seek(0)

    # MP4 باید box ابتدایی ftyp داشته باشد. این بررسی سبک است و جلوی فایل متنی/جعلی را می‌گیرد.
    if b"ftyp" not in header[:32]:
        raise ValidationError("فایل ویدیویی اِم‌پی۴ معتبر نیست.")


def validate_staff_content_media_upload(uploaded_file, *, declared_content_type=None):
    if not uploaded_file:
        return uploaded_file

    if uploaded_file.size > _staff_content_media_max_size_bytes():
        raise ValidationError("حجم فایل محتوا بیش از حد مجاز است.")

    original_name = Path(uploaded_file.name or "").name.lower()
    ext = Path(original_name).suffix.lower()

    if ext not in STAFF_CONTENT_MEDIA_ALLOWED_EXTENSIONS:
        raise ValidationError(
            "پسوند فایل محتوا مجاز نیست. فقط جی‌پی‌جی، پی‌اِن‌جی، وِب‌پی یا اِم‌پی۴ قابل قبول است."
        )

    name_without_last_ext = original_name[: -len(ext)] if ext else original_name
    if any(
        blocked in name_without_last_ext
        for blocked in STAFF_CONTENT_MEDIA_BLOCKED_FILENAME_PARTS
    ):
        raise ValidationError("نام یا پسوند فایل محتوا مجاز نیست.")

    content_type = (
        declared_content_type
        if declared_content_type is not None
        else getattr(uploaded_file, "content_type", "")
    )
    content_type = str(content_type or "").split(";")[0].strip().lower()

    if content_type not in STAFF_CONTENT_MEDIA_ALLOWED_CONTENT_TYPES:
        raise ValidationError(
            "فرمت فایل محتوا مجاز نیست. فقط جی‌پی‌جی، پی‌اِن‌جی، وِب‌پی یا اِم‌پی۴ قابل قبول است."
        )

    if ext == ".mp4":
        if content_type != "video/mp4":
            raise ValidationError("فرمت ویدیوی محتوا معتبر نیست.")
        _validate_staff_content_media_mp4(uploaded_file)
        return uploaded_file

    if content_type not in STAFF_CONTENT_MEDIA_IMAGE_CONTENT_TYPES:
        raise ValidationError("فرمت تصویر محتوا معتبر نیست.")

    _validate_staff_content_media_image(uploaded_file)
    return uploaded_file


class StaffContentSubmissionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        files = kwargs.get("files")
        if files is None and len(args) > 1:
            files = args[1]

        raw_media = files.get("media") if files else None
        self._raw_media_content_type = getattr(raw_media, "content_type", "") or ""

        super().__init__(*args, **kwargs)

        self.fields["media"].widget.attrs.update(
            {"accept": "image/jpeg,image/png,image/webp,video/mp4"}
        )

    class Meta:
        model = StaffContentSubmission
        fields = [
            "submission_type",
            "title",
            "body",
            "media",
            "contains_identifiable_client",
            "client_consent_status",
            "professional_confirmed_responsibility",
        ]

    def clean_media(self):
        media = self.cleaned_data.get("media")
        return validate_staff_content_media_upload(
            media,
            declared_content_type=self._raw_media_content_type or None,
        )

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("professional_confirmed_responsibility"):
            self.add_error(
                "professional_confirmed_responsibility",
                "برای ارسال محتوا باید مسئولیت اصالت و مجوز انتشار را تأیید کنید.",
            )
        if cleaned.get("contains_identifiable_client") and cleaned.get(
            "client_consent_status"
        ) in {"", "not_required"}:
            self.add_error(
                "client_consent_status",
                "برای محتوای دارای هویت قابل تشخیص مشتری، وضعیت رضایت مشتری را مشخص کنید.",
            )
        return cleaned


class ContentReportForm(forms.ModelForm):
    class Meta:
        model = ContentReport
        fields = ["reason", "description"]
