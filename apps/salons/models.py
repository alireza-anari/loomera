from datetime import datetime

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.gis.db import models as gis_models
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from middlewares.middlewares import RequestMiddleware
from utils import File_Uploader

from apps.accounts.models import Customer, CustomUser
from apps.locations.models import Neighborhood
from apps.services.models import Services


def _unique_slug_for_model(instance, source_value, field_name="slug", max_length=170):
    base_slug = slugify(source_value or "salon", allow_unicode=True).strip("-") or "salon"
    base_slug = base_slug[:max_length].strip("-") or "salon"
    slug = base_slug
    counter = 2
    model = instance.__class__
    while model.objects.filter(**{field_name: slug}).exclude(pk=instance.pk).exists():
        suffix = f"-{counter}"
        slug = f"{base_slug[: max_length - len(suffix)]}{suffix}"
        counter += 1
    return slug


# --------------------------------------------------------------------
# Salon verification choices
class SalonVerificationStatus(models.TextChoices):
    UNVERIFIED = "unverified", "تأیید نشده"
    PROFILE_INCOMPLETE = "profile_incomplete", "پروفایل ناقص"
    DOCUMENTS_PENDING = "documents_pending", "در انتظار ارسال مدارک"
    UNDER_REVIEW = "under_review", "در حال بررسی"
    VERIFIED = "verified", "تأیید شده"
    REJECTED = "rejected", "رد شده"
    SUSPENDED = "suspended", "تعلیق شده"
    EXPIRED = "expired", "نیازمند تمدید مدارک"


# --------------------------------------------------------------------
# Salon
class Salon(models.Model):
    salon_name = models.CharField(max_length=50, verbose_name="نام سالن")
    slug = models.SlugField(
        max_length=180,
        unique=True,
        allow_unicode=True,
        blank=True,
        verbose_name="اسلاگ سئویی",
        help_text="برای URL پایدار و قابل اشتراک سالن استفاده می‌شود.",
    )
    seo_title = models.CharField(max_length=160, blank=True, default="", verbose_name="عنوان SEO")
    seo_description = models.CharField(max_length=220, blank=True, default="", verbose_name="توضیحات SEO")
    canonical_url = models.URLField(blank=True, default="", verbose_name="Canonical URL")
    allow_indexing = models.BooleanField(default=True, verbose_name="اجازه ایندکس SEO")
    og_image = models.ImageField(
        upload_to="images/salons/og/",
        blank=True,
        null=True,
        verbose_name="تصویر Open Graph",
    )
    file_upload = File_Uploader("images", "salons_banner")
    banner_image = models.ImageField(
        upload_to=file_upload,
        default="salons_banner.jpg",
        verbose_name="بنر",
        null=True,
        blank=True,
    )
    description = models.TextField(blank=True, verbose_name="توضیحات ")
    video = models.FileField(
        upload_to=file_upload, blank=True, null=True, verbose_name="ویدیو"
    )
    zone = models.PositiveIntegerField(verbose_name="منطقه ", null=True, blank=True)
    location = gis_models.PointField(geography=True, verbose_name="موقعیت جغرافیایی", null=True)
    neighborhood = models.ForeignKey(
        Neighborhood,
        on_delete=models.CASCADE,
        verbose_name="محله",
        null=True,
        related_name="salon_neighborhood",
    )
    address = models.TextField(verbose_name="آدرس", blank=True, null=True)
    linkedin_link = models.CharField(
        max_length=200, null=True, blank=True, verbose_name="لینک لینکدین"
    )
    insta_link = models.CharField(
        max_length=200, null=True, blank=True, verbose_name="لینک اینستا"
    )
    telegram_link = models.CharField(
        max_length=200, null=True, blank=True, verbose_name="لینک تلگرام "
    )
    salon_manager = models.ForeignKey(
        "accounts.SalonManager",
        on_delete=models.CASCADE,
        verbose_name="مدیر سالن ",
        related_name="salon_manager",
    )
    services = models.ManyToManyField(
        Services, verbose_name="خدمات ", related_name="services_of_salon"
    )
    stylists = models.ManyToManyField(
        "accounts.Stylist", verbose_name="آرایشگر", related_name="stylists_of_salon"
    )
    is_active = models.BooleanField(default=False, verbose_name="وضعیت ")
    verification_status = models.CharField(
        max_length=64,
        choices=SalonVerificationStatus.choices,
        default=SalonVerificationStatus.UNVERIFIED,
        db_index=True,
        verbose_name="وضعیت احراز سالن",
    )
    registere_date = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")
    phone_number = models.CharField(max_length=32, verbose_name="شماره تلفن ", null=True, blank=True)
    payout_iban = models.CharField(
        max_length=26,
        blank=True,
        default="",
        verbose_name="شماره شبا برای تسویه",
    )
    payout_account_holder_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="نام صاحب حساب برای تسویه",
    )
    payout_bank_name = models.CharField(
        max_length=80,
        blank=True,
        default="",
        verbose_name="نام بانک",
    )
    payout_contact_mobile = models.CharField(
        max_length=11,
        blank=True,
        default="",
        verbose_name="شماره موبایل مسئول تسویه",
    )
    cancellation_window_hours = models.PositiveSmallIntegerField(
        default=24,
        verbose_name="مهلت لغو آنلاین (ساعت)",
    )
    cancellation_refund_percent = models.PositiveSmallIntegerField(
        default=100,
        verbose_name="درصد بازگشت وجه به کیف پول",
    )
    cancellation_policy_note = models.TextField(
        blank=True,
        default="",
        verbose_name="توضیحات سیاست لغو",
    )
    payout_delay_days = models.PositiveSmallIntegerField(
        default=2,
        verbose_name="تاخیر تسویه به سالن (روز)",
    )

    @property
    def payout_profile_complete(self):
        return bool(
            (self.payout_iban or "").strip()
            and (self.payout_account_holder_name or "").strip()
            and (self.payout_contact_mobile or "").strip()
        )

    @property
    def cancellation_policy_summary(self):
        hours = int(self.cancellation_window_hours or 0)
        refund_percent = int(self.cancellation_refund_percent or 0)
        return f"لغو تا {hours} ساعت قبل با بازگشت {refund_percent}٪ به کیف پول"

    @property
    def effective_seo_title(self):
        if self.seo_title:
            return self.seo_title
        location_label = self.neighborhood.name if self.neighborhood_id else (f"منطقه {self.zone}" if self.zone else "")
        suffix = f" در {location_label}" if location_label else ""
        return f"{self.salon_name} | رزرو آنلاین خدمات زیبایی{suffix}"

    @property
    def effective_seo_description(self):
        if self.seo_description:
            return self.seo_description
        service_names = ", ".join(self.services.filter(is_active=True).values_list("service_name", flat=True)[:4])
        service_part = f" خدمات {service_names}" if service_names else " خدمات زیبایی"
        return f"رزرو آنلاین{service_part} در {self.salon_name}، مشاهده قیمت، نمونه‌کارها، نظرات مشتریان و زمان‌های آزاد در Loomera."[:220]

    def get_absolute_url(self):
        return reverse("salons:detail_salon_slug", kwargs={"salon_slug": self.slug})

    def get_legacy_absolute_url(self):
        return reverse("salons:detail_salon", kwargs={"salon_id": self.pk})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug_for_model(self, self.salon_name, max_length=170)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.salon_name}"

    def get_user_score(self):
        request = RequestMiddleware(get_response=None)
        request = request.thread_local.current_request
        score = 0
        user_score = self.scoring_salon.filter(scoring_user=request.user)
        if user_score.count() > 0:
            score = user_score[0].score
        return score

    def get_average_score(self):
        from apps.comments_scores_favories.models import Comments

        # دریافت نظرات تایید شده مرتبط با این سالن
        approved_comments = Comments.objects.filter(salon=self, is_active=True)
        approved_scores = []
        for comment in approved_comments:
            # چک می‌کنیم که اگر نظر دارای رابطه scoring است و امتیاز مقداردهی شده باشد
            if (
                hasattr(comment, "scoring")
                and comment.scoring
                and comment.scoring.score is not None
            ):
                approved_scores.append(comment.scoring.score)
        if approved_scores:
            return round(sum(approved_scores) / len(approved_scores), 1)
        return None

    def get_user_favorite(self):
        request = RequestMiddleware(get_response=None)
        request = request.thread_local.current_request
        flag = self.favorite_salon.filter(favorite_user__user=request.user,).exists()
        return flag

    def get_salon_age(self):
        # بررسی اینکه آیا ناحیه زمانی فعال است یا خیر
        if self.registere_date.tzinfo is not None:
            now = datetime.now(
                self.registere_date.tzinfo
            )  # اگر ناحیه زمانی دارد، همسان سازی با ناحیه زمانی
        else:
            now = datetime.now()  # در غیر این صورت استفاده از زمان فعلی بدون ناحیه زمانی
        # محاسبه اختلاف با استفاده از relativedelta
        age_difference = relativedelta(now, self.registere_date)

        # سن را به صورت سال برمی‌گردانیم
        return age_difference.years

    class Meta:
        verbose_name = "سالن"
        verbose_name_plural = "سالن ها "
        db_table = "s_salon"


# --------------------------------------------------------------------
# گالری سالن
class SalonsGallery(models.Model):
    salon = models.ForeignKey(
        Salon,
        on_delete=models.CASCADE,
        verbose_name="سالن",
        related_name="gallery_images",
    )
    file_upload = File_Uploader("images", "salon_gallery")
    salon_image = models.ImageField(upload_to=file_upload, verbose_name="تصویر سالن")
    order = models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")
    is_cover = models.BooleanField(default=False, verbose_name="تصویر کاور")

    class Meta:
        verbose_name = "تصویر سالن"
        verbose_name_plural = "تصاویر سالن ها "
        db_table = "salons_gallery"
        ordering = ["order"]  # مرتب‌سازی بر اساس فیلد order


# --------------------------------------------------------------------
class SalonOpeningHours(models.Model):
    DAY_CHOICES = [
        (1, "شنبه"),
        (2, "یکشنبه"),
        (3, "دوشنبه"),
        (4, "سه شنبه"),
        (5, "چهارشنبه"),
        (6, "پنج شنبه"),
        (7, "جمعه"),
    ]
    salon = models.ForeignKey(
        "Salon",
        on_delete=models.CASCADE,
        related_name="opening_hours",
        verbose_name="سالن مرتبط",
    )
    day_of_week = models.PositiveSmallIntegerField(choices=DAY_CHOICES, verbose_name="روز هفته")
    open_time = models.TimeField(null=True, blank=True, verbose_name="ساعت شروع")
    close_time = models.TimeField(null=True, blank=True, verbose_name="ساعت پایان")
    is_closed = models.BooleanField(default=False, verbose_name="تعطیل")

    class Meta:
        verbose_name = "ساعت کاری سالن"
        verbose_name_plural = "ساعت کاری سالن‌ها"
        db_table = "s_salon_opening_hours"

    def __str__(self):
        return f"{self.get_day_of_week_display()} - {self.salon.salon_name}"

    def get_day_of_week_display(self):
        """برگرداندن نام فارسی روز متناسب با day_of_week"""
        day_dict = {
            1: "شنبه",
            2: "یکشنبه",
            3: "دوشنبه",
            4: "سه شنبه",
            5: "چهارشنبه",
            6: "پنج شنبه",
            7: "جمعه",
        }
        return day_dict.get(self.day_of_week, "نامشخص")


# ---------------------------------------------------------------------
class SalonMembershipStatus(models.TextChoices):
    INVITED = "invited", "دعوت‌شده"
    PENDING_ACCEPTANCE = "pending_acceptance", "در انتظار پذیرش"
    ACTIVE = "active", "فعال"
    PAUSED = "paused", "موقتاً غیرفعال"
    ENDED = "ended", "قطع همکاری"
    REJECTED = "rejected", "رد شده"
    EXPIRED = "expired", "منقضی شده"
    CANCELLED_BY_SALON = "cancelled_by_salon", "لغو شده توسط سالن"


class SalonMembership(models.Model):
    salon = models.ForeignKey(
        "Salon",
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name="سالن",
    )
    stylist = models.ForeignKey(
        "accounts.Stylist",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="salon_memberships",
        verbose_name="آرایشگر",
    )
    invited_phone = models.CharField(max_length=32, blank=True, default="", db_index=True, verbose_name="موبایل دعوت‌شده")
    invited_email = models.EmailField(blank=True, default="", verbose_name="ایمیل دعوت‌شده")
    role_title = models.CharField(max_length=128, blank=True, default="", verbose_name="عنوان نقش")
    status = models.CharField(
        max_length=64,
        choices=SalonMembershipStatus.choices,
        default=SalonMembershipStatus.INVITED,
        db_index=True,
        verbose_name="وضعیت همکاری",
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_salon_membership_invites",
        verbose_name="دعوت‌کننده",
    )
    accepted_at = models.DateTimeField(null=True, blank=True, verbose_name="تاریخ پذیرش")
    ended_at = models.DateTimeField(null=True, blank=True, verbose_name="تاریخ پایان همکاری")
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="تاریخ انقضای دعوت")
    show_on_salon_profile = models.BooleanField(default=True, verbose_name="نمایش در پروفایل سالن")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="داده تکمیلی")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["salon", "status"]),
            models.Index(fields=["stylist", "status"]),
            models.Index(fields=["invited_phone", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["salon", "stylist"],
                condition=models.Q(stylist__isnull=False),
                name="uniq_salon_member_sty",
            ),
        ]
        verbose_name = "عضویت آرایشگر در سالن"
        verbose_name_plural = "عضویت‌های آرایشگران در سالن‌ها"
        db_table = "s_salon_memberships"

    @property
    def is_active_membership(self):
        return self.status == SalonMembershipStatus.ACTIVE

    def __str__(self):
        person = self.stylist or self.invited_phone or self.invited_email or "بدون نام"
        return f"{person} - {self.salon}"


class StaffDashboardPermission(models.Model):
    membership = models.OneToOneField(
        SalonMembership,
        on_delete=models.CASCADE,
        related_name="dashboard_permissions",
        verbose_name="عضویت",
    )
    can_complete_appointments = models.BooleanField(default=True, verbose_name="اجرای مراحل نوبت")
    can_view_own_finance = models.BooleanField(default=True, verbose_name="مشاهده مالی خود")
    can_request_payout = models.BooleanField(default=True, verbose_name="درخواست پرداخت سهم")
    can_view_own_clients = models.BooleanField(default=True, verbose_name="مشاهده مشتریان خود")
    can_create_own_bookings = models.BooleanField(
        default=True,
        verbose_name="ثبت نوبت برای خود",
    )
    can_view_client_phone = models.BooleanField(default=False, verbose_name="مشاهده شماره تماس مشتری")
    can_manage_own_portfolio = models.BooleanField(default=True, verbose_name="مدیریت نمونه‌کار خود")
    can_submit_posts = models.BooleanField(default=False, verbose_name="ارسال مقاله پیشنهادی")
    can_submit_stories = models.BooleanField(default=False, verbose_name="ارسال استوری پیشنهادی")
    can_request_leave = models.BooleanField(default=True, verbose_name="درخواست مرخصی")
    can_manage_own_schedule = models.BooleanField(default=False, verbose_name="مدیریت برنامه کاری خود")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        verbose_name = "دسترسی داشبورد آرایشگر"
        verbose_name_plural = "دسترسی‌های داشبورد آرایشگران"
        db_table = "s_staff_dashboard_permissions"

    def __str__(self):
        return f"دسترسی {self.membership}"


class MembershipEvent(models.Model):
    membership = models.ForeignKey(
        SalonMembership,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name="عضویت",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="membership_events",
        verbose_name="اقدام‌کننده",
    )
    event_type = models.CharField(max_length=64, db_index=True, verbose_name="نوع رویداد")
    old_status = models.CharField(max_length=64, blank=True, default="", verbose_name="وضعیت قبلی")
    new_status = models.CharField(max_length=64, blank=True, default="", verbose_name="وضعیت جدید")
    note = models.TextField(blank=True, default="", verbose_name="یادداشت")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="داده تکمیلی")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاریخ ایجاد")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["membership", "-created_at"])]
        verbose_name = "رویداد عضویت"
        verbose_name_plural = "رویدادهای عضویت"
        db_table = "s_membership_events"

    def __str__(self):
        return f"{self.event_type} - {self.membership}"


class SalonVerification(models.Model):
    salon = models.OneToOneField(
        "Salon",
        on_delete=models.CASCADE,
        related_name="verification",
        verbose_name="سالن",
    )
    status = models.CharField(
        max_length=64,
        choices=SalonVerificationStatus.choices,
        default=SalonVerificationStatus.UNVERIFIED,
        db_index=True,
        verbose_name="وضعیت احراز",
    )
    identity_status = models.CharField(max_length=64, default="not_submitted", verbose_name="وضعیت مدارک هویتی")
    business_info_status = models.CharField(max_length=64, default="not_submitted", verbose_name="وضعیت اطلاعات کسب‌وکار")
    license_status = models.CharField(max_length=64, default="not_required", verbose_name="وضعیت مجوز")
    bank_account_status = models.CharField(max_length=64, default="not_submitted", verbose_name="وضعیت حساب بانکی")
    contract_status = models.CharField(max_length=64, default="not_signed", verbose_name="وضعیت قرارداد")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_salon_verifications",
        verbose_name="بررسی‌کننده",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاریخ بررسی")
    rejection_reason = models.TextField(blank=True, default="", verbose_name="دلیل رد")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="داده تکمیلی")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        ordering = ["-updated_at", "-id"]
        verbose_name = "احراز سالن"
        verbose_name_plural = "احراز سالن‌ها"
        db_table = "s_salon_verifications"

    def __str__(self):
        return f"{self.salon} - {self.get_status_display()}"


class SalonVerificationDocument(models.Model):
    DOCUMENT_IDENTITY = "identity"
    DOCUMENT_BUSINESS_LICENSE = "business_license"
    DOCUMENT_BANK = "bank"
    DOCUMENT_CONTRACT = "contract"
    DOCUMENT_OTHER = "other"

    DOCUMENT_TYPE_CHOICES = [
        (DOCUMENT_IDENTITY, "مدرک هویتی"),
        (DOCUMENT_BUSINESS_LICENSE, "جواز یا مجوز فعالیت"),
        (DOCUMENT_BANK, "مدرک حساب بانکی"),
        (DOCUMENT_CONTRACT, "قرارداد"),
        (DOCUMENT_OTHER, "سایر"),
    ]

    verification = models.ForeignKey(
        SalonVerification,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="پرونده احراز",
    )
    document_type = models.CharField(max_length=64, choices=DOCUMENT_TYPE_CHOICES, verbose_name="نوع مدرک")
    file_upload = File_Uploader("documents", "salon_verification")
    file = models.FileField(upload_to=file_upload, verbose_name="فایل")
    status = models.CharField(max_length=64, default="pending", db_index=True, verbose_name="وضعیت")
    note = models.TextField(blank=True, default="", verbose_name="یادداشت")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_salon_verification_documents",
        verbose_name="بارگذار",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_salon_verification_documents",
        verbose_name="بررسی‌کننده",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاریخ بررسی")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "مدرک احراز سالن"
        verbose_name_plural = "مدارک احراز سالن"
        db_table = "s_salon_verification_documents"


class BankAccount(models.Model):
    salon = models.ForeignKey("Salon", on_delete=models.CASCADE, related_name="bank_accounts", verbose_name="سالن")
    iban = models.CharField(max_length=34, verbose_name="شماره شبا")
    account_owner_name = models.CharField(max_length=255, verbose_name="نام صاحب حساب")
    bank_name = models.CharField(max_length=128, blank=True, default="", verbose_name="نام بانک")
    is_verified = models.BooleanField(default=False, verbose_name="تأیید شده")
    verified_at = models.DateTimeField(null=True, blank=True, verbose_name="تاریخ تأیید")
    is_default = models.BooleanField(default=False, verbose_name="حساب پیش‌فرض")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="داده تکمیلی")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        ordering = ["-is_default", "-created_at"]
        indexes = [models.Index(fields=["salon", "is_default"])]
        verbose_name = "حساب بانکی سالن"
        verbose_name_plural = "حساب‌های بانکی سالن‌ها"
        db_table = "s_bank_accounts"

    def __str__(self):
        return f"{self.salon} - {self.iban}"


# ---------------------------------------------------------------------
User = get_user_model()


class SalonVisit(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name="کاربر",
        related_name="salon_visits",
    )
    salon = models.ForeignKey(
        "Salon",
        on_delete=models.CASCADE,
        verbose_name="سالن",
        related_name="salon_visits",
    )
    visit_date = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ بازدید")

    class Meta:
        verbose_name = "بازدید سالن"
        verbose_name_plural = "بازدیدهای سالن"
        db_table = "s_salon_visit"
        # اطمینان از اینکه هر کاربر فقط یک بازدید برای هر سالن دارد که آپدیت می‌شود
        unique_together = ("user", "salon")

    def __str__(self):
        return f"{self.user} - {self.salon} - {self.visit_date}"


# ----------------------------------------------------------------------
class SupplementaryInfoView(models.Model):
    salon = models.ForeignKey(
        Salon,
        on_delete=models.CASCADE,
        verbose_name="سالن",
        related_name="supplementary_info",
    )
    title = models.CharField(max_length=50, verbose_name="عنوان")
    description = models.CharField(max_length=200, verbose_name="توضیحات", null=True, blank=True)
    file_upload = File_Uploader("images", "SupplementaryInfo")
    icon_image = models.ImageField(
        upload_to=file_upload,
        verbose_name="تصویر آیکون",
        null=True,
        blank=True,
    )
    icon_class = models.CharField(max_length=50, verbose_name="کلاس آیکون", null=True, blank=True)
    is_active = models.BooleanField(default=False, verbose_name="وضعیت")

    class Meta:
        verbose_name = "اطلاعات تکمیلی"
        verbose_name_plural = "اطلاعات تکمیلی"
        db_table = "s_salon_supplementary_info"


# -------------------------------------------------------------------------
class CustomerNote(models.Model):
    salon = models.ForeignKey(
        Salon,
        on_delete=models.CASCADE,
        verbose_name="سالن",
        related_name="customer_notes",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        verbose_name="مشتری",
        related_name="customer_note",
        null=True,
        blank=True,
    )
    note = models.TextField(verbose_name="یادداشت")
    file_upload = File_Uploader("images", "customer_note")
    note_image = models.ImageField(
        upload_to=file_upload,
        verbose_name="تصویر یادداشت",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        verbose_name="ایجاد کننده",
        related_name="customer_note_creator",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "یادداشت مشتری"
        verbose_name_plural = "یادداشت‌های مشتری"
        db_table = "s_customer_note"
        
        # ✅ بهینه‌سازی: اضافه کردن ایندکس برای جستجوی سریع‌تر
        indexes = [
            models.Index(fields=['customer', 'salon'], name='customer_salon_note_idx'),
        ]

    def __str__(self):
        return f"{self.salon} - {self.created_at}"
