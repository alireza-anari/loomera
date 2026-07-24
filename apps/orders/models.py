import uuid
from datetime import date, datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from apps.accounts.models import Customer, Stylist
from apps.salons.models import Salon
from apps.services.models import Services
from django.core.exceptions import ValidationError


class PaymentType(models.Model):
    payment_title = models.CharField(max_length=50, verbose_name="نوع پرداخت")

    def __str__(self):
        return self.payment_title

    class Meta:
        verbose_name = "نوع پرداخت"
        verbose_name_plural = "انواغ روش پرداخت"


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "در انتظار تایید"),
        ("confirmed", "تایید شده"),
        ("paid", "پرداخت شده"),
        ("completed", "انجام شده"),
        ("cancelled", "لغو شده"),
        ("no_show", "عدم حضور"),
        ("disputed", "دارای اختلاف"),
    ]
    PAYMENT_METHOD_CHOICES = [
        ("online", "پرداخت آنلاین"),
        ("wallet", "کیف پول"),
        ("pay_in_salon", "پرداخت در سالن"),
    ]
    REMINDER_STATUS_CHOICES = [
        ("pending", "در انتظار ارسال"),
        ("scheduled", "زمان‌بندی شد"),
        ("sent", "ارسال شد"),
        ("skipped", "رد شد"),
        ("cancelled", "لغو شد"),
    ]

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="وضعیت"
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, verbose_name="مشتری", related_name="orders"
    )
    salon = models.ForeignKey(
        Salon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name="سالن",
    )
    register_date = models.DateField(default=timezone.now, verbose_name="تاریخ ثبت")
    update_date = models.DateField(auto_now=True, verbose_name="تاریخ آپدیت")
    is_finally = models.BooleanField(default=False, verbose_name="نهایی شده")
    is_paid = models.BooleanField(default=False, verbose_name="پرداخت شده")
    order_code = models.UUIDField(
        unique=True, default=uuid.uuid4, verbose_name="کد سفارش", editable=False
    )
    discount = models.IntegerField(
        null=True, blank=True, verbose_name="تخفیف", default=0
    )
    description = models.TextField(null=True, blank=True, verbose_name="توضیحات")
    payment_type = models.ForeignKey(
        PaymentType,
        on_delete=models.CASCADE,
        verbose_name="نوع پرداخت",
        related_name="payment",
        null=True,
        blank=True,
    )
    stylist_approved = models.BooleanField(default=False, verbose_name="تایید آرایشگر")
    selected_payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default="pay_in_salon",
        verbose_name="روش پرداخت انتخابی",
    )
    requires_online_payment = models.BooleanField(
        default=False,
        verbose_name="الزام پرداخت آنلاین",
    )
    subtotal_amount = models.PositiveIntegerField(default=0, verbose_name="جمع خدمات")
    discount_amount = models.PositiveIntegerField(default=0, verbose_name="مبلغ تخفیف")
    basket_discount_amount = models.PositiveIntegerField(
        default=0, verbose_name="مبلغ تخفیف خدمات"
    )
    coupon_discount_amount = models.PositiveIntegerField(
        default=0, verbose_name="مبلغ تخفیف کد"
    )
    basket_discount_percent = models.PositiveSmallIntegerField(
        default=0, verbose_name="درصد تخفیف خدمات"
    )
    basket_discount_title = models.CharField(
        max_length=120, blank=True, default="", verbose_name="عنوان سبد تخفیف"
    )
    tax_amount = models.PositiveIntegerField(default=0, verbose_name="مالیات")
    total_amount = models.PositiveIntegerField(default=0, verbose_name="مبلغ نهایی")
    coupon_code = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="کد تخفیف اعمال شده",
    )
    discount_rules_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="اسنپ‌شات قوانین تخفیف",
    )
    platform_commission_applies = models.BooleanField(
        default=False,
        verbose_name="مشمول کارمزد اولین مراجعه",
    )
    platform_commission_percent = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="درصد کارمزد پلتفرم",
    )
    platform_commission_amount = models.PositiveIntegerField(
        default=0,
        verbose_name="مبلغ کارمزد پلتفرم",
    )
    salon_payout_amount = models.PositiveIntegerField(
        default=0,
        verbose_name="مبلغ تسویه به سالن",
    )
    checkout_locked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان قفل شدن چک‌اوت",
    )
    refunded_to_wallet_amount = models.PositiveIntegerField(
        default=0,
        verbose_name="مبلغ بازگشت‌داده‌شده به کیف پول",
    )
    refunded_to_wallet_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان بازگشت وجه به کیف پول",
    )
    cancellation_reason = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="دلیل لغو",
    )
    booking_source = models.CharField(
        max_length=32,
        choices=[
            ("customer", "رزرو کاربر"),
            ("dashboard_manual", "رزرو دستی داشبورد"),
        ],
        default="customer",
        verbose_name="منبع ثبت رزرو",
    )
    booking_quick_link = models.ForeignKey(
        "orders.BookingQuickLink",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="attributed_orders",
        verbose_name="لینک رزرو منتسب",
    )
    stylist_confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان تایید آرایشگر",
    )
    customer_arrived_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان رسیدن مشتری",
    )
    service_started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان شروع خدمت",
    )
    service_completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان پایان خدمت",
    )
    reminder_due_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان برنامه‌ریزی یادآوری",
    )
    reminder_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان ارسال یادآوری",
    )
    reminder_status = models.CharField(
        max_length=20,
        choices=REMINDER_STATUS_CHOICES,
        default="pending",
        verbose_name="وضعیت یادآوری",
    )
    review_requested_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان درخواست نظرسنجی",
    )
    review_completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان ثبت نظرسنجی",
    )

    @property
    def order_number(self):
        return f"ORD-{self.id:06d}"

    def get_order_total_price(self):
        total = 0
        for item in self.order_details1.all():
            total += item.price

        if self.total_amount:
            return self.total_amount
        return total

    def update_status(self):
        if self.status == "cancelled":
            pass
        elif self.service_completed_at:
            self.status = "completed"
        elif self.is_paid:
            self.status = "paid"
        elif self.is_finally:
            self.status = "confirmed"
        else:
            self.status = "pending"

        self.save()

    @property
    def is_dashboard_manual_booking(self):
        return self.booking_source == "dashboard_manual"

    def refresh_lifecycle_from_details(self, save=True):
        """
        وضعیت کلی سفارش را از روی آیتم‌های رزرو sync می‌کند.
        این کار برای رزروهای چندخدمتی و چندآرایشگری لازم است.
        """
        if self.status == "cancelled":
            return self

        details = list(self.order_details1.all())
        if not details:
            return self

        confirmed_details = [
            item
            for item in details
            if item.confirmation_status == OrderDetail.ConfirmationStatus.CONFIRMED
        ]
        rejected_details = [
            item
            for item in details
            if item.confirmation_status == OrderDetail.ConfirmationStatus.REJECTED
        ]

        all_confirmed = len(confirmed_details) == len(details)
        any_confirmed = bool(confirmed_details)
        any_rejected = bool(rejected_details)

        arrived_values = [
            item.customer_arrived_at for item in details if item.customer_arrived_at
        ]
        started_values = [
            item.service_started_at for item in details if item.service_started_at
        ]
        completed_values = [
            item.service_completed_at for item in details if item.service_completed_at
        ]
        confirmed_values = [
            item.stylist_confirmed_at for item in details if item.stylist_confirmed_at
        ]
        disputed_details = [
            item
            for item in details
            if item.lifecycle_status == OrderDetail.ServiceLifecycleStatus.DISPUTED
            or item.disputed_at
        ]
        no_show_confirmed_details = [
            item for item in details if item.no_show_confirmed_at
        ]
        all_no_show_confirmed = len(no_show_confirmed_details) == len(details)

        self.stylist_approved = all_confirmed
        self.stylist_confirmed_at = (
            min(confirmed_values) if all_confirmed and confirmed_values else None
        )
        self.customer_arrived_at = (
            min(arrived_values) if len(arrived_values) == len(details) else None
        )
        self.service_started_at = min(started_values) if started_values else None
        self.service_completed_at = (
            max(completed_values) if len(completed_values) == len(details) else None
        )

        if disputed_details:
            self.is_finally = False
            self.status = "disputed"
        elif all_no_show_confirmed:
            self.is_finally = True
            self.status = "no_show"
        elif any_rejected and not any_confirmed:
            self.is_finally = False
            if not self.is_paid:
                self.status = "pending"
        elif self.service_completed_at:
            self.is_finally = True
            self.status = "completed"
        elif self.is_paid:
            self.is_finally = all_confirmed
            self.status = "paid"
        elif all_confirmed:
            self.is_finally = True
            self.status = "confirmed"
        else:
            self.is_finally = False
            self.status = "pending"

        if save:
            self.save(
                update_fields=[
                    "stylist_approved",
                    "stylist_confirmed_at",
                    "customer_arrived_at",
                    "service_started_at",
                    "service_completed_at",
                    "is_finally",
                    "status",
                    "update_date",
                ]
            )

        return self

    def __str__(self):
        return f"{self.customer}"

    class Meta:
        verbose_name = "سفارش"
        verbose_name_plural = "سفارش ها"


class BookingQuickLink(models.Model):
    class Mode(models.TextChoices):
        SALON = "salon", "صفحه اصلی سالن"
        SERVICE = "service", "فقط خدمت"
        STYLIST = "stylist", "فقط متخصص"
        SERVICE_STYLIST = "service_stylist", "خدمت + متخصص"
        SERVICE_STYLIST_TIME = "service_stylist_time", "خدمت + متخصص + زمان"

    class Placement(models.TextChoices):
        DIRECT = "direct", "ارسال مستقیم به مشتری"
        MIRROR_LABEL = "mirror_label", "لیبل کنار آینه"
        RECEPTION = "reception", "پذیرش"
        TABLE_STAND = "table_stand", "استند رومیزی"
        BOOKING_CARD = "booking_card", "کارت رزرو"
        INSTAGRAM_BIO = "instagram_bio", "بیوی اینستاگرام"
        INSTAGRAM_STORY = "instagram_story", "استوری اینستاگرام"
        WHATSAPP = "whatsapp", "واتساپ"
        OTHER = "other", "سایر"

    token = models.UUIDField(
        unique=True,
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        verbose_name="توکن لینک",
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="booking_quick_links",
        verbose_name="سازنده لینک",
    )
    salon = models.ForeignKey(
        Salon,
        on_delete=models.CASCADE,
        related_name="booking_quick_links",
        verbose_name="سالن",
    )
    service = models.ForeignKey(
        Services,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_quick_links",
        verbose_name="خدمت",
    )
    stylist = models.ForeignKey(
        Stylist,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_quick_links",
        verbose_name="متخصص",
    )
    title = models.CharField(
        max_length=160,
        blank=True,
        default="",
        verbose_name="عنوان لینک",
    )
    placement = models.CharField(
        max_length=32,
        choices=Placement.choices,
        default=Placement.OTHER,
        db_index=True,
        verbose_name="محل استفاده",
    )
    campaign_name = models.CharField(
        max_length=160,
        blank=True,
        default="",
        verbose_name="نام کمپین",
    )
    internal_note = models.TextField(
        blank=True,
        default="",
        verbose_name="یادداشت داخلی",
    )
    mode = models.CharField(
        max_length=32,
        choices=Mode.choices,
        verbose_name="نوع لینک",
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="اطلاعات لینک",
    )
    is_permanent = models.BooleanField(
        default=False,
        verbose_name="لینک دائمی",
        help_text="برای لینک‌هایی که در شبکه‌های اجتماعی قرار می‌گیرند فعال شود.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال",
    )
    opens_count = models.PositiveIntegerField(
        default=0,
        verbose_name="تعداد بازشدن",
    )
    bookings_count = models.PositiveIntegerField(
        default=0,
        verbose_name="تعداد رزرو ثبت‌شده",
    )
    used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان مصرف لینک",
    )
    disabled_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان غیرفعال‌سازی",
    )
    archived_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="زمان بایگانی",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان انقضا",
    )
    last_opened_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="آخرین بازدید",
    )
    last_converted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="آخرین رزرو موفق",
    )
    used_order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="used_quick_links",
        verbose_name="رزرو مصرف‌کننده لینک",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="زمان ساخت",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخرین تغییر",
    )

    @property
    def is_expired(self):
        return bool(self.expires_at and timezone.now() >= self.expires_at)

    @property
    def can_open(self):
        if self.archived_at:
            return False
        if not self.is_active:
            return False
        if not self.is_permanent and self.used_at:
            return False
        if self.is_expired:
            return False
        return True

    @property
    def status_label(self):
        if self.archived_at:
            return "بایگانی‌شده"
        if not self.is_active:
            return "غیرفعال"
        if not self.is_permanent and self.used_at:
            return "مصرف‌شده"
        if self.is_expired:
            return "منقضی‌شده"
        if self.is_permanent:
            return "دائمی"
        return "فعال"

    @property
    def status_tone(self):
        if self.archived_at:
            return "muted"
        if not self.is_active:
            return "danger"
        if not self.is_permanent and self.used_at:
            return "muted"
        if self.is_expired:
            return "warning"
        if self.is_permanent:
            return "success"
        return "primary"

    def mark_opened(self):
        self.last_opened_at = timezone.now()
        self.save(update_fields=["last_opened_at", "updated_at"])

    def mark_disabled(self):
        self.is_active = False
        self.disabled_at = timezone.now()
        self.save(update_fields=["is_active", "disabled_at", "updated_at"])

    def mark_enabled(self):
        if self.archived_at:
            raise ValidationError("لینک بایگانی‌شده را نمی‌توان فعال کرد.")

        self.is_active = True
        self.disabled_at = None
        if not self.is_permanent and self.used_at:
            self.used_at = None
            self.used_order = None
        self.save(
            update_fields=[
                "is_active",
                "disabled_at",
                "used_at",
                "used_order",
                "updated_at",
            ]
        )

    def mark_archived(self):
        archived_at = timezone.now()
        self.archived_at = archived_at
        self.is_active = False
        self.disabled_at = archived_at
        self.save(
            update_fields=[
                "archived_at",
                "is_active",
                "disabled_at",
                "updated_at",
            ]
        )

    def mark_used(self, order=None):
        """
        Wrapper سازگار با کدهای قدیمی.

        منطق افزایش شمارنده در سرویس اتمیک quick_links قرار دارد.
        """
        if order is None or not getattr(order, "pk", None):
            raise ValidationError(
                "برای ثبت استفاده از لینک، سفارش معتبر لازم است."
            )

        if (
            order.booking_quick_link_id
            and order.booking_quick_link_id != self.pk
        ):
            raise ValidationError(
                "این سفارش قبلاً به لینک رزرو دیگری منتسب شده است."
            )

        if order.booking_quick_link_id is None:
            order.booking_quick_link = self
            order.save(update_fields=["booking_quick_link"])

        from .quick_links import mark_booking_quick_link_converted

        return mark_booking_quick_link_converted(order)

    def __str__(self):
        return self.title or f"لینک سریع {self.pk}"

    class Meta:
        verbose_name = "لینک سریع رزرو"
        verbose_name_plural = "لینک‌های سریع رزرو"
        ordering = ["-created_at"]


class OrderDetail(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        verbose_name="سفارش",
        related_name="order_details1",
    )
    service = models.ForeignKey(
        Services,
        on_delete=models.CASCADE,
        verbose_name="خدمت",
        related_name="order_details_services",
    )
    stylist = models.ForeignKey(
        Stylist,
        on_delete=models.CASCADE,
        verbose_name="آرایشگر",
        related_name="order_details_stylist",
    )
    salon = models.ForeignKey(
        Salon,
        on_delete=models.CASCADE,
        verbose_name="سالن",
        related_name="order_details_salon",
    )
    price = models.IntegerField(verbose_name=" قیمت")
    date = models.DateField(verbose_name="تاریخ", null=True)
    time = models.TimeField(verbose_name="زمان", null=True)
    end_time = models.TimeField(verbose_name="زمان پایان", null=True)
    scheduled_duration_minutes = models.PositiveIntegerField(
        default=0,
        verbose_name="مدت زمان زمان‌بندی‌شده خدمت",
        help_text="در زمان رزرو از مدت خدمت snapshot می‌شود تا تغییرات بعدی روی نوبت‌های قبلی اثر نگذارد.",
    )
    buffer_minutes = models.PositiveIntegerField(
        default=0,
        verbose_name="بافر رزروشده بعد از خدمت",
        help_text="این زمان بعد از پایان خدمت برای جلوگیری از تداخل نوبت بعدی لحاظ می‌شود.",
    )
    occupied_until = models.TimeField(
        null=True,
        blank=True,
        verbose_name="پایان اشغال تقویم با احتساب بافر",
    )

    class ConfirmationStatus(models.TextChoices):
        PENDING = "pending", "در انتظار تایید"
        CONFIRMED = "confirmed", "تایید شده"
        REJECTED = "rejected", "رد شده"

    class ServiceLifecycleStatus(models.TextChoices):
        AWAITING_CONFIRMATION = "awaiting_confirmation", "در انتظار تایید"
        CONFIRMED = "confirmed", "تایید شده"
        CLIENT_LATE = "client_late", "مشتری با تاخیر"
        NO_SHOW_PENDING_REVIEW = "no_show_pending_review", "عدم حضور در انتظار بررسی"
        NO_SHOW_CONFIRMED = "no_show_confirmed", "عدم حضور تایید شده"
        ARRIVED = "arrived", "مشتری رسید"
        IN_SERVICE = "in_service", "در حال انجام"
        SERVICE_OVERRUN = "service_overrun", "طولانی‌شدن خدمت"
        COMPLETED = "completed", "تکمیل شده"
        DISPUTED = "disputed", "دارای اختلاف"

    confirmation_status = models.CharField(
        max_length=20,
        choices=ConfirmationStatus.choices,
        default=ConfirmationStatus.PENDING,
        verbose_name="وضعیت تایید آرایشگر",
    )

    lifecycle_status = models.CharField(
        max_length=32,
        choices=ServiceLifecycleStatus.choices,
        default=ServiceLifecycleStatus.AWAITING_CONFIRMATION,
        verbose_name="وضعیت اجرای خدمت",
    )

    stylist_confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان تایید این خدمت توسط آرایشگر",
    )

    stylist_rejected_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان رد این خدمت توسط آرایشگر",
    )

    rejection_reason = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="دلیل رد خدمت",
    )

    customer_arrived_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان رسیدن مشتری برای این خدمت",
    )

    service_started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان شروع این خدمت",
    )

    service_completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان پایان این خدمت",
    )

    financial_finalized_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان نهایی شدن مالی این خدمت",
    )
    client_late_recorded_at = models.DateTimeField(
        null=True, blank=True, verbose_name="زمان ثبت تاخیر مشتری"
    )
    client_late_minutes = models.PositiveIntegerField(
        default=0, verbose_name="میزان تاخیر مشتری به دقیقه"
    )
    no_show_pending_at = models.DateTimeField(
        null=True, blank=True, verbose_name="زمان ثبت عدم حضور در انتظار بررسی"
    )
    no_show_dispute_until = models.DateTimeField(
        null=True, blank=True, verbose_name="مهلت اعتراض یا بررسی عدم حضور"
    )
    no_show_confirmed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="زمان تایید نهایی عدم حضور"
    )
    no_show_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_no_show_order_details",
        verbose_name="تاییدکننده عدم حضور",
    )
    expected_service_completed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="زمان مورد انتظار پایان خدمت"
    )
    service_overrun_recorded_at = models.DateTimeField(
        null=True, blank=True, verbose_name="زمان ثبت طولانی‌شدن خدمت"
    )
    service_overrun_minutes = models.PositiveIntegerField(
        default=0, verbose_name="میزان طولانی‌شدن خدمت به دقیقه"
    )
    service_overrun_reason = models.CharField(
        max_length=255, blank=True, default="", verbose_name="دلیل طولانی‌شدن خدمت"
    )
    disputed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="زمان ورود به وضعیت اختلاف"
    )
    operational_note = models.TextField(
        blank=True, default="", verbose_name="یادداشت عملیاتی"
    )

    def __str__(self):
        return f"{self.order}"

    def is_upcoming(self):
        try:
            if isinstance(self.date, date):
                appointment_date = self.date
            elif isinstance(self.date, str):
                from persiantools.jdatetime import JalaliDate

                parts = self.date.split("-")
                jdate = JalaliDate(int(parts[0]), int(parts[1]), int(parts[2]))
                appointment_date = jdate.to_gregorian()
            else:
                return False

            today = timezone.localdate()

            if appointment_date >= today:
                if appointment_date == today and self.time:
                    now_time = timezone.localtime(timezone.now()).time()
                    return self.time > now_time
                return True

            return False

        except Exception:
            return False

    def is_past(self):
        return not self.is_upcoming()

    def can_cancel(self):
        if self.order.status not in ["pending", "confirmed", "paid"]:
            return False

        if not self.is_upcoming():
            return False

        try:
            if isinstance(self.date, date):
                naive_dt = datetime.combine(self.date, self.time or datetime.min.time())
            elif isinstance(self.date, str):
                from persiantools.jdatetime import JalaliDate

                parts = self.date.split("-")
                jdate = JalaliDate(int(parts[0]), int(parts[1]), int(parts[2]))
                gregorian_date = jdate.to_gregorian()
                naive_dt = datetime.combine(
                    gregorian_date, self.time or datetime.min.time()
                )
            else:
                return False

            if timezone.is_naive(naive_dt):
                appointment_datetime = timezone.make_aware(
                    naive_dt, timezone.get_current_timezone()
                )
            else:
                appointment_datetime = naive_dt

            now = timezone.now()
            time_until = appointment_datetime - now
            required_hours = 24
            try:
                required_hours = int(
                    getattr(self.salon, "cancellation_window_hours", 24) or 24
                )
            except Exception:
                required_hours = 24

            return time_until.total_seconds() >= (required_hours * 3600)

        except Exception:
            return False

    def get_status_display_fa(self):
        if self.order.status == "cancelled":
            return "لغو شده"

        if self.confirmation_status == self.ConfirmationStatus.REJECTED:
            return "رد شده توسط آرایشگر"

        status_map = {
            self.ServiceLifecycleStatus.AWAITING_CONFIRMATION: "در انتظار تایید",
            self.ServiceLifecycleStatus.CONFIRMED: "تایید شده",
            self.ServiceLifecycleStatus.CLIENT_LATE: "مشتری با تاخیر",
            self.ServiceLifecycleStatus.NO_SHOW_PENDING_REVIEW: "عدم حضور در انتظار بررسی",
            self.ServiceLifecycleStatus.NO_SHOW_CONFIRMED: "عدم حضور تایید شده",
            self.ServiceLifecycleStatus.ARRIVED: "مشتری رسید",
            self.ServiceLifecycleStatus.IN_SERVICE: "در حال انجام",
            self.ServiceLifecycleStatus.SERVICE_OVERRUN: "طولانی‌شدن خدمت",
            self.ServiceLifecycleStatus.COMPLETED: "انجام شده",
            self.ServiceLifecycleStatus.DISPUTED: "دارای اختلاف",
        }
        return status_map.get(self.lifecycle_status, "در انتظار تایید")

    def get_status_badge_class(self):
        if self.order.status == "cancelled":
            return "bg-red-600"

        if self.confirmation_status == self.ConfirmationStatus.REJECTED:
            return "bg-rose-600"

        status_classes = {
            self.ServiceLifecycleStatus.AWAITING_CONFIRMATION: "bg-yellow-500",
            self.ServiceLifecycleStatus.CONFIRMED: "bg-purple-600 status-badge-confirmed",
            self.ServiceLifecycleStatus.CLIENT_LATE: "bg-amber-600",
            self.ServiceLifecycleStatus.NO_SHOW_PENDING_REVIEW: "bg-orange-600",
            self.ServiceLifecycleStatus.NO_SHOW_CONFIRMED: "bg-rose-700",
            self.ServiceLifecycleStatus.ARRIVED: "bg-indigo-600",
            self.ServiceLifecycleStatus.IN_SERVICE: "bg-sky-600",
            self.ServiceLifecycleStatus.SERVICE_OVERRUN: "bg-orange-700",
            self.ServiceLifecycleStatus.COMPLETED: "bg-blue-600",
            self.ServiceLifecycleStatus.DISPUTED: "bg-slate-700",
        }
        return status_classes.get(self.lifecycle_status, "bg-gray-600")

    def mark_confirmed(self, *, at=None, save=True):
        at = at or timezone.now()
        self.confirmation_status = self.ConfirmationStatus.CONFIRMED
        self.lifecycle_status = self.ServiceLifecycleStatus.CONFIRMED
        self.stylist_confirmed_at = at
        self.stylist_rejected_at = None
        self.rejection_reason = ""

        if save:
            self.save(
                update_fields=[
                    "confirmation_status",
                    "lifecycle_status",
                    "stylist_confirmed_at",
                    "stylist_rejected_at",
                    "rejection_reason",
                ]
            )
        return self

    def mark_rejected(self, *, reason="", at=None, save=True):
        at = at or timezone.now()
        self.confirmation_status = self.ConfirmationStatus.REJECTED
        self.lifecycle_status = self.ServiceLifecycleStatus.AWAITING_CONFIRMATION
        self.stylist_rejected_at = at
        self.rejection_reason = (reason or "")[:255]

        if save:
            self.save(
                update_fields=[
                    "confirmation_status",
                    "lifecycle_status",
                    "stylist_rejected_at",
                    "rejection_reason",
                ]
            )
        return self

    def mark_customer_arrived(self, *, at=None, save=True):
        at = at or timezone.now()
        self.customer_arrived_at = at
        self.lifecycle_status = self.ServiceLifecycleStatus.ARRIVED

        if save:
            self.save(update_fields=["customer_arrived_at", "lifecycle_status"])
        return self

    def mark_service_started(self, *, at=None, save=True):
        at = at or timezone.now()
        self.service_started_at = at
        self.lifecycle_status = self.ServiceLifecycleStatus.IN_SERVICE
        duration = int(
            self.scheduled_duration_minutes
            or getattr(self.service, "duration_minutes", 0)
            or 30
        )
        self.expected_service_completed_at = at + timedelta(minutes=duration)

        if save:
            self.save(
                update_fields=[
                    "service_started_at",
                    "expected_service_completed_at",
                    "lifecycle_status",
                ]
            )
        return self

    def mark_service_completed(self, *, at=None, save=True):
        at = at or timezone.now()
        self.service_completed_at = at
        expected = self.expected_service_completed_at
        if expected and at > expected:
            delta = at - expected
            self.service_overrun_minutes = max(
                int(delta.total_seconds() // 60), self.service_overrun_minutes or 0
            )
            if self.service_overrun_minutes and not self.service_overrun_recorded_at:
                self.service_overrun_recorded_at = at
        self.lifecycle_status = self.ServiceLifecycleStatus.COMPLETED

        if save:
            self.save(
                update_fields=[
                    "service_completed_at",
                    "service_overrun_minutes",
                    "service_overrun_recorded_at",
                    "lifecycle_status",
                ]
            )
        return self

    def appointment_start_datetime(self):
        if not self.date or not self.time:
            return None
        value = datetime.combine(self.date, self.time)
        return (
            timezone.make_aware(value, timezone.get_current_timezone())
            if timezone.is_naive(value)
            else value
        )

    def scheduled_end_datetime(self):
        if not self.date or not self.end_time:
            return None
        value = datetime.combine(self.date, self.end_time)
        return (
            timezone.make_aware(value, timezone.get_current_timezone())
            if timezone.is_naive(value)
            else value
        )

    def occupied_until_datetime(self):
        if not self.date:
            return None
        end_time = self.occupied_until or self.end_time
        if not end_time:
            return None
        value = datetime.combine(self.date, end_time)
        return (
            timezone.make_aware(value, timezone.get_current_timezone())
            if timezone.is_naive(value)
            else value
        )

    def recompute_schedule_snapshots(self, *, save=True):
        duration = int(
            self.scheduled_duration_minutes
            or getattr(self.service, "duration_minutes", 0)
            or 30
        )
        buffer_value = int(
            self.buffer_minutes or getattr(self.service, "buffer_minutes", 0) or 0
        )
        self.scheduled_duration_minutes = duration
        self.buffer_minutes = buffer_value
        if self.date and self.time:
            start_dt = datetime.combine(self.date, self.time)
            service_end_dt = start_dt + timedelta(minutes=duration)
            occupied_dt = service_end_dt + timedelta(minutes=buffer_value)
            self.end_time = service_end_dt.time()
            self.occupied_until = occupied_dt.time()
        if save:
            self.save(
                update_fields=[
                    "scheduled_duration_minutes",
                    "buffer_minutes",
                    "end_time",
                    "occupied_until",
                ]
            )
        return self

    def mark_client_late(self, *, minutes=0, note="", at=None, save=True):
        at = at or timezone.now()
        self.client_late_recorded_at = at
        self.client_late_minutes = max(int(minutes or 0), 0)
        self.lifecycle_status = self.ServiceLifecycleStatus.CLIENT_LATE
        if note:
            self.operational_note = (note or "")[:2000]
        if save:
            self.save(
                update_fields=[
                    "client_late_recorded_at",
                    "client_late_minutes",
                    "lifecycle_status",
                    "operational_note",
                ]
            )
        return self

    def mark_no_show_pending(self, *, dispute_until=None, note="", at=None, save=True):
        at = at or timezone.now()
        self.no_show_pending_at = at
        self.no_show_dispute_until = dispute_until
        self.lifecycle_status = self.ServiceLifecycleStatus.NO_SHOW_PENDING_REVIEW
        if note:
            self.operational_note = (note or "")[:2000]
        if save:
            self.save(
                update_fields=[
                    "no_show_pending_at",
                    "no_show_dispute_until",
                    "lifecycle_status",
                    "operational_note",
                ]
            )
        return self

    def mark_no_show_confirmed(self, *, confirmed_by=None, note="", at=None, save=True):
        at = at or timezone.now()
        self.no_show_confirmed_at = at
        self.no_show_confirmed_by = confirmed_by
        self.lifecycle_status = self.ServiceLifecycleStatus.NO_SHOW_CONFIRMED
        if note:
            self.operational_note = (note or "")[:2000]
        if save:
            self.save(
                update_fields=[
                    "no_show_confirmed_at",
                    "no_show_confirmed_by",
                    "lifecycle_status",
                    "operational_note",
                ]
            )
        return self

    def mark_service_overrun(self, *, minutes=0, reason="", at=None, save=True):
        at = at or timezone.now()
        self.service_overrun_recorded_at = at
        self.service_overrun_minutes = max(int(minutes or 0), 0)
        self.service_overrun_reason = (reason or "")[:255]
        self.lifecycle_status = self.ServiceLifecycleStatus.SERVICE_OVERRUN
        if save:
            self.save(
                update_fields=[
                    "service_overrun_recorded_at",
                    "service_overrun_minutes",
                    "service_overrun_reason",
                    "lifecycle_status",
                ]
            )
        return self

    def mark_disputed(self, *, note="", at=None, save=True):
        at = at or timezone.now()
        self.disputed_at = at
        self.lifecycle_status = self.ServiceLifecycleStatus.DISPUTED
        if note:
            self.operational_note = (note or "")[:2000]
        if save:
            self.save(
                update_fields=["disputed_at", "lifecycle_status", "operational_note"]
            )
        return self

    def get_material_cost_total(self):
        total = (
            self.material_usages.aggregate(total=models.Sum("total_cost"))["total"] or 0
        )
        return int(total or 0)

    def save(self, *args, **kwargs):
        if self.service_id:
            if not self.scheduled_duration_minutes:
                self.scheduled_duration_minutes = int(
                    getattr(self.service, "duration_minutes", 0) or 30
                )
            if not self.buffer_minutes:
                self.buffer_minutes = int(
                    getattr(self.service, "buffer_minutes", 0) or 0
                )
        if self.date and self.time and self.scheduled_duration_minutes:
            start_dt = datetime.combine(self.date, self.time)
            service_end_dt = start_dt + timedelta(
                minutes=int(self.scheduled_duration_minutes or 0)
            )
            occupied_dt = service_end_dt + timedelta(
                minutes=int(self.buffer_minutes or 0)
            )
            if not self.end_time:
                self.end_time = service_end_dt.time()
            self.occupied_until = occupied_dt.time()
        return super().save(*args, **kwargs)

    def ensure_material_usage_from_template(self, *, recorded_by=None):
        """
        قالب مواد مصرفی خدمت را برای این آیتم رزرو به مواد مصرفی واقعی تبدیل می‌کند.
        اگر قبلاً برای یک ماده مصرفی رکورد ثبت شده باشد، دوباره ایجاد نمی‌کند.
        """
        from apps.services.models import ServiceMaterialTemplate

        existing_material_ids = set(
            self.material_usages.values_list("material_id", flat=True)
        )

        templates = (
            ServiceMaterialTemplate.objects.filter(
                salon=self.salon,
                service=self.service,
                is_active=True,
            )
            .select_related("material")
            .order_by("id")
        )

        created_items = []

        for template in templates:
            if template.material_id in existing_material_ids:
                continue

            usage = AppointmentMaterialUsage.objects.create(
                order_detail=self,
                source_template=template,
                material=template.material,
                quantity=template.default_quantity,
                unit_cost=template.resolved_unit_cost,
                paid_by=template.paid_by,
                recorded_by=recorded_by,
            )
            created_items.append(usage)

        return created_items

    class Meta:
        constraints = []
        indexes = [
            models.Index(
                fields=["salon", "date", "time"], name="orderdetail_salon_dt_idx"
            ),
            models.Index(
                fields=["stylist", "date", "time"], name="orderdetail_stylist_dt_idx"
            ),
            models.Index(
                fields=["lifecycle_status", "date"], name="orderdetail_lifecycle_dt_idx"
            ),
            models.Index(fields=["no_show_pending_at"], name="orddet_no_show_pend_idx"),
        ]


class DelayPolicy(models.Model):
    salon = models.OneToOneField(
        Salon,
        on_delete=models.CASCADE,
        related_name="delay_policy",
        verbose_name="سالن",
    )
    grace_period_minutes = models.PositiveIntegerField(
        default=10, verbose_name="مهلت قابل قبول تاخیر مشتری"
    )
    no_show_after_minutes = models.PositiveIntegerField(
        default=20, verbose_name="ثبت عدم حضور بعد از چند دقیقه"
    )
    no_show_dispute_window_hours = models.PositiveIntegerField(
        default=12, verbose_name="مهلت بررسی/اعتراض عدم حضور"
    )
    default_service_buffer_minutes = models.PositiveIntegerField(
        default=10, verbose_name="بافر پیش‌فرض خدمات"
    )
    customer_facing_text = models.TextField(
        blank=True, default="", verbose_name="متن قابل نمایش قوانین تاخیر به مشتری"
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    def __str__(self):
        return f"قوانین تاخیر {self.salon}"

    class Meta:
        verbose_name = "قانون تاخیر سالن"
        verbose_name_plural = "قوانین تاخیر سالن‌ها"


class AppointmentEvent(models.Model):
    class EventType(models.TextChoices):
        CREATED = "created", "ثبت رزرو"
        STYLIST_CONFIRMED = "stylist_confirmed", "تایید آرایشگر"
        STYLIST_REJECTED = "stylist_rejected", "رد آرایشگر"
        CLIENT_LATE = "client_late", "ثبت تاخیر مشتری"
        CUSTOMER_ARRIVED = "customer_arrived", "رسیدن مشتری"
        SERVICE_STARTED = "service_started", "شروع خدمت"
        SERVICE_OVERRUN = "service_overrun", "طولانی‌شدن خدمت"
        SERVICE_COMPLETED = "service_completed", "پایان خدمت"
        NO_SHOW_PENDING = "no_show_pending", "عدم حضور در انتظار بررسی"
        NO_SHOW_CONFIRMED = "no_show_confirmed", "عدم حضور تایید شده"
        DISPUTED = "disputed", "اختلاف"
        STATUS_CHANGED = "status_changed", "تغییر وضعیت"
        NOTE = "note", "یادداشت"

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="appointment_events",
        verbose_name="سفارش",
    )
    order_detail = models.ForeignKey(
        OrderDetail,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name="آیتم رزرو",
        null=True,
        blank=True,
    )
    salon = models.ForeignKey(
        Salon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointment_events",
        verbose_name="سالن",
    )
    stylist = models.ForeignKey(
        Stylist,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointment_events",
        verbose_name="آرایشگر",
    )
    event_type = models.CharField(
        max_length=64, choices=EventType.choices, verbose_name="نوع رویداد"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="appointment_events",
        verbose_name="انجام‌دهنده",
    )
    old_status = models.CharField(
        max_length=64, blank=True, default="", verbose_name="وضعیت قبلی"
    )
    new_status = models.CharField(
        max_length=64, blank=True, default="", verbose_name="وضعیت جدید"
    )
    note = models.TextField(blank=True, default="", verbose_name="یادداشت")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="فراداده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "رویداد نوبت"
        verbose_name_plural = "رویدادهای نوبت"
        indexes = [
            models.Index(
                fields=["order", "created_at"], name="appt_event_order_time_idx"
            ),
            models.Index(
                fields=["order_detail", "created_at"], name="appt_event_detail_time_idx"
            ),
            models.Index(
                fields=["event_type", "created_at"], name="appt_event_type_time_idx"
            ),
        ]

    def __str__(self):
        return f"{self.get_event_type_display()} - {self.order_id}"


# --------------------------------------------------------------------------------------
class AppointmentMaterialUsage(models.Model):
    class PaidBy(models.TextChoices):
        SALON = "salon", "هزینه با سالن"
        STYLIST = "stylist", "هزینه با آرایشگر"
        SHARED = "shared", "هزینه مشترک"

    order_detail = models.ForeignKey(
        OrderDetail,
        on_delete=models.CASCADE,
        related_name="material_usages",
        verbose_name="آیتم رزرو",
    )
    source_template = models.ForeignKey(
        "services.ServiceMaterialTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointment_usages",
        verbose_name="قالب اولیه مواد",
    )
    material = models.ForeignKey(
        "services.MaterialItem",
        on_delete=models.PROTECT,
        related_name="appointment_usages",
        verbose_name="ماده مصرفی",
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1.00"),
        verbose_name="مقدار مصرف‌شده",
    )
    unit_cost = models.PositiveIntegerField(
        default=0,
        verbose_name="هزینه هر واحد",
    )
    total_cost = models.PositiveIntegerField(
        default=0,
        verbose_name="هزینه کل",
    )
    paid_by = models.CharField(
        max_length=20,
        choices=PaidBy.choices,
        default=PaidBy.SALON,
        verbose_name="پرداخت‌کننده هزینه مواد",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_material_usages",
        verbose_name="ثبت‌کننده",
    )
    note = models.TextField(blank=True, default="", verbose_name="یادداشت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    def calculate_total_cost(self):
        amount = Decimal(self.quantity or 0) * Decimal(self.unit_cost or 0)
        return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def clean(self):
        super().clean()

        if self.order_detail_id and self.material_id:
            if self.material.salon_id != self.order_detail.salon_id:
                raise ValidationError("ماده مصرفی باید متعلق به سالن همین رزرو باشد.")

        if self.quantity is not None and self.quantity < 0:
            raise ValidationError("مقدار مصرف نمی‌تواند منفی باشد.")

        if self.order_detail_id and getattr(
            self.order_detail, "financial_finalized_at", None
        ):
            raise ValidationError(
                "بعد از نهایی شدن مالی، مواد مصرفی این خدمت قابل تغییر نیست."
            )

    def save(self, *args, **kwargs):
        self.total_cost = self.calculate_total_cost()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.material} - {self.order_detail}"

    class Meta:
        verbose_name = "مواد مصرفی رزرو"
        verbose_name_plural = "مواد مصرفی رزروها"
        db_table = "o_appointment_material_usage"
        constraints = [
            models.UniqueConstraint(
                fields=["order_detail", "material"],
                name="uniq_mat_usage_orderdet",
            ),
            models.CheckConstraint(
                check=models.Q(quantity__gte=0),
                name="appt_mat_qty_gte0",
            ),
            models.CheckConstraint(
                check=models.Q(unit_cost__gte=0),
                name="appt_mat_unit_cost_gte0",
            ),
            models.CheckConstraint(
                check=models.Q(total_cost__gte=0),
                name="appt_mat_total_gte0",
            ),
        ]
        indexes = [
            models.Index(
                fields=["order_detail", "material"], name="appt_mat_usage_lookup_idx"
            ),
            models.Index(fields=["paid_by"], name="appt_mat_paid_by_idx"),
        ]


# --------------------------------------------------------------------------------------------
class AppointmentNotification(models.Model):
    AUDIENCE_CHOICES = [
        ("customer", "مشتری"),
        ("stylist", "آرایشگر"),
        ("manager", "مدیر سالن"),
        ("system", "سیستم"),
    ]
    CHANNEL_CHOICES = [
        ("dashboard", "داشبورد"),
        ("email", "ایمیل"),
        ("sms", "پیامک"),
        ("system", "سیستم"),
    ]
    EVENT_CHOICES = [
        ("booking_created", "رزرو ثبت شد"),
        ("booking_paid", "پرداخت رزرو ثبت شد"),
        ("stylist_confirmed", "تایید آرایشگر"),
        ("stylist_rejected", "رد رزرو توسط آرایشگر"),
        ("reminder_scheduled", "یادآوری زمان‌بندی شد"),
        ("reminder_due", "یادآوری نزدیک نوبت"),
        ("customer_arrived", "مشتری رسید"),
        ("service_started", "شروع خدمت"),
        ("service_completed", "پایان خدمت"),
        ("financial_finalized", "نهایی شدن محاسبات مالی"),
        ("client_late", "ثبت تاخیر مشتری"),
        ("client_checked_in_late", "رسیدن مشتری با تاخیر"),
        ("no_show_pending_review", "عدم حضور در انتظار بررسی"),
        ("no_show_confirmed", "عدم حضور تایید شده"),
        ("service_overrun_risk", "ریسک طولانی‌شدن خدمت"),
        ("service_overrun", "طولانی‌شدن خدمت"),
        ("appointment_disputed", "اختلاف نوبت"),
        ("pay_in_salon_pending", "پرداخت در سالن"),
        ("payment_completed", "پرداخت تکمیل شد"),
        ("review_requested", "درخواست نظرسنجی"),
        ("review_completed", "نظرسنجی ثبت شد"),
    ]
    DELIVERY_CHOICES = [
        ("sent", "ارسال شد"),
        ("queued", "در صف"),
        ("pending_setup", "نیازمند تنظیمات"),
        ("failed", "ناموفق"),
        ("skipped", "ارسال نشد"),
    ]

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="سفارش",
    )
    order_detail = models.ForeignKey(
        OrderDetail,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="آیتم رزرو",
        null=True,
        blank=True,
    )
    salon = models.ForeignKey(
        Salon,
        on_delete=models.CASCADE,
        related_name="appointment_notifications",
        verbose_name="سالن",
        null=True,
        blank=True,
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="appointment_notifications",
        verbose_name="مشتری",
        null=True,
        blank=True,
    )
    stylist = models.ForeignKey(
        Stylist,
        on_delete=models.CASCADE,
        related_name="appointment_notifications",
        verbose_name="آرایشگر",
        null=True,
        blank=True,
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointment_notifications",
        verbose_name="کاربر هدف",
    )
    audience_role = models.CharField(
        max_length=20, choices=AUDIENCE_CHOICES, verbose_name="گروه هدف"
    )
    channel = models.CharField(
        max_length=20, choices=CHANNEL_CHOICES, verbose_name="کانال"
    )
    event_type = models.CharField(
        max_length=32, choices=EVENT_CHOICES, verbose_name="نوع رویداد"
    )
    title = models.CharField(max_length=140, verbose_name="عنوان")
    body = models.TextField(blank=True, default="", verbose_name="متن")
    delivery_status = models.CharField(
        max_length=20,
        choices=DELIVERY_CHOICES,
        default="sent",
        verbose_name="وضعیت ارسال",
    )
    is_read = models.BooleanField(default=False, verbose_name="خوانده شد")
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان خواندن")
    meta = models.JSONField(default=dict, blank=True, verbose_name="فراداده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")

    def __str__(self):
        return f"{self.title} - {self.get_audience_role_display()}"

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "اعلان رزرو"
        verbose_name_plural = "اعلان‌های رزرو"
