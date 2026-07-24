from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.exceptions import DisallowedHost
from django.core.exceptions import ImproperlyConfigured
from PIL import Image, ImageDraw, ImageFont, ImageOps, features

from .models import BookingQuickLink
from .quick_link_qr import generate_booking_quick_link_qr


PRINT_TEMPLATE_DPI = 300
PRINT_TEMPLATE_PREVIEW_MAX_PIXELS = 900
PRINT_TEMPLATE_CONTENT_TYPE = "image/png"

PRINT_TEMPLATE_LOGO = (
    "branding/logo/loomera-logo-horizontal-rtl-transparent-360.png"
)
PRINT_TEMPLATE_SYMBOL = (
    "branding/logo/loomera-symbol-transparent-160.png"
)
PRINT_TEMPLATE_FONT_REGULAR = (
    "fonts/yekan-bakh/YekanBakh-Regular.woff2"
)
PRINT_TEMPLATE_FONT_BOLD = (
    "fonts/yekan-bakh/YekanBakh-Bold.woff2"
)
PRINT_TEMPLATE_FONT_BLACK = (
    "fonts/yekan-bakh/YekanBakh-Black.woff2"
)

PRINT_TEMPLATE_MIRROR_LABEL_ART = (
    "branding/quick-links/mirror-label-print-art.png"
)


PRINT_TEMPLATE_BUSINESS_CARD_FRONT_ART = (
    "branding/quick-links/business-card-front.png"
)
PRINT_TEMPLATE_BUSINESS_CARD_BACK_ART = (
    "branding/quick-links/business-card-back.png"
)


PRINT_TEMPLATE_TABLE_STAND_ART = (
    "branding/quick-links/table-stand.png"
)

TABLE_STAND_NAME_BOX = (
    240,
    530,
    1070,
    820,
)
TABLE_STAND_QR_BOX = (
    735,
    1295,
    1025,
    1585,
)


TABLE_STAND_TRIM_BOX = (
    35,
    35,
    1275,
    1783,
)
TABLE_STAND_BLEED_MM = 3
TABLE_STAND_FINISHED_WIDTH_MM = 105
TABLE_STAND_FINISHED_HEIGHT_MM = 148

# Stage 14I: the reusable template itself is
# print-ready for every salon.
TABLE_STAND_PRINT_TEMPLATE_V2 = True

# Stage 14H marker: approved advertising-heavy
# table-stand artwork with dynamic salon name and QR.
TABLE_STAND_PRINT_ART_V1 = True

BUSINESS_CARD_FRONT_QR_BOX = (
    742,
    174,
    966,
    398,
)
BUSINESS_CARD_FRONT_NAME_CENTER = (
    278,
    463,
)

BUSINESS_CARD_BACK_VALUE_X = 872
BUSINESS_CARD_BACK_ROW_CENTERS = (
    149,
    223,
    297,
    371,
    444,
)


BUSINESS_CARD_BACK_LTR_X = 505
BUSINESS_CARD_BACK_VALUE_WIDTH = 360

# Stage 14F marker: corrected full-frame white
# print canvas and calibrated dynamic regions.
BUSINESS_CARD_PRINT_FIDELITY_V3 = True

# Coordinates are based on the approved 945x945 artwork.
# The purple placeholder border remains part of the artwork;
# the live QR is inserted only inside its white area.
MIRROR_LABEL_QR_BOX = (
    320,
    385,
    625,
    690,
)

PURPLE = (115, 92, 190, 255)
PURPLE_DARK = (77, 60, 139, 255)
PURPLE_SOFT = (248, 245, 255, 255)
TEXT = (46, 42, 60, 255)
TEXT_MUTED = (112, 105, 129, 255)
GREEN = (167, 200, 161, 255)
WHITE = (255, 255, 255, 255)
TRANSPARENT = (255, 255, 255, 0)


@dataclass(frozen=True)
class BookingQuickLinkPrintTemplateSpec:
    key: str
    label: str
    description: str
    width: int
    height: int
    width_mm: int
    height_mm: int
    transparent: bool = False


@dataclass(frozen=True)
class GeneratedBookingQuickLinkPrintTemplate:
    content: bytes
    filename: str
    content_type: str
    width: int
    height: int
    dpi: int
    template: BookingQuickLinkPrintTemplateSpec
    is_preview: bool


PRINT_TEMPLATE_SPECS = (
    BookingQuickLinkPrintTemplateSpec(
        key="mirror_label",
        label="لیبل کنار آینه",
        description=(
            "قالب مربعی با پس‌زمینه شفاف، مناسب چاپ روی استیکر شفاف آینه."
        ),
        width=945,
        height=945,
        width_mm=80,
        height_mm=80,
        transparent=True,
    ),
    BookingQuickLinkPrintTemplateSpec(
        key="business_card",
        label="کارت ویزیت دو رو",
        description=(
            "کارت دو رو با نام مجموعه، QR رزرو "
            "و اطلاعات تماس خودکار."
        ),
        width=1075,
        height=575,
        width_mm=91,
        height_mm=49,
    ),
    BookingQuickLinkPrintTemplateSpec(
        key="table_stand",
        label="استند رومیزی",
        description=(
            "استند عمودی A6 آماده چاپ با Bleed "
            "سه میلی‌متری، نام مجموعه و QR پویا."
        ),
        width=1311,
        height=1819,
        width_mm=105,
        height_mm=148,
    ),
    BookingQuickLinkPrintTemplateSpec(
        key="counter_card",
        label="کارت روی میز",
        description=(
            "طرح افقی A6 برای قاب رومیزی، کانتر پذیرش یا پایه پلکسی."
        ),
        width=1748,
        height=1240,
        width_mm=148,
        height_mm=105,
    ),
)

PRINT_TEMPLATE_BY_KEY = {
    spec.key: spec
    for spec in PRINT_TEMPLATE_SPECS
}


def list_booking_quick_link_print_templates():
    return PRINT_TEMPLATE_SPECS


def get_booking_quick_link_print_template_spec(template_key: str):
    key = str(template_key or "").strip().lower()

    try:
        return PRINT_TEMPLATE_BY_KEY[key]
    except KeyError as exc:
        raise ValueError(
            "قالب چاپی انتخاب‌شده معتبر نیست."
        ) from exc


def _resolve_static_path(static_path: str) -> Path:
    resolved = finders.find(static_path)

    if not resolved:
        raise ImproperlyConfigured(
            f"فایل استاتیک لازم برای قالب چاپی پیدا نشد: {static_path}"
        )

    path = Path(resolved)

    if not path.is_file():
        raise ImproperlyConfigured(
            f"مسیر فایل استاتیک قالب چاپی معتبر نیست: {path}"
        )

    return path


def validate_booking_quick_link_print_template_dependencies():
    missing = []

    # RAQM improves complex-text rendering, but it is optional.
    # Windows Pillow wheels may be built without RAQM. In that
    # environment the local Persian shaping fallback below is used.
    for static_path in (
        PRINT_TEMPLATE_LOGO,
        PRINT_TEMPLATE_SYMBOL,
        PRINT_TEMPLATE_FONT_REGULAR,
        PRINT_TEMPLATE_FONT_BOLD,
        PRINT_TEMPLATE_FONT_BLACK,
    ):
        if not finders.find(static_path):
            missing.append(static_path)

    return tuple(missing)


# Arabic Presentation Forms used only when Pillow has no RAQM.
# Tuple order: isolated, final, initial, medial.
_ARABIC_FORMS = {
    "ء": ("\ufe80", None, None, None),
    "آ": ("\ufe81", "\ufe82", None, None),
    "أ": ("\ufe83", "\ufe84", None, None),
    "ؤ": ("\ufe85", "\ufe86", None, None),
    "إ": ("\ufe87", "\ufe88", None, None),
    "ئ": ("\ufe89", "\ufe8a", "\ufe8b", "\ufe8c"),
    "ا": ("\ufe8d", "\ufe8e", None, None),
    "ب": ("\ufe8f", "\ufe90", "\ufe91", "\ufe92"),
    "ة": ("\ufe93", "\ufe94", None, None),
    "ت": ("\ufe95", "\ufe96", "\ufe97", "\ufe98"),
    "ث": ("\ufe99", "\ufe9a", "\ufe9b", "\ufe9c"),
    "ج": ("\ufe9d", "\ufe9e", "\ufe9f", "\ufea0"),
    "ح": ("\ufea1", "\ufea2", "\ufea3", "\ufea4"),
    "خ": ("\ufea5", "\ufea6", "\ufea7", "\ufea8"),
    "د": ("\ufea9", "\ufeaa", None, None),
    "ذ": ("\ufeab", "\ufeac", None, None),
    "ر": ("\ufead", "\ufeae", None, None),
    "ز": ("\ufeaf", "\ufeb0", None, None),
    "س": ("\ufeb1", "\ufeb2", "\ufeb3", "\ufeb4"),
    "ش": ("\ufeb5", "\ufeb6", "\ufeb7", "\ufeb8"),
    "ص": ("\ufeb9", "\ufeba", "\ufebb", "\ufebc"),
    "ض": ("\ufebd", "\ufebe", "\ufebf", "\ufec0"),
    "ط": ("\ufec1", "\ufec2", "\ufec3", "\ufec4"),
    "ظ": ("\ufec5", "\ufec6", "\ufec7", "\ufec8"),
    "ع": ("\ufec9", "\ufeca", "\ufecb", "\ufecc"),
    "غ": ("\ufecd", "\ufece", "\ufecf", "\ufed0"),
    "ف": ("\ufed1", "\ufed2", "\ufed3", "\ufed4"),
    "ق": ("\ufed5", "\ufed6", "\ufed7", "\ufed8"),
    "ك": ("\ufed9", "\ufeda", "\ufedb", "\ufedc"),
    "ک": ("\ufb8e", "\ufb8f", "\ufb90", "\ufb91"),
    "گ": ("\ufb92", "\ufb93", "\ufb94", "\ufb95"),
    "ل": ("\ufedd", "\ufede", "\ufedf", "\ufee0"),
    "م": ("\ufee1", "\ufee2", "\ufee3", "\ufee4"),
    "ن": ("\ufee5", "\ufee6", "\ufee7", "\ufee8"),
    "ه": ("\ufee9", "\ufeea", "\ufeeb", "\ufeec"),
    "و": ("\ufeed", "\ufeee", None, None),
    "ى": ("\ufeef", "\ufef0", None, None),
    "ي": ("\ufef1", "\ufef2", "\ufef3", "\ufef4"),
    "ی": ("\ufbfc", "\ufbfd", "\ufbfe", "\ufbff"),
    "پ": ("\ufb56", "\ufb57", "\ufb58", "\ufb59"),
    "چ": ("\ufb7a", "\ufb7b", "\ufb7c", "\ufb7d"),
    "ژ": ("\ufb8a", "\ufb8b", None, None),
}

_RTL_MIRROR = str.maketrans(
    {
        "(": ")",
        ")": "(",
        "[": "]",
        "]": "[",
        "{": "}",
        "}": "{",
        "<": ">",
        ">": "<",
    }
)


def _has_raqm():
    return bool(features.check("raqm"))


def _can_join_previous(character):
    forms = _ARABIC_FORMS.get(character)
    return bool(forms and forms[1])


def _can_join_next(character):
    forms = _ARABIC_FORMS.get(character)
    return bool(forms and forms[2])


def _shape_arabic_run(value):
    characters = list(str(value or ""))
    shaped = []

    for index, character in enumerate(characters):
        forms = _ARABIC_FORMS.get(character)

        if not forms:
            if character != "\u200c":
                shaped.append(character)
            continue

        previous = (
            characters[index - 1]
            if index > 0
            else ""
        )
        following = (
            characters[index + 1]
            if index + 1 < len(characters)
            else ""
        )

        joins_previous = (
            _can_join_next(previous)
            and _can_join_previous(character)
        )
        joins_next = (
            _can_join_next(character)
            and _can_join_previous(following)
        )

        isolated, final, initial, medial = forms

        if joins_previous and joins_next and medial:
            shaped.append(medial)
        elif joins_previous and final:
            shaped.append(final)
        elif joins_next and initial:
            shaped.append(initial)
        else:
            shaped.append(isolated)

    return "".join(shaped)


def _is_arabic_character(character):
    codepoint = ord(character)
    return (
        character in _ARABIC_FORMS
        or 0x0600 <= codepoint <= 0x06FF
        or 0x0750 <= codepoint <= 0x077F
        or 0x08A0 <= codepoint <= 0x08FF
    )


def _fallback_visual_token(token):
    if not token:
        return ""

    runs = []
    current = []
    current_is_arabic = None

    for character in token:
        is_arabic = _is_arabic_character(
            character
        )

        if (
            current
            and is_arabic != current_is_arabic
        ):
            runs.append(
                (
                    current_is_arabic,
                    "".join(current),
                )
            )
            current = []

        current.append(character)
        current_is_arabic = is_arabic

    if current:
        runs.append(
            (
                current_is_arabic,
                "".join(current),
            )
        )

    visual_runs = []

    for is_arabic, run in runs:
        if is_arabic:
            visual_runs.append(
                _shape_arabic_run(run)[::-1]
            )
        else:
            visual_runs.append(
                run.translate(_RTL_MIRROR)
            )

    return "".join(reversed(visual_runs))


def _fallback_rtl_display(value):
    tokens = re.split(
        r"(\s+)",
        str(value or ""),
    )

    visual_tokens = [
        (
            token
            if token.isspace()
            else _fallback_visual_token(token)
        )
        for token in tokens
        if token != ""
    ]

    return "".join(reversed(visual_tokens))


def _rtl_text(value):
    value = str(value or "")

    if _has_raqm():
        return value

    return _fallback_rtl_display(value)


def _rtl_layout_kwargs():
    if not _has_raqm():
        return {}

    return {
        "direction": "rtl",
        "language": "fa",
    }


@lru_cache(maxsize=96)
def _load_font(weight: str, size: int):
    static_path = {
        "regular": PRINT_TEMPLATE_FONT_REGULAR,
        "bold": PRINT_TEMPLATE_FONT_BOLD,
        "black": PRINT_TEMPLATE_FONT_BLACK,
    }.get(weight, PRINT_TEMPLATE_FONT_REGULAR)

    arguments = (
        str(_resolve_static_path(static_path)),
        int(size),
    )

    if _has_raqm():
        return ImageFont.truetype(
            *arguments,
            layout_engine=ImageFont.Layout.RAQM,
        )

    try:
        return ImageFont.truetype(
            *arguments,
            layout_engine=ImageFont.Layout.BASIC,
        )
    except (AttributeError, TypeError):
        return ImageFont.truetype(*arguments)


def _load_asset(static_path: str, *, max_size: tuple[int, int]):
    try:
        with Image.open(_resolve_static_path(static_path)) as source:
            image = source.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise ImproperlyConfigured(
            f"تصویر برندینگ قالب چاپی قابل خواندن نیست: {static_path}"
        ) from exc

    visible_box = image.getbbox()
    if visible_box:
        image = image.crop(visible_box)

    image.thumbnail(max_size, Image.Resampling.LANCZOS)
    return image


def _tint_asset(image, color):
    tinted = Image.new(
        "RGBA",
        image.size,
        color,
    )
    tinted.putalpha(image.getchannel("A"))
    return tinted


def _fit_font(
    draw,
    text,
    *,
    max_width,
    start_size,
    minimum_size,
    weight="bold",
):
    value = _rtl_text(
        str(text or "").strip()
    )
    layout_kwargs = _rtl_layout_kwargs()

    for size in range(int(start_size), int(minimum_size) - 1, -2):
        font = _load_font(weight, size)
        box = draw.textbbox(
            (0, 0),
            value,
            font=font,
            **layout_kwargs,
        )

        if box[2] - box[0] <= max_width:
            return font

    return _load_font(weight, minimum_size)


def _draw_rtl(
    draw,
    xy,
    text,
    *,
    font,
    fill,
    anchor="ra",
):
    draw.text(
        xy,
        _rtl_text(text),
        font=font,
        fill=fill,
        anchor=anchor,
        **_rtl_layout_kwargs(),
    )


def _safe_filename_part(value, *, fallback):
    normalized = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )
    ascii_value = normalized.encode(
        "ascii",
        "ignore",
    ).decode("ascii")
    ascii_value = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "-",
        ascii_value,
    ).strip("-_")

    return ascii_value[:60] or fallback


def _filename(quick_link, spec):
    salon_part = _safe_filename_part(
        getattr(quick_link.salon, "salon_name", ""),
        fallback=f"salon-{quick_link.salon_id}",
    )

    return (
        f"loomera-{salon_part}-{spec.key}-"
        f"link-{quick_link.pk}.png"
    )


def _context_label(quick_link):
    payload = (
        quick_link.payload
        if isinstance(quick_link.payload, dict)
        else {}
    )
    summary = (
        payload.get("summary")
        if isinstance(payload.get("summary"), dict)
        else {}
    )

    service_name = (
        summary.get("service")
        or getattr(quick_link.service, "service_name", "")
        or ""
    )
    stylist_name = (
        summary.get("stylist")
        or (
            quick_link.stylist.get_fullName()
            if quick_link.stylist
            else ""
        )
        or ""
    )

    if quick_link.mode == BookingQuickLink.Mode.SALON:
        return "مشاهده خدمات و رزرو آنلاین"

    if quick_link.mode == BookingQuickLink.Mode.SERVICE:
        return service_name or "رزرو آنلاین خدمات"

    if quick_link.mode == BookingQuickLink.Mode.STYLIST:
        return (
            f"رزرو با {stylist_name}"
            if stylist_name
            else "رزرو با متخصص"
        )

    if service_name and stylist_name:
        return f"{service_name} با {stylist_name}"

    return service_name or stylist_name or "رزرو آنلاین"


def _qr_image(*, request, quick_link, target_size):
    generated = generate_booking_quick_link_qr(
        request=request,
        quick_link=quick_link,
    )

    try:
        with Image.open(BytesIO(generated.content)) as source:
            qr = source.convert("RGBA")
    except (OSError, TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            "خروجی QR برای قرار گرفتن در قالب چاپی معتبر نیست."
        ) from exc

    qr = ImageOps.contain(
        qr,
        (target_size, target_size),
        Image.Resampling.NEAREST,
    )
    return qr


def _paste_center(canvas, image, center):
    x = int(center[0] - (image.width / 2))
    y = int(center[1] - (image.height / 2))
    canvas.alpha_composite(image, (x, y))


def _rounded_qr_card(canvas, qr, box, *, radius, padding):
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=WHITE,
        outline=(226, 220, 240, 255),
        width=max(2, radius // 10),
    )

    left, top, right, bottom = box
    available = min(
        (right - left) - (padding * 2),
        (bottom - top) - (padding * 2),
    )
    qr = ImageOps.contain(
        qr,
        (available, available),
        Image.Resampling.NEAREST,
    )
    _paste_center(
        canvas,
        qr,
        (
            (left + right) / 2,
            (top + bottom) / 2,
        ),
    )


def _vertical_gradient(size, start, end):
    width, height = size
    strip = Image.new("RGBA", (1, height), start)
    pixels = strip.load()

    for y in range(height):
        ratio = y / max(height - 1, 1)
        pixels[0, y] = tuple(
            int(start[index] + ((end[index] - start[index]) * ratio))
            for index in range(4)
        )

    return strip.resize((width, height))


def _load_mirror_label_art(spec):
    static_path = _resolve_static_path(
        PRINT_TEMPLATE_MIRROR_LABEL_ART
    )

    try:
        with Image.open(static_path) as source:
            image = source.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise ImproperlyConfigured(
            "فایل هنری لیبل آینه قابل خواندن نیست."
        ) from exc

    if image.size != (
        spec.width,
        spec.height,
    ):
        raise ImproperlyConfigured(
            "ابعاد فایل هنری لیبل آینه باید "
            f"{spec.width}x{spec.height} پیکسل باشد."
        )

    if image.getpixel((0, 0))[3] != 0:
        raise ImproperlyConfigured(
            "پس‌زمینه فایل هنری لیبل آینه "
            "باید شفاف واقعی باشد."
        )

    return image


def _render_mirror_label(
    *,
    request,
    quick_link,
    spec,
):
    canvas = _load_mirror_label_art(spec)

    left, top, right, bottom = (
        MIRROR_LABEL_QR_BOX
    )
    box_width = right - left
    box_height = bottom - top

    qr = _qr_image(
        request=request,
        quick_link=quick_link,
        target_size=min(
            box_width,
            box_height,
        ),
    )
    qr = ImageOps.contain(
        qr,
        (
            box_width,
            box_height,
        ),
        Image.Resampling.LANCZOS,
    )

    qr_x = left + (
        (box_width - qr.width) // 2
    )
    qr_y = top + (
        (box_height - qr.height) // 2
    )

    canvas.alpha_composite(
        qr,
        (
            qr_x,
            qr_y,
        ),
    )

    return canvas



def _load_business_card_art(
    *,
    side,
    spec,
):
    static_path = {
        "front": PRINT_TEMPLATE_BUSINESS_CARD_FRONT_ART,
        "back": PRINT_TEMPLATE_BUSINESS_CARD_BACK_ART,
    }.get(side)

    if not static_path:
        raise ValueError("سمت کارت ویزیت معتبر نیست.")

    try:
        with Image.open(_resolve_static_path(static_path)) as source:
            image = source.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise ImproperlyConfigured(
            "فایل هنری کارت ویزیت قابل خواندن نیست."
        ) from exc

    if image.size != (spec.width, spec.height):
        raise ImproperlyConfigured(
            "ابعاد فایل هنری کارت ویزیت با قرارداد چاپ سازگار نیست."
        )

    return image


def _single_line_value(value):
    return " ".join(str(value or "").split()).strip()


def _business_card_public_salon_url(
    request,
    salon,
):
    canonical = _single_line_value(
        getattr(
            salon,
            "canonical_url",
            "",
        )
    )

    local_markers = (
        "127.0.0.1",
        "localhost",
        "0.0.0.0",
        "testserver",
    )

    if (
        canonical
        and not any(
            marker in canonical.lower()
            for marker in local_markers
        )
    ):
        return canonical

    public_base = ""

    for setting_name in (
        "PUBLIC_BASE_URL",
        "SITE_URL",
    ):
        candidate = _single_line_value(
            getattr(
                settings,
                setting_name,
                "",
            )
        )

        if (
            candidate
            and not any(
                marker
                in candidate.lower()
                for marker in local_markers
            )
        ):
            public_base = candidate
            break

    if not public_base:
        public_base = "https://loomera.ir"

    return (
        public_base.rstrip("/")
        + "/"
        + salon.get_absolute_url().lstrip("/")
    )


def _business_card_display_url(value):
    cleaned = _single_line_value(value)
    for prefix in ("https://", "http://"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    if cleaned.lower().startswith("www."):
        cleaned = cleaned[4:]
    return cleaned.rstrip("/")


def _business_card_instagram(value):
    cleaned = _single_line_value(value)
    if not cleaned:
        return "—"
    if cleaned.startswith("@"):
        return cleaned

    normalized = cleaned.rstrip("/")
    lower = normalized.lower()
    marker = "instagram.com/"

    if marker in lower:
        index = lower.index(marker) + len(marker)
        username = normalized[index:].split("/", 1)[0]
        return f"@{username}" if username else "—"

    return normalized


def _business_card_salon_data(
    *,
    request,
    salon,
):
    website = _business_card_display_url(
        _business_card_public_salon_url(
            request,
            salon,
        )
    )

    return {
        "salon_name": _single_line_value(
            getattr(
                salon,
                "salon_name",
                "",
            )
        ),
        "website": website,
        "instagram": (
            _business_card_instagram(
                getattr(
                    salon,
                    "insta_link",
                    "",
                )
            )
            if getattr(
                salon,
                "insta_link",
                "",
            )
            else ""
        ),
        "phone": _single_line_value(
            getattr(
                salon,
                "phone_number",
                "",
            )
        ),
        "address": _single_line_value(
            getattr(
                salon,
                "address",
                "",
            )
        ),
    }


def _draw_ltr_fit(
    draw,
    *,
    xy,
    text,
    max_width,
    start_size,
    minimum_size,
    fill,
    anchor="lm",
):
    value = str(text or "").strip()

    if not value:
        return

    selected_font = None

    for size in range(
        int(start_size),
        int(minimum_size) - 1,
        -1,
    ):
        font = _load_font(
            "regular",
            size,
        )
        box = draw.textbbox(
            (0, 0),
            value,
            font=font,
        )

        if box[2] - box[0] <= max_width:
            selected_font = font
            break

    if selected_font is None:
        selected_font = _load_font(
            "regular",
            minimum_size,
        )
        ellipsis = "…"
        shortened = value

        while len(shortened) > 1:
            candidate = (
                shortened.rstrip()
                + ellipsis
            )
            box = draw.textbbox(
                (0, 0),
                candidate,
                font=selected_font,
            )

            if (
                box[2] - box[0]
                <= max_width
            ):
                value = candidate
                break

            shortened = shortened[:-1]
        else:
            value = ellipsis

    draw.text(
        xy,
        value,
        font=selected_font,
        fill=fill,
        anchor=anchor,
    )


def _business_card_rtl_value(
    draw,
    *,
    value,
    max_width,
    start_size,
    minimum_size,
    weight="regular",
):
    cleaned = str(value or "").strip()

    if not cleaned:
        return "", _load_font(
            weight,
            minimum_size,
        )

    for size in range(
        int(start_size),
        int(minimum_size) - 1,
        -1,
    ):
        font = _load_font(
            weight,
            size,
        )
        visual = _rtl_text(cleaned)
        box = draw.textbbox(
            (0, 0),
            visual,
            font=font,
            **_rtl_layout_kwargs(),
        )

        if box[2] - box[0] <= max_width:
            return cleaned, font

    font = _load_font(
        weight,
        minimum_size,
    )
    shortened = cleaned
    ellipsis = "…"

    while len(shortened) > 1:
        candidate = (
            shortened.rstrip()
            + ellipsis
        )
        visual = _rtl_text(candidate)
        box = draw.textbbox(
            (0, 0),
            visual,
            font=font,
            **_rtl_layout_kwargs(),
        )

        if box[2] - box[0] <= max_width:
            return candidate, font

        shortened = shortened[:-1]

    return ellipsis, font


def _draw_business_card_rtl_wrapped(
    draw,
    *,
    xy,
    text,
    max_width,
    max_height,
    max_lines=2,
    start_size=15,
    minimum_size=10,
    fill=TEXT,
    weight="regular",
    line_spacing=2,
):
    cleaned = str(text or "").strip()

    if not cleaned:
        return

    words = cleaned.split()

    def build_lines(font):
        lines = []
        current = []

        for word in words:
            candidate = " ".join(
                [*current, word]
            )
            visual = _rtl_text(candidate)
            box = draw.textbbox(
                (0, 0),
                visual,
                font=font,
                **_rtl_layout_kwargs(),
            )

            if (
                current
                and box[2] - box[0]
                > max_width
            ):
                lines.append(
                    " ".join(current)
                )
                current = [word]
            else:
                current.append(word)

        if current:
            lines.append(
                " ".join(current)
            )

        return lines

    chosen_font = None
    chosen_lines = None
    chosen_line_height = None

    for size in range(
        int(start_size),
        int(minimum_size) - 1,
        -1,
    ):
        font = _load_font(
            weight,
            size,
        )
        lines = build_lines(font)
        sample_box = draw.textbbox(
            (0, 0),
            _rtl_text("آی"),
            font=font,
            **_rtl_layout_kwargs(),
        )
        line_height = max(
            1,
            sample_box[3] - sample_box[1],
        )
        total_height = (
            (line_height * len(lines))
            + (
                line_spacing
                * max(
                    len(lines) - 1,
                    0,
                )
            )
        )

        if (
            len(lines) <= max_lines
            and total_height <= max_height
        ):
            chosen_font = font
            chosen_lines = lines
            chosen_line_height = (
                line_height
            )
            break

    if chosen_font is None:
        chosen_font = _load_font(
            weight,
            minimum_size,
        )
        chosen_lines = build_lines(
            chosen_font
        )
        sample_box = draw.textbbox(
            (0, 0),
            _rtl_text("آی"),
            font=chosen_font,
            **_rtl_layout_kwargs(),
        )
        chosen_line_height = max(
            1,
            sample_box[3] - sample_box[1],
        )

        if len(chosen_lines) > max_lines:
            kept = chosen_lines[
                : max_lines - 1
            ]
            remainder = " ".join(
                chosen_lines[
                    max_lines - 1 :
                ]
            )
            shortened, _font = (
                _business_card_rtl_value(
                    draw,
                    value=remainder,
                    max_width=max_width,
                    start_size=minimum_size,
                    minimum_size=minimum_size,
                    weight=weight,
                )
            )
            chosen_lines = [
                *kept,
                shortened,
            ]

    total_height = (
        (
            chosen_line_height
            * len(chosen_lines)
        )
        + (
            line_spacing
            * max(
                len(chosen_lines) - 1,
                0,
            )
        )
    )
    top = xy[1] - (
        total_height / 2
    )

    for index, line in enumerate(
        chosen_lines
    ):
        line_y = (
            top
            + (
                chosen_line_height / 2
            )
            + (
                index
                * (
                    chosen_line_height
                    + line_spacing
                )
            )
        )
        _draw_rtl(
            draw,
            (
                xy[0],
                line_y,
            ),
            line,
            font=chosen_font,
            fill=fill,
            anchor="rm",
        )


def _render_business_card_front(
    *,
    request,
    quick_link,
    spec,
):
    canvas = _load_business_card_art(
        side="front",
        spec=spec,
    )
    draw = ImageDraw.Draw(canvas)

    data = _business_card_salon_data(
        request=request,
        salon=quick_link.salon,
    )

    left, top, right, bottom = (
        BUSINESS_CARD_FRONT_QR_BOX
    )
    box_width = right - left
    box_height = bottom - top

    qr = _qr_image(
        request=request,
        quick_link=quick_link,
        target_size=min(
            box_width,
            box_height,
        ),
    )
    qr = ImageOps.contain(
        qr,
        (
            box_width,
            box_height,
        ),
        Image.Resampling.NEAREST,
    )

    canvas.alpha_composite(
        qr,
        (
            left
            + (
                box_width - qr.width
            )
            // 2,
            top
            + (
                box_height - qr.height
            )
            // 2,
        ),
    )

    salon_name, salon_font = (
        _business_card_rtl_value(
            draw,
            value=data["salon_name"],
            max_width=375,
            start_size=40,
            minimum_size=21,
            weight="bold",
        )
    )

    if salon_name:
        _draw_rtl(
            draw,
            BUSINESS_CARD_FRONT_NAME_CENTER,
            salon_name,
            font=salon_font,
            fill=PURPLE_DARK,
            anchor="mm",
        )

    return canvas


def _render_business_card_back(
    *,
    request,
    quick_link,
    spec,
):
    canvas = _load_business_card_art(
        side="back",
        spec=spec,
    )
    draw = ImageDraw.Draw(canvas)

    data = _business_card_salon_data(
        request=request,
        salon=quick_link.salon,
    )

    rows = (
        (
            "rtl",
            data["salon_name"],
            19,
            12,
            "bold",
        ),
        (
            "ltr",
            data["website"],
            16,
            10,
            "regular",
        ),
        (
            "ltr",
            data["instagram"],
            16,
            10,
            "regular",
        ),
        (
            "ltr",
            data["phone"],
            17,
            11,
            "regular",
        ),
        (
            "rtl_wrapped",
            data["address"],
            15,
            10,
            "regular",
        ),
    )

    for row_y, row in zip(
        BUSINESS_CARD_BACK_ROW_CENTERS,
        rows,
    ):
        (
            direction,
            value,
            start_size,
            minimum_size,
            weight,
        ) = row

        if not value:
            continue

        if direction == "rtl":
            display_value, font = (
                _business_card_rtl_value(
                    draw,
                    value=value,
                    max_width=(
                        BUSINESS_CARD_BACK_VALUE_WIDTH
                    ),
                    start_size=start_size,
                    minimum_size=minimum_size,
                    weight=weight,
                )
            )
            _draw_rtl(
                draw,
                (
                    BUSINESS_CARD_BACK_VALUE_X,
                    row_y,
                ),
                display_value,
                font=font,
                fill=TEXT,
                anchor="rm",
            )
        elif direction == "rtl_wrapped":
            _draw_business_card_rtl_wrapped(
                draw,
                xy=(
                    BUSINESS_CARD_BACK_VALUE_X,
                    row_y,
                ),
                text=value,
                max_width=(
                    BUSINESS_CARD_BACK_VALUE_WIDTH
                ),
                max_height=48,
                max_lines=2,
                start_size=start_size,
                minimum_size=minimum_size,
                fill=TEXT,
                weight=weight,
                line_spacing=1,
            )
        else:
            _draw_ltr_fit(
                draw,
                xy=(
                    BUSINESS_CARD_BACK_LTR_X,
                    row_y,
                ),
                text=value,
                max_width=(
                    BUSINESS_CARD_BACK_VALUE_WIDTH
                ),
                start_size=start_size,
                minimum_size=minimum_size,
                fill=TEXT,
                anchor="lm",
            )

    return canvas


def _render_business_card(*, request, quick_link, spec):
    # Existing business_card URLs remain the front side.
    return _render_business_card_front(
        request=request,
        quick_link=quick_link,
        spec=spec,
    )


def _load_table_stand_art(spec):
    try:
        with Image.open(
            _resolve_static_path(
                PRINT_TEMPLATE_TABLE_STAND_ART
            )
        ) as source:
            image = source.convert("RGBA")
            dpi = source.info.get("dpi")
    except (OSError, ValueError) as exc:
        raise ImproperlyConfigured(
            "فایل هنری استند رومیزی "
            "قابل خواندن نیست."
        ) from exc

    if image.size != (
        spec.width,
        spec.height,
    ):
        raise ImproperlyConfigured(
            "ابعاد فایل هنری استند رومیزی "
            "با قرارداد چاپ سازگار نیست."
        )

    if (
        not dpi
        or not (
            295
            <= float(dpi[0])
            <= 305
        )
    ):
        raise ImproperlyConfigured(
            "فایل هنری استند رومیزی باید "
            "متادیتای ۳۰۰ DPI داشته باشد."
        )

    return image


def _table_stand_public_base_url(request):
    local_markers = (
        "127.0.0.1",
        "localhost",
        "0.0.0.0",
        "testserver",
    )

    for setting_name in (
        "PUBLIC_BASE_URL",
        "SITE_URL",
    ):
        candidate = str(
            getattr(
                settings,
                setting_name,
                "",
            )
            or ""
        ).strip()

        if (
            candidate
            and not any(
                marker in candidate.lower()
                for marker in local_markers
            )
        ):
            return candidate.rstrip("/")

    try:
        host = str(
            request.get_host()
        ).strip()
    except DisallowedHost:
        host = ""

    if (
        host
        and not any(
            marker in host.lower()
            for marker in local_markers
        )
    ):
        return (
            "https://"
            + host.rstrip("/")
        )

    return "https://loomera.ir"


class _TableStandPublicRequest:
    def __init__(self, source_request):
        self.source_request = source_request
        self.public_base_url = (
            _table_stand_public_base_url(
                source_request
            )
        )

    def build_absolute_uri(self, location=None):
        value = str(location or "/")

        if value.startswith(
            (
                "https://",
                "http://",
            )
        ):
            return value

        return (
            self.public_base_url.rstrip("/")
            + "/"
            + value.lstrip("/")
        )

    def __getattr__(self, name):
        return getattr(
            self.source_request,
            name,
        )


def _render_table_stand(
    *,
    request,
    quick_link,
    spec,
):
    canvas = _load_table_stand_art(spec)
    draw = ImageDraw.Draw(canvas)

    salon_name = str(
        getattr(
            quick_link.salon,
            "salon_name",
            "",
        )
        or ""
    ).strip()

    if salon_name:
        left, top, right, bottom = (
            TABLE_STAND_NAME_BOX
        )
        salon_font = _fit_font(
            draw,
            salon_name,
            max_width=(
                right - left - 90
            ),
            start_size=72,
            minimum_size=32,
            weight="black",
        )
        _draw_rtl(
            draw,
            (
                (left + right) / 2,
                (top + bottom) / 2,
            ),
            salon_name,
            font=salon_font,
            fill=PURPLE_DARK,
            anchor="mm",
        )

    left, top, right, bottom = (
        TABLE_STAND_QR_BOX
    )
    box_width = right - left
    box_height = bottom - top

    public_request = (
        _TableStandPublicRequest(
            request
        )
    )

    qr = _qr_image(
        request=public_request,
        quick_link=quick_link,
        target_size=min(
            box_width,
            box_height,
        ),
    )
    qr = ImageOps.contain(
        qr,
        (
            box_width,
            box_height,
        ),
        Image.Resampling.NEAREST,
    )

    canvas.alpha_composite(
        qr,
        (
            left
            + (
                box_width - qr.width
            )
            // 2,
            top
            + (
                box_height - qr.height
            )
            // 2,
        ),
    )

    return canvas


def _render_counter_card(*, request, quick_link, spec):
    canvas = Image.new(
        "RGBA",
        (spec.width, spec.height),
        WHITE,
    )
    draw = ImageDraw.Draw(canvas)

    draw.rounded_rectangle(
        (36, 36, spec.width - 36, spec.height - 36),
        radius=86,
        fill=PURPLE_SOFT,
        outline=(115, 92, 190, 80),
        width=5,
    )
    draw.rounded_rectangle(
        (36, 36, 660, spec.height - 36),
        radius=86,
        fill=PURPLE,
    )
    draw.rectangle(
        (560, 36, 660, spec.height - 36),
        fill=PURPLE,
    )
    draw.ellipse(
        (-160, 740, 410, 1310),
        fill=(167, 200, 161, 90),
    )

    qr = _qr_image(
        request=request,
        quick_link=quick_link,
        target_size=500,
    )
    _rounded_qr_card(
        canvas,
        qr,
        (105, 190, 590, 675),
        radius=60,
        padding=28,
    )

    _draw_rtl(
        draw,
        (348, 775),
        "برای رزرو اسکن کنید",
        font=_load_font("black", 43),
        fill=WHITE,
        anchor="ma",
    )
    draw.text(
        (348, 850),
        "loomera.ir",
        font=_load_font("bold", 31),
        fill=WHITE,
        anchor="mm",
    )

    logo = _load_asset(
        PRINT_TEMPLATE_LOGO,
        max_size=(390, 110),
    )
    canvas.alpha_composite(logo, (1260, 95))

    salon_name = getattr(
        quick_link.salon,
        "salon_name",
        "سالن زیبایی",
    )
    salon_font = _fit_font(
        draw,
        salon_name,
        max_width=920,
        start_size=82,
        minimum_size=46,
        weight="black",
    )
    _draw_rtl(
        draw,
        (1620, 330),
        salon_name,
        font=salon_font,
        fill=TEXT,
    )

    context = _context_label(quick_link)
    context_font = _fit_font(
        draw,
        context,
        max_width=900,
        start_size=50,
        minimum_size=31,
        weight="bold",
    )
    _draw_rtl(
        draw,
        (1620, 470),
        context,
        font=context_font,
        fill=PURPLE_DARK,
    )

    title = str(quick_link.title or "").strip()
    if title and title != context:
        title_font = _fit_font(
            draw,
            title,
            max_width=900,
            start_size=36,
            minimum_size=25,
            weight="regular",
        )
        _draw_rtl(
            draw,
            (1620, 570),
            title,
            font=title_font,
            fill=TEXT_MUTED,
        )

    draw.rounded_rectangle(
        (830, 760, 1605, 940),
        radius=60,
        fill=WHITE,
        outline=(115, 92, 190, 70),
        width=3,
    )
    _draw_rtl(
        draw,
        (1530, 850),
        "رزرو آنلاین، سریع و بدون تماس",
        font=_load_font("bold", 39),
        fill=TEXT,
        anchor="rm",
    )

    return canvas


_RENDERERS = {
    "mirror_label": _render_mirror_label,
    "business_card": _render_business_card,
    "table_stand": _render_table_stand,
    "counter_card": _render_counter_card,
}


def generate_booking_quick_link_print_template(
    *,
    request,
    quick_link: BookingQuickLink,
    template_key: str,
    preview: bool = False,
) -> GeneratedBookingQuickLinkPrintTemplate:
    if not quick_link or not getattr(quick_link, "pk", None):
        raise ValueError(
            "برای تولید قالب چاپی یک BookingQuickLink ذخیره‌شده لازم است."
        )

    missing = validate_booking_quick_link_print_template_dependencies()
    if missing:
        raise ImproperlyConfigured(
            "وابستگی‌های قالب چاپی کامل نیست: "
            + ", ".join(missing)
        )

    spec = get_booking_quick_link_print_template_spec(template_key)
    renderer = _RENDERERS[spec.key]
    image = renderer(
        request=request,
        quick_link=quick_link,
        spec=spec,
    )

    if image.size != (spec.width, spec.height):
        raise ImproperlyConfigured(
            "ابعاد خروجی قالب چاپی با قرارداد قالب سازگار نیست."
        )

    dpi = PRINT_TEMPLATE_DPI

    if preview:
        image.thumbnail(
            (
                PRINT_TEMPLATE_PREVIEW_MAX_PIXELS,
                PRINT_TEMPLATE_PREVIEW_MAX_PIXELS,
            ),
            Image.Resampling.LANCZOS,
        )
        dpi = 144

    output = BytesIO()
    save_image = (
        image
        if spec.transparent
        else image.convert("RGB")
    )
    save_image.save(
        output,
        format="PNG",
        optimize=True,
        dpi=(dpi, dpi),
    )
    content = output.getvalue()

    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ImproperlyConfigured(
            "خروجی قالب چاپی یک فایل PNG معتبر نیست."
        )

    return GeneratedBookingQuickLinkPrintTemplate(
        content=content,
        filename=_filename(quick_link, spec),
        content_type=PRINT_TEMPLATE_CONTENT_TYPE,
        width=image.width,
        height=image.height,
        dpi=dpi,
        template=spec,
        is_preview=bool(preview),
    )


@dataclass(frozen=True)
class GeneratedBookingQuickLinkBusinessCardBundle:
    content: bytes
    filename: str
    content_type: str = "application/zip"


def _business_card_filename(quick_link, *, side):
    salon_part = _safe_filename_part(
        getattr(quick_link.salon, "salon_name", ""),
        fallback=f"salon-{quick_link.salon_id}",
    )
    return (
        f"loomera-{salon_part}-business-card-"
        f"{side}-link-{quick_link.pk}.png"
    )


def _encode_business_card_image(image, *, preview):
    dpi = PRINT_TEMPLATE_DPI

    if preview:
        image.thumbnail(
            (
                PRINT_TEMPLATE_PREVIEW_MAX_PIXELS,
                PRINT_TEMPLATE_PREVIEW_MAX_PIXELS,
            ),
            Image.Resampling.LANCZOS,
        )
        dpi = 144

    output = BytesIO()
    image.convert("RGB").save(
        output,
        format="PNG",
        optimize=True,
        dpi=(dpi, dpi),
    )
    content = output.getvalue()

    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ImproperlyConfigured(
            "خروجی کارت ویزیت PNG معتبر نیست."
        )

    return content, dpi


def generate_booking_quick_link_business_card_side(
    *,
    request,
    quick_link,
    side,
    preview=False,
):
    if side not in {"front", "back"}:
        raise ValueError("سمت کارت ویزیت معتبر نیست.")

    spec = get_booking_quick_link_print_template_spec("business_card")
    renderer = {
        "front": _render_business_card_front,
        "back": _render_business_card_back,
    }[side]
    image = renderer(
        request=request,
        quick_link=quick_link,
        spec=spec,
    )

    if image.size != (spec.width, spec.height):
        raise ImproperlyConfigured(
            "ابعاد خروجی کارت ویزیت معتبر نیست."
        )

    content, dpi = _encode_business_card_image(
        image,
        preview=preview,
    )

    return GeneratedBookingQuickLinkPrintTemplate(
        content=content,
        filename=_business_card_filename(quick_link, side=side),
        content_type=PRINT_TEMPLATE_CONTENT_TYPE,
        width=image.width,
        height=image.height,
        dpi=dpi,
        template=spec,
        is_preview=bool(preview),
    )


def generate_booking_quick_link_business_card_zip(
    *,
    request,
    quick_link,
):
    front = generate_booking_quick_link_business_card_side(
        request=request,
        quick_link=quick_link,
        side="front",
        preview=False,
    )
    back = generate_booking_quick_link_business_card_side(
        request=request,
        quick_link=quick_link,
        side="back",
        preview=False,
    )

    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(front.filename, front.content)
        archive.writestr(back.filename, back.content)

    salon_part = _safe_filename_part(
        getattr(quick_link.salon, "salon_name", ""),
        fallback=f"salon-{quick_link.salon_id}",
    )

    return GeneratedBookingQuickLinkBusinessCardBundle(
        content=output.getvalue(),
        filename=(
            f"loomera-{salon_part}-business-card-"
            f"link-{quick_link.pk}.zip"
        ),
    )
