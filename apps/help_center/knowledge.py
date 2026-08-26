from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class HelpArticle:
    key: str
    slug: str
    title: str
    role: str
    category: str
    summary: str
    steps: tuple[tuple[str, str], ...]
    keywords: tuple[str, ...] = ()
    tips: tuple[str, ...] = ()

    @property
    def searchable_text(self) -> str:
        chunks = [
            self.title,
            self.summary,
            self.role,
            self.category,
            " ".join(self.keywords),
        ]
        for title, body in self.steps:
            chunks.extend([title, body])
        chunks.extend(self.tips)
        return " ".join(chunks)


CATEGORIES = {
    "getting-started": {
        "title": "شروع کار",
        "icon": "fa-solid fa-rocket",
        "description": "راهنمای قدم‌های اول و شناخت مسیرهای اصلی لومرا.",
    },
    "manager": {
        "title": "مدیر مجموعه",
        "icon": "fa-solid fa-store",
        "description": "مدیریت تیم، خدمات، نوبت‌ها، رزرو آنلاین و امور مالی.",
    },
    "stylist": {
        "title": "متخصص",
        "icon": "fa-solid fa-user-check",
        "description": "برنامه کاری، نوبت‌ها، پروفایل حرفه‌ای و مالی متخصص.",
    },
    "customer": {
        "title": "مشتری",
        "icon": "fa-regular fa-user",
        "description": "جستجو، رزرو، پرداخت، حساب و پیگیری نوبت‌ها.",
    },
    "booking": {
        "title": "رزرو و نوبت",
        "icon": "fa-regular fa-calendar-check",
        "description": "مراحل رزرو، انتخاب متخصص، زمان‌بندی و تغییر نوبت.",
    },
    "payments": {
        "title": "پرداخت و کیف پول",
        "icon": "fa-solid fa-wallet",
        "description": "پرداخت نوبت، کیف پول، تراکنش‌ها و برداشت.",
    },
    "account": {
        "title": "حساب و امنیت",
        "icon": "fa-solid fa-shield-halved",
        "description": "پروفایل، آدرس‌ها، رمز عبور و تنظیمات ارتباطی.",
    },
}


def _a(
    key,
    slug,
    title,
    role,
    category,
    summary,
    steps,
    keywords=(),
    tips=(),
):
    return HelpArticle(
        key=key,
        slug=slug,
        title=title,
        role=role,
        category=category,
        summary=summary,
        steps=tuple(tuple(item) for item in steps),
        keywords=tuple(keywords),
        tips=tuple(tips),
    )


ARTICLES = (
    _a(
        "manager.home",
        "manager-dashboard",
        "خانه داشبورد مدیر",
        "manager",
        "manager",
        "خانه داشبورد برای مرور سریع وضعیت امروز مجموعه است؛ موارد نیازمند اقدام، نوبت‌های نزدیک و وضعیت راه‌اندازی را از اینجا بررسی کن.",
        (
            ("اقدام مهم امروز را پیدا کن", "اول کارت‌ها یا هشدارهای بالای صفحه را ببین و کار ناقص یا فوری را جلو ببر."),
            ("نوبت‌های امروز را مرور کن", "رزروهای نزدیک و موارد منتظر را بررسی کن تا چیزی از قلم نیفتد."),
            ("برای ویرایش وارد بخش تخصصی شو", "خانه داشبورد خلاصه است؛ تغییر تیم، خدمات یا مالی را در صفحه همان بخش انجام بده."),
        ),
        ("داشبورد مدیر", "خانه مدیر", "امروز", "اقدام بعدی"),
    ),
    _a(
        "manager.team",
        "manager-team",
        "مدیریت تیم مجموعه",
        "manager",
        "manager",
        "در صفحه تیم اعضا، دعوت‌ها و درخواست‌های همکاری را مدیریت می‌کنی و بعد خدمات و برنامه کاری هر متخصص را تکمیل می‌کنی.",
        (
            ("عضو جدید را اضافه کن", "برای همکاری جدید از افزودن عضو یا دعوت متخصص شروع کن."),
            ("درخواست‌ها و دعوت‌ها را تعیین تکلیف کن", "موارد باز را معطل نگذار تا وضعیت همکاری شفاف بماند."),
            ("خدمات متخصص را کامل کن", "متخصص فعال باید حداقل یک خدمت واقعی برای ارائه داشته باشد."),
            ("برنامه کاری را ثبت کن", "شیفت و عدم حضور روی زمان‌های قابل رزرو مشتری اثر مستقیم دارند."),
        ),
        ("تیم", "متخصص", "دعوت", "همکاری", "عضو", "شیفت"),
        ("اگر متخصص اضافه شده ولی قابل رزرو نیست، اول خدمت و سپس برنامه کاری او را بررسی کن.",),
    ),
    _a(
        "manager.services",
        "manager-services",
        "مدیریت خدمات مجموعه",
        "manager",
        "manager",
        "خدمات قابل رزرو مجموعه، قیمت، مدت و اتصال آن‌ها به متخصص‌ها در این بخش مدیریت می‌شوند.",
        (
            ("خدمت درست را انتخاب یا اضافه کن", "نام خدمت باید با چیزی که مشتری رزرو می‌کند هم‌خوان باشد."),
            ("قیمت و مدت واقعی ثبت کن", "مدت غیرواقعی باعث تداخل برنامه و تجربه نامناسب رزرو می‌شود."),
            ("متخصص ارائه‌دهنده را بررسی کن", "خدمت بدون متخصص فعال و برنامه کاری معتبر قابل رزرو نخواهد بود."),
        ),
        ("خدمت", "سرویس", "قیمت", "مدت", "متخصص", "service"),
    ),
    _a(
        "manager.schedule",
        "manager-team-schedule",
        "برنامه کاری تیم",
        "manager",
        "manager",
        "شیفت‌های تیم و زمان‌های عدم حضور مبنای تولید زمان‌های قابل رزرو هستند.",
        (
            ("شیفت‌های عادی را مرور کن", "روز و ساعت حضور هر متخصص باید با برنامه واقعی مجموعه هماهنگ باشد."),
            ("استثناها را جدا ثبت کن", "برای مرخصی یا غیبت موقت از عدم حضور استفاده کن، نه تغییر دائمی شیفت ثابت."),
            ("تداخل نوبت‌ها را بررسی کن", "قبل از تغییر مهم برنامه، رزروهای موجود آن بازه را در نظر بگیر."),
        ),
        ("شیفت", "برنامه کاری", "مرخصی", "عدم حضور", "schedule"),
    ),
    _a(
        "manager.appointments",
        "manager-appointments",
        "نوبت‌ها و تقویم مدیر",
        "manager",
        "manager",
        "نوبت‌های مجموعه را بر اساس زمان، متخصص و وضعیت پیگیری کن و قبل از هر تغییر جزئیات رزرو را ببین.",
        (
            ("نوبت نزدیک را پیدا کن", "موارد امروز و رزروهای نیازمند اقدام را در اولویت قرار بده."),
            ("جزئیات را قبل از تغییر بررسی کن", "مشتری، خدمت، متخصص، زمان و وضعیت پرداخت را ببین."),
            ("وضعیت را مطابق اتفاق واقعی تغییر بده", "تأیید، لغو یا تکمیل باید با وضعیت واقعی مراجعه هماهنگ باشد."),
        ),
        ("نوبت", "تقویم", "رزرو", "لغو", "appointment", "calendar"),
    ),
    _a(
        "manager.online_booking",
        "manager-online-booking",
        "رزرو آنلاین مجموعه",
        "manager",
        "manager",
        "برای دریافت رزرو آنلاین باید خدمت، متخصص و برنامه کاری همگی آماده باشند.",
        (
            ("آمادگی خدمات را بررسی کن", "خدمات فعال باید قیمت و مدت معتبر داشته باشند."),
            ("تیم و شیفت‌ها را کامل کن", "بدون متخصص و برنامه کاری، زمان قابل رزرو ساخته نمی‌شود."),
            ("مسیر مشتری را تست کن", "بعد از تغییر مهم یک رزرو آزمایشی از سمت مشتری انجام بده."),
        ),
        ("رزرو آنلاین", "لینک رزرو", "زمان خالی", "online booking"),
    ),
    _a(
        "manager.finance",
        "manager-finance",
        "مالی مجموعه",
        "manager",
        "manager",
        "در بخش مالی درآمد، هزینه، برداشت، تخفیف‌ها و گزارش‌های مجموعه را کنترل می‌کنی.",
        (
            ("اول موضوع مالی را مشخص کن", "برای برداشت، هزینه، تخفیف یا گزارش وارد زیرصفحه مرتبط شو."),
            ("اعداد را با داده مرجع تطبیق بده", "برای مبلغ نامعمول به تراکنش یا نوبت مرتبط برگرد."),
            ("قبل از عملیات مالی نهایی دوباره بررسی کن", "مبلغ و مقصد تسویه یا برداشت باید دقیق باشند."),
        ),
        ("مالی", "درآمد", "برداشت", "تسویه", "سود", "تخفیف"),
    ),
    _a(
        "stylist.home",
        "stylist-dashboard",
        "داشبورد متخصص",
        "stylist",
        "stylist",
        "داشبورد متخصص برای مرور نوبت‌های امروز، برنامه کاری و وضعیت کلی فعالیت حرفه‌ای است.",
        (
            ("نوبت نزدیک را ببین", "زمان و خدمت مراجعه بعدی را قبل از شروع کار بررسی کن."),
            ("برنامه کاری را به‌روز نگه دار", "شیفت و عدم حضور روی زمان‌های قابل رزرو اثر مستقیم دارند."),
            ("پروفایل حرفه‌ای را کامل کن", "اطلاعات واضح‌تر به انتخاب بهتر مشتری کمک می‌کند."),
        ),
        ("داشبورد متخصص", "نوبت امروز", "متخصص"),
    ),
    _a(
        "stylist.schedule",
        "stylist-schedule",
        "برنامه کاری متخصص",
        "stylist",
        "stylist",
        "زمان‌های کاری و عدم حضور را دقیق ثبت کن تا مشتری فقط در زمان‌هایی که واقعاً در دسترس هستی رزرو انجام دهد.",
        (
            ("شیفت‌های عادی را کامل کن", "روز و ساعت حضور باید با برنامه واقعی تو هماهنگ باشد."),
            ("عدم حضور را برای استثناها ثبت کن", "مرخصی یا غیبت را بدون تغییر الگوی دائمی شیفت مسدود کن."),
            ("بعد از تغییر برنامه را مرور کن", "مطمئن شو زمان‌های قابل رزرو طبق انتظار تغییر کرده‌اند."),
        ),
        ("شیفت متخصص", "مرخصی", "عدم حضور", "schedule"),
    ),
    _a(
        "stylist.appointments",
        "stylist-appointments",
        "نوبت‌های متخصص",
        "stylist",
        "stylist",
        "نوبت‌های آینده و گذشته را مرور کن و برای هر مراجعه جزئیات مشتری، خدمت و وضعیت را ببین.",
        (
            ("موارد نزدیک را اول بررسی کن", "برای روز کاری روی نوبت‌های آینده نزدیک تمرکز کن."),
            ("قبل از خدمت جزئیات را ببین", "زمان، خدمت و اطلاعات ضروری مراجعه را مرور کن."),
            ("وضعیت نوبت را به‌موقع ثبت کن", "تغییر وضعیت باید با اتفاق واقعی مراجعه هماهنگ باشد."),
        ),
        ("نوبت متخصص", "رزرو", "مراجعه"),
    ),
    _a(
        "customer.account",
        "customer-account",
        "حساب من",
        "customer",
        "customer",
        "از حساب من به رزروها، کیف پول، آدرس‌ها و تنظیمات شخصی دسترسی داری.",
        (
            ("رزروهای آینده را پیگیری کن", "برای پرداخت، لغو یا تغییر زمان وارد همان نوبت شو."),
            ("اطلاعات شخصی را به‌روز نگه دار", "شماره تماس و آدرس صحیح فرایندهای بعدی را ساده‌تر می‌کنند."),
            ("برای تنظیمات بیشتر وارد تنظیمات حساب شو", "امنیت و اعلان‌ها در بخش تنظیمات مدیریت می‌شوند."),
        ),
        ("حساب من", "پروفایل", "تنظیمات مشتری"),
    ),
    _a(
        "customer.addresses",
        "customer-addresses",
        "آدرس‌های من",
        "customer",
        "account",
        "آدرس‌های ذخیره‌شده را مدیریت کن و یک آدرس پیش‌فرض داشته باش تا انتخاب‌های بعدی سریع‌تر شوند.",
        (
            ("نشانی را دقیق ثبت کن", "شهر، متن آدرس، پلاک و واحد را در صورت نیاز کامل بنویس."),
            ("آدرس اصلی را پیش‌فرض کن", "آدرس پیش‌فرض سریع‌تر در دسترس خواهد بود."),
            ("آدرس قدیمی را اصلاح یا حذف کن", "لیست کوتاه و به‌روز احتمال انتخاب اشتباه را کم می‌کند."),
        ),
        ("آدرس", "نشانی", "پلاک", "کد پستی", "پیش فرض"),
    ),
    _a(
        "customer.communications",
        "customer-communications",
        "اعلان‌ها و ارتباطات",
        "customer",
        "account",
        "انتخاب کن پیام‌های نوبت و پیام‌های اختیاری از چه کانال‌هایی دریافت شوند.",
        (
            ("پیام‌های نوبت را تنظیم کن", "حداقل کانالی را فعال کن که مرتب آن را بررسی می‌کنی."),
            ("پیام‌های اختیاری را جدا مدیریت کن", "خبرها و پیشنهادها مستقل از پیام‌های ضروری هستند."),
            ("اتصال پیام‌رسان را بررسی کن", "فعال‌کردن سوییچ بدون اتصال حساب پیام‌رسان کافی نیست."),
        ),
        ("اعلان", "پیامک", "ایمیل", "بله", "ارتباطات"),
    ),
    _a(
        "booking.start",
        "booking-start",
        "شروع رزرو",
        "customer",
        "booking",
        "برای رزرو ابتدا خدمت یا مجموعه مناسب را انتخاب کن و سپس متخصص و زمان را مشخص کن.",
        (
            ("خدمت درست را انتخاب کن", "انتخاب خدمت روی متخصص‌ها و زمان‌های مرحله بعد اثر دارد."),
            ("متخصص مناسب را انتخاب کن", "اگر ترجیح خاصی نداری گزینه‌ای را انتخاب کن که زمان مناسب دارد."),
            ("تاریخ و ساعت را نهایی کن", "مدت خدمت را هم در برنامه روز خود در نظر بگیر."),
        ),
        ("رزرو", "انتخاب خدمت", "متخصص", "تاریخ", "ساعت"),
    ),
    _a(
        "booking.datetime",
        "booking-date-time",
        "انتخاب تاریخ و ساعت",
        "customer",
        "booking",
        "زمان‌های قابل انتخاب بر اساس خدمت، متخصص و برنامه کاری ساخته می‌شوند.",
        (
            ("روز دارای ظرفیت را انتخاب کن", "روزهایی که زمان خالی ندارند قابل انتخاب نخواهند بود."),
            ("ساعت را با برنامه خودت تطبیق بده", "مدت خدمت را هم در نظر بگیر."),
            ("اگر زمان مناسب نیست انتخاب قبلی را تغییر بده", "متخصص دیگر ممکن است ظرفیت متفاوتی داشته باشد."),
        ),
        ("تاریخ", "ساعت", "زمان خالی", "رزرو"),
    ),
    _a(
        "booking.preview",
        "booking-preview",
        "بررسی رزرو قبل از تأیید",
        "customer",
        "booking",
        "قبل از ثبت نهایی، مجموعه، خدمت، متخصص، زمان و مبلغ رزرو را یک‌بار کامل مرور کن.",
        (
            ("مجموعه و متخصص را تأیید کن", "مطمئن شو مقصد مراجعه و فرد ارائه‌دهنده درست هستند."),
            ("خدمت و زمان را دوباره ببین", "این آخرین نقطه مناسب برای اصلاح انتخاب‌هاست."),
            ("مبلغ نهایی را بررسی کن", "تخفیف، اعتبار یا روش پرداخت را قبل از ادامه ببین."),
        ),
        ("پیش نمایش رزرو", "تأیید رزرو", "مبلغ"),
    ),
    _a(
        "customer.appointments",
        "customer-appointments",
        "نوبت‌های من",
        "customer",
        "booking",
        "رزروهای آینده و گذشته را پیگیری کن و برای هر اقدام وارد جزئیات همان نوبت شو.",
        (
            ("نوبت آینده را پیدا کن", "زمان، مجموعه و متخصص مراجعه نزدیک را بررسی کن."),
            ("برای تغییر یا پرداخت وارد جزئیات شو", "اقدامات متناسب با وضعیت نوبت همان‌جا نمایش داده می‌شوند."),
            ("سوابق گذشته را مرور کن", "نوبت‌های انجام‌شده و لغوشده در تاریخچه باقی می‌مانند."),
        ),
        ("نوبت من", "رزروهای من", "لغو", "تغییر زمان"),
    ),
    _a(
        "payments.wallet",
        "wallet",
        "کیف پول",
        "customer",
        "payments",
        "موجودی، تراکنش‌ها، شارژ و برداشت کیف پول را از این بخش مدیریت کن.",
        (
            ("موجودی فعلی را ببین", "قبل از عملیات مالی عدد قابل استفاده را بررسی کن."),
            ("برای جزئیات وارد تراکنش‌ها شو", "ورود و خروج وجه با تاریخ و نوع تراکنش نمایش داده می‌شود."),
            ("عملیات مالی را با مبلغ دقیق انجام بده", "قبل از تأیید تعداد صفرها و مبلغ را دوباره بررسی کن."),
        ),
        ("کیف پول", "شارژ", "تراکنش", "برداشت"),
    ),
    _a(
        "payments.result",
        "payment-result",
        "نتیجه پرداخت",
        "customer",
        "payments",
        "پس از بازگشت از درگاه ابتدا وضعیت نهایی پرداخت و سپس وضعیت رزرو را بررسی کن.",
        (
            ("پیام نتیجه را بخوان", "مشخص کن پرداخت موفق، ناموفق یا نیازمند بررسی است."),
            ("وضعیت رزرو را هم کنترل کن", "پرداخت و رزرو باید با هم هماهنگ باشند."),
            ("قبل از پرداخت دوباره بررسی کن", "اگر نتیجه مبهم است اول مطمئن شو مبلغ قبلی کسر نشده است."),
        ),
        ("پرداخت موفق", "پرداخت ناموفق", "درگاه"),
    ),
    _a(
        "public.services",
        "services",
        "خدمات زیبایی",
        "all",
        "getting-started",
        "گروه و زیرگروه خدمت را انتخاب کن، سپس خدمت مناسب و مجموعه‌های ارائه‌دهنده را مقایسه کن.",
        (
            ("گروه اصلی را انتخاب کن", "انتخاب دسته، فهرست خدمات را محدود می‌کند."),
            ("در صورت نیاز زیرگروه را مشخص کن", "برای رسیدن سریع‌تر به خدمت دقیق‌تر استفاده کن."),
            ("مجموعه‌ها و قیمت‌ها را مقایسه کن", "از کارت خدمت به گزینه‌های ارائه‌دهنده برو."),
        ),
        ("خدمات", "گروه خدمت", "قیمت متخصص"),
    ),
    _a(
        "public.search",
        "search",
        "جستجو در لومرا",
        "all",
        "getting-started",
        "برای پیدا کردن مجموعه، خدمت یا متخصص، عبارت مشخص وارد کن و در صورت نیاز فیلترها را محدود کن.",
        (
            ("موضوع جستجو را مشخص کن", "نام خدمت یا مجموعه نتیجه دقیق‌تری می‌دهد."),
            ("فیلترها را فقط در صورت نیاز اعمال کن", "فیلتر زیاد ممکن است گزینه‌های مناسب را پنهان کند."),
            ("قبل از رزرو صفحه گزینه را باز کن", "جزئیات را ببین و بعد وارد مسیر رزرو شو."),
        ),
        ("جستجو", "پیدا کردن سالن", "پیدا کردن متخصص"),
    ),
)

ARTICLE_BY_KEY = {article.key: article for article in ARTICLES}
ARTICLE_BY_SLUG = {article.slug: article for article in ARTICLES}


# Route rules are intentionally server-side so the JS widget does not carry product docs.
ROUTE_RULES = (
    # Manager
    (re.compile(r"^/dashboards/team_member/?$"), "manager.team"),
    (re.compile(r"^/dashboards/(add_stylist|edit_stylist|stylist_overview)"), "manager.team"),
    (re.compile(r"^/dashboards/(scheduled_shifts|schedule/)"), "manager.schedule"),
    (re.compile(r"^/dashboards/(service_menu|add_service|edit_service|catalog|request_service)"), "manager.services"),
    (re.compile(r"^/dashboards/(calendar/|reports/)"), "manager.appointments"),
    (re.compile(r"^/dashboards/online_booking"), "manager.online_booking"),
    (re.compile(r"^/dashboards/settings/finance"), "manager.finance"),
    # Stylist
    (re.compile(r"^/dashboards/stylist/schedule"), "stylist.schedule"),
    (re.compile(r"^/dashboards/stylist/time-off"), "stylist.schedule"),
    (re.compile(r"^/dashboards/stylist/appointments"), "stylist.appointments"),
    (re.compile(r"^/dashboards/stylist/?$"), "stylist.home"),
    # Customer/account
    (re.compile(r"^/accounts/addresses"), "customer.addresses"),
    (re.compile(r"^/accounts/communications"), "customer.communications"),
    (re.compile(r"^/accounts/customer"), "customer.account"),
    # Booking
    (re.compile(r"^/orders/select_dateTime"), "booking.datetime"),
    (re.compile(r"^/orders/reservation_preview"), "booking.preview"),
    (re.compile(r"^/orders/(select_stylists|quick-link/)"), "booking.start"),
    (re.compile(r"^/orders/(appointments|appointment_detail|a/)"), "customer.appointments"),
    # Payments
    (re.compile(r"^/payments/appointment/result"), "payments.result"),
    (re.compile(r"^/payments/"), "payments.wallet"),
    # Public
    (re.compile(r"^/services/"), "public.services"),
    (re.compile(r"^/search/"), "public.search"),
)


def resolve_page_key(path: str, role: str = "") -> str:
    path = (path or "/").split("?", 1)[0]
    for pattern, key in ROUTE_RULES:
        if pattern.search(path):
            return key

    role = (role or "").strip().lower()
    if role == "manager":
        return "manager.home"
    if role == "stylist":
        return "stylist.home"
    if role == "customer":
        return "customer.account"
    return "public.services"


def normalize_text(value: str) -> str:
    value = (value or "").lower()
    value = value.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    value = re.sub(r"[^\w\u0600-\u06ff]+", " ", value)
    return " ".join(value.split())


def tokenize(value: str) -> set[str]:
    stop = {
        "را", "به", "از", "در", "با", "برای", "که", "این", "آن", "من", "چطور",
        "چگونه", "یک", "و", "یا", "روی", "میخوام", "میخواهم", "می", "کنم",
    }
    return {
        token
        for token in normalize_text(value).split()
        if len(token) > 1 and token not in stop
    }


def score_article(query: str, article: HelpArticle, page_key: str = "") -> float:
    q = normalize_text(query)
    q_tokens = tokenize(query)
    text = normalize_text(article.searchable_text)
    text_tokens = tokenize(text)

    score = 0.0
    if article.key == page_key:
        score += 8.0
    if q and q in text:
        score += 8.0

    overlap = q_tokens & text_tokens
    score += len(overlap) * 2.3

    title = normalize_text(article.title)
    for token in q_tokens:
        if token in title:
            score += 1.5
        if token in normalize_text(" ".join(article.keywords)):
            score += 1.2

    return score


def search_articles(
    query: str,
    *,
    page_key: str = "",
    role: str = "",
    limit: int = 5,
) -> list[HelpArticle]:
    role = (role or "").strip().lower()
    candidates: Iterable[HelpArticle] = ARTICLES
    if role in {"customer", "manager", "stylist"}:
        candidates = [a for a in ARTICLES if a.role in {"all", role}]

    ranked = sorted(
        ((score_article(query, article, page_key), article) for article in candidates),
        key=lambda item: item[0],
        reverse=True,
    )
    useful = [article for score, article in ranked if score > 0]
    if not useful and page_key in ARTICLE_BY_KEY:
        useful = [ARTICLE_BY_KEY[page_key]]
    return useful[:limit]
