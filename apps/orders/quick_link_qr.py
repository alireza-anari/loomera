from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from math import ceil
from pathlib import Path

import qrcode
from django.contrib.staticfiles import finders
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from django.utils.text import slugify
from PIL import Image, ImageDraw
from qrcode.constants import ERROR_CORRECT_H

from .models import BookingQuickLink
from .quick_links import build_quick_link_url


BOOKING_QUICK_LINK_QR_GLYPH = (
    "branding/logo/"
    "loomera-glyph-mark-square-transparent-512.png"
)

BOOKING_QUICK_LINK_QR_CONTENT_TYPE = "image/png"

BOOKING_QUICK_LINK_QR_ERROR_CORRECTION = ERROR_CORRECT_H
BOOKING_QUICK_LINK_QR_BORDER_MODULES = 4

BOOKING_QUICK_LINK_QR_MIN_PIXELS = 2048
BOOKING_QUICK_LINK_QR_MIN_BOX_SIZE = 10

BOOKING_QUICK_LINK_QR_FILL_COLOR = "#111111"
BOOKING_QUICK_LINK_QR_BACKGROUND_COLOR = "#FFFFFF"

BOOKING_QUICK_LINK_QR_LOGO_RATIO = 0.16
BOOKING_QUICK_LINK_QR_BACKING_RATIO = 0.19
BOOKING_QUICK_LINK_QR_DPI = 300


PLACEMENT_FILENAME_LABELS = {
    BookingQuickLink.Placement.DIRECT: "direct",
    BookingQuickLink.Placement.MIRROR_LABEL: "mirror",
    BookingQuickLink.Placement.RECEPTION: "reception",
    BookingQuickLink.Placement.TABLE_STAND: "stand",
    BookingQuickLink.Placement.BOOKING_CARD: "booking-card",
    BookingQuickLink.Placement.INSTAGRAM_BIO: "instagram-bio",
    BookingQuickLink.Placement.INSTAGRAM_STORY: "instagram-story",
    BookingQuickLink.Placement.WHATSAPP: "whatsapp",
    BookingQuickLink.Placement.OTHER: "other",
}


@dataclass(frozen=True)
class GeneratedBookingQuickLinkQR:
    content: bytes
    url: str
    filename: str
    content_type: str
    width: int
    height: int
    box_size: int
    border_modules: int
    error_correction: int
    glyph_static_path: str
    logo_width_ratio: float
    warnings: tuple[str, ...]


def _resolve_official_glyph_path() -> Path:
    resolved = finders.find(
        BOOKING_QUICK_LINK_QR_GLYPH
    )

    if not resolved:
        raise ImproperlyConfigured(
            "Glyph رسمی Loomera برای تولید QR پیدا نشد: "
            f"{BOOKING_QUICK_LINK_QR_GLYPH}"
        )

    glyph_path = Path(resolved)

    if not glyph_path.is_file():
        raise ImproperlyConfigured(
            "مسیر Glyph رسمی Loomera فایل معتبر نیست: "
            f"{glyph_path}"
        )

    return glyph_path


def _safe_filename_part(
    value,
    *,
    fallback: str,
) -> str:
    normalized = slugify(
        str(value or "").strip(),
        allow_unicode=True,
    )

    normalized = normalized.replace("_", "-")

    normalized = re.sub(
        r"[^\w\-؀-ۿ]+",
        "-",
        normalized,
        flags=re.UNICODE,
    )

    normalized = re.sub(
        r"-{2,}",
        "-",
        normalized,
    ).strip("-")

    return normalized or fallback


def build_booking_quick_link_qr_filename(
    quick_link: BookingQuickLink,
) -> str:
    salon_name = getattr(
        quick_link.salon,
        "salon_name",
        "",
    )

    salon_part = _safe_filename_part(
        salon_name,
        fallback=f"salon-{quick_link.salon_id}",
    )

    placement_value = (
        quick_link.placement
        or BookingQuickLink.Placement.OTHER
    )

    placement_label = PLACEMENT_FILENAME_LABELS.get(
        placement_value,
        "other",
    )

    placement_part = _safe_filename_part(
        placement_label,
        fallback="other",
    )

    return (
        f"loomera-{salon_part}-"
        f"{placement_part}-link-{quick_link.pk}.png"
    )


def get_booking_quick_link_qr_warnings(
    quick_link: BookingQuickLink,
) -> tuple[str, ...]:
    warnings = []

    if quick_link.archived_at:
        warnings.append(
            "این لینک بایگانی شده و QR آن برای استفاده جدید "
            "مناسب نیست."
        )
    elif not quick_link.is_active:
        warnings.append(
            "این لینک غیرفعال است و پیش از استفاده از QR "
            "باید فعال شود."
        )
    elif (
        quick_link.expires_at
        and timezone.now() >= quick_link.expires_at
    ):
        warnings.append(
            "اعتبار این لینک به پایان رسیده است."
        )

    payload = (
        quick_link.payload
        if isinstance(quick_link.payload, dict)
        else {}
    )

    if (
        quick_link.mode
        == BookingQuickLink.Mode.SERVICE_STYLIST_TIME
        or payload.get("date")
        or payload.get("time")
    ):
        warnings.append(
            "این لینک دارای تاریخ یا ساعت ثابت است و برای "
            "چاپ دائمی پیشنهاد نمی‌شود."
        )

    return tuple(warnings)


def _load_and_prepare_glyph(
    glyph_path: Path,
    *,
    qr_width: int,
    box_size: int,
) -> tuple[Image.Image, int]:
    try:
        with Image.open(glyph_path) as source:
            glyph = source.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise ImproperlyConfigured(
            "Glyph رسمی Loomera یک تصویر PNG معتبر نیست."
        ) from exc

    visible_box = glyph.getbbox()

    if visible_box:
        glyph = glyph.crop(visible_box)

    max_logo_width = max(
        box_size * 4,
        int(qr_width * BOOKING_QUICK_LINK_QR_LOGO_RATIO),
    )

    max_logo_height = max_logo_width

    glyph.thumbnail(
        (max_logo_width, max_logo_height),
        Image.Resampling.LANCZOS,
    )

    return glyph, max_logo_width


def _overlay_official_glyph(
    qr_image: Image.Image,
    *,
    glyph_path: Path,
    box_size: int,
) -> tuple[Image.Image, float]:
    qr_image = qr_image.convert("RGBA")

    glyph, max_logo_width = _load_and_prepare_glyph(
        glyph_path,
        qr_width=qr_image.width,
        box_size=box_size,
    )

    backing_size = max(
        glyph.width + (box_size * 2),
        glyph.height + (box_size * 2),
        int(
            qr_image.width
            * BOOKING_QUICK_LINK_QR_BACKING_RATIO
        ),
    )

    maximum_backing_size = int(
        qr_image.width
        * BOOKING_QUICK_LINK_QR_BACKING_RATIO
    )

    backing_size = min(
        backing_size,
        maximum_backing_size,
    )

    backing_size = max(
        backing_size,
        glyph.width,
        glyph.height,
    )

    backing = Image.new(
        "RGBA",
        (backing_size, backing_size),
        (255, 255, 255, 0),
    )

    draw = ImageDraw.Draw(backing)

    radius = max(
        box_size,
        int(backing_size * 0.14),
    )

    draw.rounded_rectangle(
        (
            0,
            0,
            backing_size - 1,
            backing_size - 1,
        ),
        radius=radius,
        fill=(255, 255, 255, 255),
    )

    glyph_x = (backing_size - glyph.width) // 2
    glyph_y = (backing_size - glyph.height) // 2

    backing.alpha_composite(
        glyph,
        (glyph_x, glyph_y),
    )

    backing_x = (qr_image.width - backing.width) // 2
    backing_y = (qr_image.height - backing.height) // 2

    qr_image.alpha_composite(
        backing,
        (backing_x, backing_y),
    )

    actual_ratio = glyph.width / qr_image.width

    if actual_ratio > BOOKING_QUICK_LINK_QR_LOGO_RATIO:
        raise ImproperlyConfigured(
            "عرض Glyph مرکزی از نسبت مجاز QR بیشتر شد."
        )

    if glyph.width > max_logo_width:
        raise ImproperlyConfigured(
            "ابعاد Glyph مرکزی از محدودیت QR بیشتر شد."
        )

    return qr_image, actual_ratio


def generate_booking_quick_link_qr(
    *,
    request,
    quick_link: BookingQuickLink,
) -> GeneratedBookingQuickLinkQR:
    if not quick_link or not getattr(
        quick_link,
        "pk",
        None,
    ):
        raise ValueError(
            "برای تولید QR یک BookingQuickLink ذخیره‌شده "
            "لازم است."
        )

    public_url = build_quick_link_url(
        request,
        quick_link,
    )

    if not public_url:
        raise ValueError(
            "URL عمومی لینک رزرو برای QR ساخته نشد."
        )

    glyph_path = _resolve_official_glyph_path()

    qr = qrcode.QRCode(
        version=None,
        error_correction=(
            BOOKING_QUICK_LINK_QR_ERROR_CORRECTION
        ),
        box_size=1,
        border=BOOKING_QUICK_LINK_QR_BORDER_MODULES,
    )

    qr.add_data(
        public_url,
        optimize=0,
    )

    qr.make(fit=True)

    total_modules = (
        int(qr.modules_count)
        + (
            BOOKING_QUICK_LINK_QR_BORDER_MODULES
            * 2
        )
    )

    box_size = max(
        BOOKING_QUICK_LINK_QR_MIN_BOX_SIZE,
        ceil(
            BOOKING_QUICK_LINK_QR_MIN_PIXELS
            / total_modules
        ),
    )

    qr.box_size = box_size

    rendered = qr.make_image(
        fill_color=BOOKING_QUICK_LINK_QR_FILL_COLOR,
        back_color=(
            BOOKING_QUICK_LINK_QR_BACKGROUND_COLOR
        ),
    )

    if hasattr(rendered, "get_image"):
        qr_image = rendered.get_image().convert("RGBA")
    else:
        qr_image = rendered.convert("RGBA")

    qr_image, logo_width_ratio = (
        _overlay_official_glyph(
            qr_image,
            glyph_path=glyph_path,
            box_size=box_size,
        )
    )

    output = BytesIO()

    qr_image.convert("RGB").save(
        output,
        format="PNG",
        optimize=True,
        dpi=(
            BOOKING_QUICK_LINK_QR_DPI,
            BOOKING_QUICK_LINK_QR_DPI,
        ),
    )

    content = output.getvalue()

    if not content.startswith(
        b"\x89PNG\r\n\x1a\n"
    ):
        raise ImproperlyConfigured(
            "خروجی سرویس QR یک فایل PNG معتبر نیست."
        )

    return GeneratedBookingQuickLinkQR(
        content=content,
        url=public_url,
        filename=(
            build_booking_quick_link_qr_filename(
                quick_link
            )
        ),
        content_type=(
            BOOKING_QUICK_LINK_QR_CONTENT_TYPE
        ),
        width=qr_image.width,
        height=qr_image.height,
        box_size=box_size,
        border_modules=(
            BOOKING_QUICK_LINK_QR_BORDER_MODULES
        ),
        error_correction=(
            BOOKING_QUICK_LINK_QR_ERROR_CORRECTION
        ),
        glyph_static_path=(
            BOOKING_QUICK_LINK_QR_GLYPH
        ),
        logo_width_ratio=logo_width_ratio,
        warnings=get_booking_quick_link_qr_warnings(
            quick_link
        ),
    )
