from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    Permission,
    PermissionsMixin,
)
from django.db import models
from django.db.models import Avg
from django.utils import timezone
from utils import File_Uploader


# ----------------------------------------------------------------
#  Create User
class CustomUserManager(BaseUserManager):
    def create_user(
        self,
        mobile_number,
        active_code=None,
        email="",
        name="",
        family="",
        password=None,
    ):
        if not mobile_number:
            raise ValueError("شماره موبایل را وارد کنید ")
        user = self.model(
            mobile_number=mobile_number,
            active_code=active_code,
            email=self.normalize_email(email),
            name=name,
            family=family,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, mobile_number, email, name, family, active_code=None, password=None
    ):
        user = self.create_user(
            mobile_number=mobile_number,
            active_code=active_code,
            email=email,
            name=name,
            family=family,
            password=password,
        )
        user.is_active = True
        user.is_admin = True
        user.is_superuser = True
        user.save(using=self._db)
        return user


# ----------------------------------------------------------------------------
# Custom User
class CustomUser(AbstractBaseUser, PermissionsMixin):
    mobile_number = models.CharField(
        max_length=11, unique=True, verbose_name="شماره موبایل"
    )
    email = models.EmailField(max_length=100, blank=True, verbose_name="ایمیل")
    name = models.CharField(max_length=50, blank=True, verbose_name="نام")
    family = models.CharField(max_length=50, blank=True, verbose_name="نام خانوادگی")
    register_date = models.DateField(default=timezone.now, verbose_name="تاریخ ثبت")
    is_active = models.BooleanField(default=False, verbose_name="وضعیت ")
    active_code = models.CharField(
        max_length=100, null=True, blank=True, verbose_name="کد فعال سازی"
    )
    is_admin = models.BooleanField(default=False)

    USERNAME_FIELD = "mobile_number"
    REQUIRED_FIELDS = ["email", "name", "family"]

    objects = CustomUserManager()

    # Specify custom related_name for groups
    groups = models.ManyToManyField(
        "auth.Group",
        verbose_name="groups",
        blank=True,
        help_text=(
            "The groups this user belongs to."
            "A user will get all permissions "
            "granted to each of their groups."
        ),
        related_name="custom_user_set",
        related_query_name="user",
    )

    # Specify custom related_name for user_permissions
    user_permissions = models.ManyToManyField(
        Permission,
        verbose_name="user permissions",
        blank=True,
        help_text="Specific permissions for this user.",
        related_name="custom_user_permissions",  # Specify a custom related_name
    )

    def __str__(self):
        return self.name + " " + self.family

    def get_fullName(self):
        fullName = self.name + " " + self.family
        return fullName

    @property
    def is_staff(self):
        return self.is_admin

    class Meta:
        verbose_name = "کاربر"
        verbose_name_plural = "کاربران"
        db_table = "A_CustomUser"


# ----------------------------------------------------------------------------
# Customer
class Customer(models.Model):
    GENDER_CHOICES = [
        ("male", "مرد"),
        ("female", "زن"),
        ("other", "سایر"),
    ]

    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        primary_key=True,
        verbose_name="کاربر",
        related_name="customer_profile",
    )
    address = models.TextField(null=True, blank=True, verbose_name="آدرس")
    file_upload = File_Uploader("images", "customers")
    profile_image = models.ImageField(
        upload_to=file_upload,
        null=True,
        blank=True,
        verbose_name="تصویر مشتری",
    )
    added_by_salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="اضافه شده توسط سالن",
        related_name="added_customers",
    )
    birth_date = models.DateField(null=True, blank=True, verbose_name="تاریخ تولد")
    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
        null=True,
        blank=True,
        verbose_name="جنسیت",
    )

    # Notification Settings - Appointment Notifications
    notify_appointment_sms = models.BooleanField(
        default=True, verbose_name="اطلاع رسانی قرار ملاقات از طریق پیامک"
    )
    notify_appointment_whatsapp = models.BooleanField(
        default=True, verbose_name="اطلاع رسانی قرار ملاقات از طریق واتس اپ"
    )
    notify_appointment_email = models.BooleanField(
        default=True,
        verbose_name="اطلاع رسانی قرار ملاقات از طریق ایمیل",
    )

    # Notification Settings - Marketing Notifications
    notify_marketing_email = models.BooleanField(
        default=True, verbose_name="اطلاع رسانی بازاریابی از طریق ایمیل"
    )
    notify_marketing_sms = models.BooleanField(
        default=True, verbose_name="اطلاع رسانی بازاریابی از طریق پیامک"
    )
    notify_marketing_whatsapp = models.BooleanField(
        default=True, verbose_name="اطلاع رسانی بازاریابی از طریق واتس اپ"
    )

    def __str__(self):
        return f"{self.user.name} {self.user.family}"

    def get_fullName(self):
        fullName = self.user.name + " " + self.user.family
        return fullName

    class Meta:
        verbose_name = "مشتری"
        verbose_name_plural = "مشتری ها "
        db_table = "A_Customers"


class CustomerAddress(models.Model):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="addresses",
        verbose_name="مشتری",
    )
    title = models.CharField(max_length=60, default="آدرس", verbose_name="عنوان آدرس")
    recipient_name = models.CharField(max_length=120, blank=True, verbose_name="نام گیرنده")
    phone_number = models.CharField(max_length=20, blank=True, verbose_name="شماره تماس")
    city = models.CharField(max_length=80, blank=True, verbose_name="شهر")
    address_line = models.TextField(verbose_name="متن آدرس")
    postal_code = models.CharField(max_length=20, blank=True, verbose_name="کد پستی")
    plaque = models.CharField(max_length=20, blank=True, verbose_name="پلاک")
    unit = models.CharField(max_length=20, blank=True, verbose_name="واحد")
    is_default = models.BooleanField(default=False, verbose_name="آدرس پیش‌فرض")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        ordering = ["-is_default", "-updated_at", "-id"]
        verbose_name = "آدرس مشتری"
        verbose_name_plural = "آدرس‌های مشتری"
        db_table = "A_CustomerAddresses"

    def __str__(self):
        return f"{self.customer.get_fullName()} - {self.title}"

    @property
    def full_address(self):
        parts = []
        if self.city:
            parts.append(self.city)
        if self.address_line:
            parts.append(self.address_line)
        extra = []
        if self.plaque:
            extra.append(f"پلاک {self.plaque}")
        if self.unit:
            extra.append(f"واحد {self.unit}")
        if extra:
            parts.append(" - ".join(extra))
        return "، ".join([part for part in parts if part])

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.is_default:
            self.customer.addresses.exclude(pk=self.pk).update(is_default=False)
        elif not self.customer.addresses.filter(is_default=True).exists():
            self.customer.addresses.filter(pk=self.pk).update(is_default=True)
            self.is_default = True

        default_address = self.customer.addresses.filter(is_default=True).first() or self
        Customer.objects.filter(pk=self.customer.pk).update(address=default_address.full_address)

    def delete(self, *args, **kwargs):
        customer = self.customer
        super().delete(*args, **kwargs)
        fallback = customer.addresses.filter(is_default=True).first() or customer.addresses.first()
        if fallback and not fallback.is_default:
            customer.addresses.filter(pk=fallback.pk).update(is_default=True)
            fallback = customer.addresses.get(pk=fallback.pk)
        Customer.objects.filter(pk=customer.pk).update(address=fallback.full_address if fallback else "")


class CustomerNotification(models.Model):
    CATEGORY_BOOKING = "booking"
    CATEGORY_PAYMENT = "payment"
    CATEGORY_WALLET = "wallet"
    CATEGORY_SUPPORT = "support"
    CATEGORY_SYSTEM = "system"
    CATEGORY_MARKETING = "marketing"

    CATEGORY_CHOICES = [
        (CATEGORY_BOOKING, "رزرو"),
        (CATEGORY_PAYMENT, "پرداخت"),
        (CATEGORY_WALLET, "کیف پول"),
        (CATEGORY_SUPPORT, "پشتیبانی"),
        (CATEGORY_SYSTEM, "سیستمی"),
        (CATEGORY_MARKETING, "پیشنهادها"),
    ]

    PRIORITY_LOW = "low"
    PRIORITY_NORMAL = "normal"
    PRIORITY_HIGH = "high"

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "کم"),
        (PRIORITY_NORMAL, "معمولی"),
        (PRIORITY_HIGH, "مهم"),
    ]

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="customer_notifications",
        verbose_name="کاربر",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
        verbose_name="مشتری",
    )
    category = models.CharField(
        max_length=24,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_SYSTEM,
        db_index=True,
        verbose_name="دسته‌بندی",
    )
    priority = models.CharField(
        max_length=12,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_NORMAL,
        verbose_name="اولویت",
    )
    title = models.CharField(max_length=160, verbose_name="عنوان")
    body = models.TextField(blank=True, verbose_name="متن اعلان")
    action_url = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="لینک اقدام",
        help_text="می‌تواند یک مسیر داخلی مثل /orders/appointments/ باشد.",
    )
    icon = models.CharField(
        max_length=80,
        default="fa-regular fa-bell",
        blank=True,
        verbose_name="کلاس آیکون",
    )
    metadata = models.JSONField(default=dict, blank=True, verbose_name="داده تکمیلی")
    is_read = models.BooleanField(default=False, db_index=True, verbose_name="خوانده شده")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاریخ ایجاد")
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="تاریخ خواندن")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"]),
            models.Index(fields=["customer", "category", "-created_at"]),
            models.Index(fields=["category", "-created_at"]),
        ]
        verbose_name = "اعلان مشتری"
        verbose_name_plural = "اعلان‌های مشتری"
        db_table = "A_CustomerNotifications"

    def __str__(self):
        return f"{self.title} - {self.user}"

    def mark_as_read(self, *, save=True):
        if self.is_read:
            return
        self.is_read = True
        self.read_at = timezone.now()
        if save:
            self.save(update_fields=["is_read", "read_at"])

    def mark_as_unread(self, *, save=True):
        if not self.is_read and self.read_at is None:
            return
        self.is_read = False
        self.read_at = None
        if save:
            self.save(update_fields=["is_read", "read_at"])



class UserConsent(models.Model):
    CONSENT_TERMS = "terms"
    CONSENT_PRIVACY = "privacy"
    CONSENT_MARKETING = "marketing"
    CONSENT_IMAGE_PUBLICATION = "image_publication"

    CONSENT_TYPE_CHOICES = [
        (CONSENT_TERMS, "پذیرش قوانین استفاده"),
        (CONSENT_PRIVACY, "پذیرش سیاست حریم خصوصی"),
        (CONSENT_MARKETING, "اجازه پیام‌های بازاریابی"),
        (CONSENT_IMAGE_PUBLICATION, "اجازه انتشار تصویر"),
    ]

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="consents",
        verbose_name="کاربر",
    )
    consent_type = models.CharField(
        max_length=64, choices=CONSENT_TYPE_CHOICES, db_index=True, verbose_name="نوع رضایت"
    )
    version = models.CharField(max_length=32, default="1.0", verbose_name="نسخه متن")
    is_granted = models.BooleanField(default=True, verbose_name="تأیید شده")
    source = models.CharField(max_length=64, blank=True, default="", verbose_name="منبع")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP")
    user_agent = models.TextField(blank=True, default="", verbose_name="User Agent")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="داده تکمیلی")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاریخ ثبت")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "consent_type", "-created_at"]),
            models.Index(fields=["consent_type", "is_granted", "-created_at"]),
        ]
        verbose_name = "رضایت کاربر"
        verbose_name_plural = "رضایت‌های کاربران"
        db_table = "A_UserConsents"

    def __str__(self):
        return f"{self.user} - {self.get_consent_type_display()}"


class AccountDeletionRequest(models.Model):
    STATUS_REQUESTED = "requested"
    STATUS_ANONYMIZED = "anonymized"
    STATUS_COMPLETED = "completed"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_REQUESTED, "درخواست شده"),
        (STATUS_ANONYMIZED, "ناشناس‌سازی شده"),
        (STATUS_COMPLETED, "تکمیل شده"),
        (STATUS_REJECTED, "رد شده"),
    ]

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deletion_requests",
        verbose_name="کاربر",
    )
    original_user_id = models.PositiveIntegerField(null=True, blank=True, db_index=True, verbose_name="شناسه کاربر اصلی")
    original_mobile_number = models.CharField(max_length=20, blank=True, default="", verbose_name="موبایل اصلی")
    original_email = models.EmailField(blank=True, default="", verbose_name="ایمیل اصلی")
    reason = models.CharField(max_length=64, blank=True, default="", verbose_name="دلیل")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_REQUESTED, verbose_name="وضعیت")
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ درخواست")
    anonymized_at = models.DateTimeField(null=True, blank=True, verbose_name="تاریخ ناشناس‌سازی")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاریخ تکمیل")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="داده تکمیلی")

    class Meta:
        ordering = ["-requested_at", "-id"]
        indexes = [
            models.Index(fields=["status", "-requested_at"]),
            models.Index(fields=["original_user_id"]),
        ]
        verbose_name = "درخواست حذف حساب"
        verbose_name_plural = "درخواست‌های حذف حساب"
        db_table = "A_AccountDeletionRequests"

    def __str__(self):
        return f"Account deletion #{self.pk or 'new'} - {self.status}"


# -----------------------------------------------------------------------------------
class Stylist(models.Model):
    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, primary_key=True, verbose_name="کاربر"
    )
    description = models.TextField(blank=True, null=True, verbose_name="توضیحات")
    linkedin_link = models.CharField(
        max_length=200, null=True, blank=True, verbose_name="لینک لینکدین"
    )
    insta_link = models.CharField(
        max_length=200, null=True, blank=True, verbose_name="لینک اینستا"
    )
    telegram_link = models.CharField(
        max_length=200, null=True, blank=True, verbose_name="لینک تلگرام "
    )
    file_upload_2 = File_Uploader("images", "stylists")
    profile_image = models.ImageField(
        upload_to=file_upload_2,
        blank=True,
        null=True,
        verbose_name="تصویر پروفایل",
    )
    address = models.TextField(null=True, blank=True, verbose_name="آدرس")
    is_active = models.BooleanField(default=False, verbose_name="وضعیت")
    expert = models.CharField(max_length=100, verbose_name="تخصص", null=True)
    calendar_color = models.CharField(
        max_length=10, verbose_name="رنگ تقویم ", null=True, blank=True
    )
    notify_booking_dashboard = models.BooleanField(
    default=True,
    verbose_name="اعلان رزرو در داشبورد آرایشگر",
    )
    notify_booking_email = models.BooleanField(
        default=True,
        verbose_name="اعلان رزرو با ایمیل برای آرایشگر",
    )
    notify_booking_sms = models.BooleanField(
        default=False,
        verbose_name="اعلان رزرو با پیامک برای آرایشگر",
    )

    class PublicVisibility(models.TextChoices):
        HIDDEN = "hidden", "مخفی"
        SALON_ONLY = "salon_only", "فقط در سالن‌های فعال"
        PUBLIC = "public", "عمومی در Loomera"
        RESUME_ONLY = "resume_only", "فقط رزومه قابل ارسال"

    display_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="نام نمایشی حرفه‌ای",
    )
    started_working_year = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="سال شروع فعالیت",
    )
    public_visibility = models.CharField(
        max_length=32,
        choices=PublicVisibility.choices,
        default=PublicVisibility.SALON_ONLY,
        db_index=True,
        verbose_name="وضعیت نمایش پروفایل",
    )
    is_verified_professional = models.BooleanField(
        default=False,
        verbose_name="متخصص تأییدشده",
    )
    profile_locked_note = models.TextField(
        blank=True,
        default="",
        verbose_name="یادداشت سیستمی رزومه",
    )
    resume_headline = models.CharField(
        max_length=180,
        blank=True,
        default="",
        verbose_name="تیتر رزومه حرفه‌ای",
    )
    resume_summary = models.TextField(
        blank=True,
        default="",
        verbose_name="خلاصه رزومه حرفه‌ای",
    )

    @property
    def professional_display_name(self):
        return (self.display_name or self.get_fullName() or str(self)).strip()

    @property
    def is_visible_on_salon_pages(self):
        return self.public_visibility in {
            self.PublicVisibility.SALON_ONLY,
            self.PublicVisibility.PUBLIC,
        }

    @property
    def is_publicly_searchable(self):
        return self.public_visibility == self.PublicVisibility.PUBLIC

    def __str__(self):
        return f"{self.user.name} {self.user.family}"

    def get_average_score(self):
        avg_score = self.scoring_stylist.all().aggregate(Avg("score"))["score__avg"]
        if avg_score is None:
            avg_score = 0
        return avg_score

    def get_price_for_service(self, service):
        price_record = self.stylist_prices.filter(service=service).first()
        if price_record:
            return price_record.price
        return getattr(service, "base_price", None) or None

    def get_discount_for_service(self, service):
        """
        دریافت تخفیف برای خدمت خاص از سبد تخفیف
        """
        current_time = timezone.now()
        try:
            discount_basket_detail = self.discount_basket_details3.filter(
                service=service,
                discount_basket__is_active=True,
                discount_basket__start_date__lte=current_time,
                discount_basket__end_date__gte=current_time,
            ).first()

            # اگر تخفیفی وجود داشته باشد
            if discount_basket_detail:
                return discount_basket_detail.discount_basket.discount
            else:
                return 0
        except self.discount_basket_details3.model.DoesNotExist:
            return 0

    def get_price_by_discount(self, service):
        """
        محاسبه قیمت با تخفیف برای خدمت خاص
        """
        # بررسی اینکه آیا آرایشگر قیمتی برای خدمت دارد
        service_price = self.get_price_for_service(service)
        if not service_price:
            return 0  # اگر قیمت خدمت وجود ندارد، صفر برمی‌گرداند

        # گرفتن تخفیف
        discount = self.get_discount_for_service(service)

        # محاسبه قیمت نهایی با تخفیف
        final_price = service_price - (service_price * discount / 100)
        return final_price

    def get_fullName(self):
        fullName = self.user.name + " " + self.user.family
        return fullName

    class Meta:
        verbose_name = "آرایشگر"
        verbose_name_plural = "آرایشگران"
        db_table = "a_stylists"


# ----------------------------------------------------------------------------
# Salon Manager
class SalonManager(models.Model):
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        primary_key=True,
        verbose_name="کاربر",
        related_name="salon_manager_profile",
    )
    address = models.TextField(null=True, blank=True, verbose_name="آدرس")
    file_upload = File_Uploader("images", "salon_manager")
    profile_image = models.ImageField(
        upload_to=file_upload,
        blank=True,
        null=True,
        verbose_name="تصویر پروفایل",
    )
    salon_number = models.IntegerField(null=True, blank=True, verbose_name="تلفن سالن")
    is_active = models.BooleanField(default=False, verbose_name="وضعیت")
    slug = models.SlugField(null=True, blank=True, verbose_name="اسلاگ")

    def __str__(self):
        return f"{self.user.name} {self.user.family}"

    class Meta:
        verbose_name = "مدیر سالن"
        verbose_name_plural = "مدیران سالن ها"
        db_table = "A_Salon_Managers"


# ----------------------------------------------------------------------------
# work_sampels
class WorkSamples(models.Model):
    stylist = models.ForeignKey(
        Stylist,
        on_delete=models.CASCADE,
        verbose_name="آرایشگر",
        related_name="work_samples_of_stylist",
        null=True,
    )
    service = models.ForeignKey(
        "services.Services",
        on_delete=models.CASCADE,
        verbose_name="خدمت ",
        related_name="work_samples_services",
        null=True,
    )
    file_upload = File_Uploader("images", "work_samples")
    sample_image = models.ImageField(
        upload_to=file_upload, verbose_name="تصویر نمونه کار"
    )
    description = models.TextField(verbose_name="توضیحات", null=True, blank=True)
    like_count = models.PositiveIntegerField(default=0, verbose_name="تعداد لایک")
    is_active = models.BooleanField(default=False, verbose_name="وضعیت")
    salon = models.ForeignKey(
        "salons.Salon",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_samples",
        verbose_name="سالن مرتبط",
    )
    appointment = models.ForeignKey(
        "orders.OrderDetail",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verified_work_samples",
        verbose_name="نوبت مرتبط",
    )
    is_public = models.BooleanField(default=True, verbose_name="نمایش عمومی")
    is_verified_work = models.BooleanField(default=False, verbose_name="نمونه‌کار تأییدشده")
    contains_identifiable_client = models.BooleanField(default=False, verbose_name="دارای هویت قابل تشخیص مشتری")
    client_consent_status = models.CharField(
        max_length=64,
        default="not_required",
        verbose_name="وضعیت رضایت مشتری",
    )
    review_status = models.CharField(
        max_length=64,
        default="published",
        db_index=True,
        verbose_name="وضعیت بررسی",
    )

    def __str__(self):
        return self.description or f"نمونه‌کار {self.pk or ''}"

    class Meta:
        verbose_name = "نمونه کار"
        verbose_name_plural = "نمونه کار ها"
        db_table = "A_Work_Samples"


# -------------------------------------------------------------------------------------------
