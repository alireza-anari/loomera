from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from apps.accounts.models import Stylist
from apps.services.models import Services
from django.utils.text import slugify

class DiscountType(models.TextChoices):
    """Shared discount source/type choices used by discount services.

    Some service layers import ``DiscountType`` directly from models while
    tracking models also define nested ``SourceType`` choices. Keeping this
    top-level class avoids import errors and provides one stable enum for
    coupon, basket and campaign calculations.
    """

    COUPON = "coupon", "کد تخفیف"
    BASKET = "basket", "سبد تخفیف"
    CAMPAIGN = "campaign", "کمپین"
    MANUAL = "manual", "دستی"


class DiscountValueType(models.TextChoices):
    PERCENTAGE = "percentage", "درصدی"
    FIXED_AMOUNT = "fixed_amount", "مبلغ ثابت"


class DiscountVisibility(models.TextChoices):
    PRIVATE_CODE = "private_code", "کد خصوصی"
    PUBLIC_CODE = "public_code", "کد عمومی"
    SEARCH_BADGE = "search_badge", "نمایش در کارت و جستجو"
    CHECKOUT_ONLY = "checkout_only", "فقط در تسویه"


class DiscountFundedBy(models.TextChoices):
    SALON = "salon", "سالن"
    PLATFORM = "platform", "Loomera"
    SHARED = "shared", "مشترک"


class DiscountStaffShareImpact(models.TextChoices):
    AFTER_DISCOUNT = "after_discount", "سهم از مبلغ بعد از تخفیف"
    BEFORE_DISCOUNT = "before_discount", "سهم از مبلغ قبل از تخفیف"
    SALON_ABSORBS = "salon_absorbs", "تخفیف از سهم سالن کسر شود"
    PLATFORM_FUNDED = "platform_funded", "تأمین توسط پلتفرم"


class DiscountStackingChoice(models.TextChoices):
    NOT_STACKABLE = "not_stackable", "قابل ترکیب نیست"
    STACK_WITH_SERVICE = "stack_with_service", "قابل ترکیب با تخفیف خدمت"
    STACK_WITH_PLATFORM = "stack_with_platform", "قابل ترکیب با کمپین پلتفرم"
    BEST_ONLY = "best_only", "فقط بهترین تخفیف"


class Coupon(models.Model):
    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="coupons",
        verbose_name="سالن",
    )
    coupon_code = models.CharField(max_length=100, verbose_name="کد تخفیف ")
    start_date = models.DateTimeField(verbose_name="تاریخ شروع")
    end_date = models.DateTimeField(verbose_name="تاریخ پایان")
    discount = models.IntegerField(
        verbose_name="درصد تخفیف",
        validators=(MinValueValidator(0), MaxValueValidator(100)),
    )
    max_discount_amount = models.PositiveIntegerField(
        default=0,
        verbose_name="سقف مبلغ تخفیف (تومان)",
        help_text="اگر صفر باشد، سقف مبلغی برای این کد در نظر گرفته نمی‌شود.",
    )
    is_active = models.BooleanField(default=False, verbose_name="وضعیت")
    description = models.TextField(blank=True, default="", verbose_name="توضیحات")
    campaign = models.ForeignKey(
        "discounts.DiscountCampaign",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legacy_coupon_links",
        verbose_name="کمپین",
    )
    discount_type = models.CharField(
        max_length=32,
        choices=DiscountValueType.choices,
        default=DiscountValueType.PERCENTAGE,
        verbose_name="نوع تخفیف",
    )
    discount_value = models.PositiveIntegerField(default=0, verbose_name="مقدار تخفیف")
    min_order_amount = models.PositiveIntegerField(
        default=0, verbose_name="حداقل مبلغ رزرو"
    )
    max_order_amount = models.PositiveIntegerField(
        default=0, verbose_name="حداکثر مبلغ رزرو"
    )
    total_usage_limit = models.PositiveIntegerField(
        default=0, verbose_name="حداکثر استفاده کل"
    )
    per_customer_usage_limit = models.PositiveIntegerField(
        default=0, verbose_name="حداکثر استفاده هر مشتری"
    )
    first_booking_only = models.BooleanField(
        default=False, verbose_name="فقط اولین رزرو کاربر"
    )
    first_salon_booking_only = models.BooleanField(
        default=False, verbose_name="فقط اولین رزرو کاربر در این سالن"
    )
    visibility = models.CharField(
        max_length=32,
        choices=DiscountVisibility.choices,
        default=DiscountVisibility.CHECKOUT_ONLY,
        verbose_name="نوع نمایش",
    )
    funded_by = models.CharField(
        max_length=32,
        choices=DiscountFundedBy.choices,
        default=DiscountFundedBy.SALON,
        verbose_name="تأمین‌کننده هزینه",
    )
    salon_funding_percent = models.PositiveSmallIntegerField(
        default=100, verbose_name="درصد سهم سالن از هزینه تخفیف"
    )
    platform_funding_percent = models.PositiveSmallIntegerField(
        default=0, verbose_name="درصد سهم Loomera از هزینه تخفیف"
    )
    stacking_policy = models.CharField(
        max_length=32,
        choices=DiscountStackingChoice.choices,
        default=DiscountStackingChoice.STACK_WITH_SERVICE,
        verbose_name="قانون ترکیب",
    )
    staff_share_impact = models.CharField(
        max_length=32,
        choices=DiscountStaffShareImpact.choices,
        default=DiscountStaffShareImpact.AFTER_DISCOUNT,
        verbose_name="اثر روی سهم آرایشگر",
    )
    eligible_payment_methods = models.JSONField(
        blank=True, default=list, verbose_name="روش‌های پرداخت مجاز"
    )
    archived_at = models.DateTimeField(blank=True, null=True, verbose_name="زمان آرشیو")
    terms_text = models.TextField(
        blank=True, default="", verbose_name="قوانین قابل نمایش"
    )
    metadata = models.JSONField(blank=True, default=dict, verbose_name="متادیتا")
    is_archived = models.BooleanField(default=False, verbose_name="آرشیوشده")

    def __str__(self):
        return self.coupon_code

    @property
    def effective_discount_type(self):
        return self.discount_type or DiscountValueType.PERCENTAGE

    @property
    def effective_discount_value(self):
        return int(self.discount_value or self.discount or 0)

    @property
    def effective_discount(self):
        return self.effective_discount_value

    @property
    def effective_max_discount_amount(self):
        return int(self.max_discount_amount or 0)

    @property
    def effective_cap_amount(self):
        return self.effective_max_discount_amount

    @property
    def effective_discount_label(self):
        value = self.effective_discount_value
        if not value:
            return ""
        if self.effective_discount_type == DiscountValueType.FIXED_AMOUNT:
            return f"{value:,} تومان تخفیف"
        return f"{value}٪ تخفیف"

    def save(self, *args, **kwargs):
        if not self.discount_value:
            self.discount_value = int(self.discount or 0)
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = "کد تخفیف"
        verbose_name_plural = "کد های تخفیف"
        constraints = [
            models.UniqueConstraint(fields=["salon", "coupon_code"], name="unique_coupon_per_salon"),
        ]


class DiscountBasket(models.Model):
    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="discount_baskets",
        verbose_name="سالن",
    )
    discount_title = models.CharField(max_length=100, verbose_name="عنوان تخفیف")
    start_date = models.DateTimeField(verbose_name="تاریخ شروع")
    end_date = models.DateTimeField(verbose_name="تاریخ پایان")
    discount = models.IntegerField(
        verbose_name="درصد تخفیف",
        validators=(MinValueValidator(0), MaxValueValidator(100)),
    )
    max_discount_amount = models.PositiveIntegerField(
        default=0,
        verbose_name="سقف مبلغ تخفیف (تومان)",
        help_text="اگر صفر باشد، سقف مبلغی برای این سبد تخفیف در نظر گرفته نمی‌شود.",
    )
    is_active = models.BooleanField(default=False, verbose_name="وضعیت")
    is_archived = models.BooleanField(default=False, verbose_name="آرشیوشده")
    description = models.TextField(blank=True, default="", verbose_name="توضیحات")
    campaign = models.ForeignKey(
        "discounts.DiscountCampaign",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legacy_basket_links",
        verbose_name="کمپین",
    )
    discount_type = models.CharField(
        max_length=32,
        choices=DiscountValueType.choices,
        default=DiscountValueType.PERCENTAGE,
        verbose_name="نوع تخفیف",
    )
    discount_value = models.PositiveIntegerField(default=0, verbose_name="مقدار تخفیف")
    min_order_amount = models.PositiveIntegerField(default=0, verbose_name="حداقل مبلغ رزرو")
    visibility = models.CharField(
        max_length=32,
        choices=DiscountVisibility.choices,
        default=DiscountVisibility.SEARCH_BADGE,
        verbose_name="نوع نمایش",
    )
    funded_by = models.CharField(
        max_length=32,
        choices=DiscountFundedBy.choices,
        default=DiscountFundedBy.SALON,
        verbose_name="تأمین‌کننده هزینه",
    )
    salon_funding_percent = models.PositiveSmallIntegerField(default=100, verbose_name="درصد سهم سالن از هزینه تخفیف")
    platform_funding_percent = models.PositiveSmallIntegerField(default=0, verbose_name="درصد سهم Loomera از هزینه تخفیف")
    stacking_policy = models.CharField(
        max_length=32,
        choices=DiscountStackingChoice.choices,
        default=DiscountStackingChoice.STACK_WITH_SERVICE,
        verbose_name="قانون ترکیب",
    )
    staff_share_impact = models.CharField(
        max_length=32,
        choices=DiscountStaffShareImpact.choices,
        default=DiscountStaffShareImpact.AFTER_DISCOUNT,
        verbose_name="اثر روی سهم آرایشگر",
    )
    archived_at = models.DateTimeField(blank=True, null=True, verbose_name="زمان آرشیو")
    terms_text = models.TextField(blank=True, default="", verbose_name="قوانین قابل نمایش")
    metadata = models.JSONField(blank=True, default=dict, verbose_name="متادیتا")

    def __str__(self):
        return self.discount_title

    def save(self, *args, **kwargs):
        if not self.discount_value:
            self.discount_value = int(self.discount or 0)
        super().save(*args, **kwargs)

    @property
    def effective_discount_type(self):
        return getattr(self, "discount_type", "") or "percentage"

    @property
    def effective_discount_value(self):
        return int(getattr(self, "discount_value", None) or self.discount or 0)

    @property
    def effective_discount(self):
        return self.effective_discount_value

    @property
    def effective_max_discount_amount(self):
        return int(getattr(self, "max_discount_amount", 0) or 0)

    @property
    def effective_cap_amount(self):
        return self.effective_max_discount_amount

    @property
    def effective_discount_title(self):
        return self.discount_title

    @property
    def effective_title(self):
        return self.discount_title

    @property
    def effective_discount_label(self):
        value = self.effective_discount_value
        if not value:
            return ""
        if self.effective_discount_type in ("fixed", "amount", "fixed_amount"):
            return f"{value:,} تومان تخفیف"
        return f"{value}٪ تخفیف"

    @property
    def effective_discount_caption(self):
        cap = self.effective_max_discount_amount
        return f"تا سقف {cap:,} تومان" if cap else ""

    class Meta:
        verbose_name = "سبد تخفیف "
        verbose_name_plural = "سبدهای تخفیف "


class DiscountBasketDetails(models.Model):
    discount_basket = models.ForeignKey(
        DiscountBasket,
        on_delete=models.CASCADE,
        related_name="discount_basket_details1",
        verbose_name="سبد تخفیف",
    )
    service = models.ForeignKey(
        Services,
        on_delete=models.CASCADE,
        related_name="discount_basket_details2",
        verbose_name="خدمت",
    )
    stylist = models.ForeignKey(
        Stylist,
        on_delete=models.CASCADE,
        related_name="discount_basket_details3",
        verbose_name="آرایشگر",
        null=True,
        blank=True,
    )

    @property
    def is_active_now(self):
        now = timezone.now()
        return (
            self.is_active
            and not self.is_archived
            and self.start_date <= now <= self.end_date
        )

    class Meta:
        verbose_name = "جزییات سبد تخفیف "
        verbose_name_plural = "جزئیات سبد تخفیف"
        constraints = [
            models.UniqueConstraint(
                fields=["discount_basket", "service", "stylist"],
                name="disc_basket_svc_sty_u",
            ),
        ]


class DiscountCampaign(models.Model):
    class CampaignType(models.TextChoices):
        COUPON = "coupon", "کد تخفیف"
        BASKET = "basket", "سبد تخفیف"
        MIXED = "mixed", "کمپین ترکیبی"

    class OwnerType(models.TextChoices):
        SALON = "salon", "سالن"
        PLATFORM = "platform", "Loomera"
        PARTNER = "partner", "همکار"

    class FundedBy(models.TextChoices):
        SALON = "salon", "سالن"
        PLATFORM = "platform", "Loomera"
        SHARED = "shared", "مشترک"

    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        ACTIVE = "active", "فعال"
        PAUSED = "paused", "متوقف"
        ARCHIVED = "archived", "آرشیو شده"

    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="discount_campaigns",
        verbose_name="سالن",
    )
    title = models.CharField(max_length=160, verbose_name="عنوان کمپین")
    slug = models.SlugField(
        max_length=180,
        blank=True,
        default="",
        allow_unicode=True,
        verbose_name="اسلاگ",
    )

    # فیلدهای legacy که در دیتابیس فعلی وجود دارند
    owner_type = models.CharField(
        max_length=32,
        choices=OwnerType.choices,
        default=OwnerType.SALON,
        verbose_name="مالک کمپین",
    )
    funded_by = models.CharField(
        max_length=32,
        choices=FundedBy.choices,
        default=FundedBy.SALON,
        verbose_name="تأمین‌کننده هزینه",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="وضعیت",
    )
    internal_note = models.TextField(
        blank=True, default="", verbose_name="یادداشت داخلی"
    )
    is_featured = models.BooleanField(default=False, verbose_name="ویژه")
    created_by = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_discount_campaigns",
        verbose_name="ایجادکننده",
    )

    # فیلدهای جدید داشبورد
    campaign_type = models.CharField(
        max_length=20,
        choices=CampaignType.choices,
        default=CampaignType.MIXED,
        verbose_name="نوع کمپین",
    )
    start_date = models.DateTimeField(null=True, blank=True, verbose_name="تاریخ شروع")
    end_date = models.DateTimeField(null=True, blank=True, verbose_name="تاریخ پایان")
    coupons = models.ManyToManyField(
        Coupon,
        blank=True,
        related_name="campaigns",
        verbose_name="کدهای تخفیف",
    )
    baskets = models.ManyToManyField(
        DiscountBasket,
        blank=True,
        related_name="campaigns",
        verbose_name="سبدهای تخفیف",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    is_archived = models.BooleanField(default=False, verbose_name="آرشیوشده")
    description = models.TextField(blank=True, default="", verbose_name="توضیحات")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین ویرایش")

    @property
    def is_active_now(self):
        now = timezone.now()
        return (
            self.is_active
            and not self.is_archived
            and self.start_date
            and self.end_date
            and self.start_date <= now <= self.end_date
        )

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = (
                slugify(self.title or "campaign", allow_unicode=True) or "campaign"
            )
            salon_part = self.salon_id or "global"
            timestamp_part = int(timezone.now().timestamp())
            self.slug = f"{base_slug}-{salon_part}-{timestamp_part}"[:180]

        if not self.owner_type:
            self.owner_type = self.OwnerType.SALON

        if not self.funded_by:
            self.funded_by = self.FundedBy.SALON

        if self.is_archived:
            self.status = self.Status.ARCHIVED
        elif self.is_active:
            self.status = self.Status.ACTIVE
        elif not self.status:
            self.status = self.Status.PAUSED

        if self.internal_note is None:
            self.internal_note = ""

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "کمپین تخفیف"
        verbose_name_plural = "کمپین‌های تخفیف"
        ordering = ["-is_active", "-start_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["salon", "title"],
                name="disc_campaign_title_u",
            ),
        ]


class DiscountStackingPolicy(models.Model):
    """Salon-level rules for combining coupons, baskets and campaigns.

    The discount service imports this model while calculating checkout totals.
    Defaults are intentionally conservative: use the best single discount unless
    a salon explicitly enables stacking.
    """

    BEST_DISCOUNT_ONLY = "best_discount_only"
    STACK_ALL = "stack_all"
    COUPON_THEN_BASKET = "coupon_then_basket"
    BASKET_THEN_COUPON = "basket_then_coupon"
    CAMPAIGN_PRIORITY = "campaign_priority"

    class StackingMode(models.TextChoices):
        BEST_DISCOUNT_ONLY = "best_discount_only", "بهترین تخفیف فقط"
        STACK_ALL = "stack_all", "تجمیع همه تخفیف‌ها"
        COUPON_THEN_BASKET = "coupon_then_basket", "اول کد تخفیف سپس سبد"
        BASKET_THEN_COUPON = "basket_then_coupon", "اول سبد سپس کد تخفیف"
        CAMPAIGN_PRIORITY = "campaign_priority", "اولویت با کمپین"

    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="discount_stacking_policies",
        verbose_name="سالن",
        help_text="اگر خالی باشد، قانون به عنوان پیش‌فرض عمومی قابل استفاده است.",
    )
    title = models.CharField(max_length=140, default="قانون تجمیع تخفیف", verbose_name="عنوان")
    policy = models.CharField(
        max_length=40,
        choices=StackingMode.choices,
        default=StackingMode.BEST_DISCOUNT_ONLY,
        verbose_name="سیاست تجمیع",
    )
    stacking_mode = models.CharField(
        max_length=40,
        choices=StackingMode.choices,
        default=StackingMode.BEST_DISCOUNT_ONLY,
        verbose_name="حالت تجمیع",
        help_text="برای سازگاری با سرویس‌های جدید و قدیمی همزمان نگهداری می‌شود.",
    )
    allow_coupon_with_basket = models.BooleanField(default=False, verbose_name="اجازه ترکیب کد و سبد")
    allow_coupon_with_campaign = models.BooleanField(default=False, verbose_name="اجازه ترکیب کد و کمپین")
    allow_basket_with_campaign = models.BooleanField(default=False, verbose_name="اجازه ترکیب سبد و کمپین")
    max_discount_sources = models.PositiveSmallIntegerField(default=1, verbose_name="حداکثر تعداد منابع تخفیف")
    priority = models.PositiveSmallIntegerField(default=100, verbose_name="اولویت")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    metadata = models.JSONField(blank=True, default=dict, verbose_name="متادیتا")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین ویرایش")

    def save(self, *args, **kwargs):
        if not self.stacking_mode:
            self.stacking_mode = self.policy
        if not self.policy:
            self.policy = self.stacking_mode
        super().save(*args, **kwargs)

    @property
    def is_best_only(self):
        return self.policy == self.StackingMode.BEST_DISCOUNT_ONLY or self.stacking_mode == self.StackingMode.BEST_DISCOUNT_ONLY

    def can_stack(self, first: str, second: str) -> bool:
        pair = {first, second}
        if self.policy == self.StackingMode.STACK_ALL or self.stacking_mode == self.StackingMode.STACK_ALL:
            return True
        if pair == {"coupon", "basket"}:
            return self.allow_coupon_with_basket
        if pair == {"coupon", "campaign"}:
            return self.allow_coupon_with_campaign
        if pair == {"basket", "campaign"}:
            return self.allow_basket_with_campaign
        return False

    def __str__(self):
        salon_name = getattr(self.salon, "salon_name", "عمومی") if self.salon_id else "عمومی"
        return f"{self.title} - {salon_name}"

    class Meta:
        verbose_name = "قانون تجمیع تخفیف"
        verbose_name_plural = "قوانین تجمیع تخفیف"
        ordering = ["-is_active", "priority", "-updated_at"]
        indexes = [
            models.Index(fields=["salon", "is_active"], name="disc_stack_salon_active_idx"),
            models.Index(fields=["policy", "is_active"], name="disc_stack_policy_active_idx"),
        ]


class DiscountTrackingManager(models.Manager):
    """Tolerant manager for discount tracking records.

    Some service layers pass optional diagnostic fields when creating discount
    snapshots/redemptions. Unknown fields are preserved inside ``metadata`` so
    checkout never crashes because of a harmless extra key.
    """

    def _split_known_kwargs(self, kwargs):
        valid_names = {
            field.name
            for field in self.model._meta.get_fields()
            if not getattr(field, "many_to_many", False) and not getattr(field, "one_to_many", False)
        }
        known = {}
        extra = {}
        for key, value in kwargs.items():
            if key in valid_names:
                known[key] = value
            else:
                extra[key] = value
        if extra:
            metadata = dict(known.get("metadata") or {})
            metadata.update({key: str(value) for key, value in extra.items()})
            known["metadata"] = metadata
        return known

    def create(self, **kwargs):
        return super().create(**self._split_known_kwargs(kwargs))


class DiscountSnapshot(models.Model):
    class SourceType(models.TextChoices):
        COUPON = DiscountType.COUPON
        BASKET = DiscountType.BASKET
        CAMPAIGN = DiscountType.CAMPAIGN
        MANUAL = DiscountType.MANUAL

    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discount_snapshots",
        verbose_name="سالن",
    )
    customer = models.ForeignKey(
        "accounts.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discount_snapshots",
        verbose_name="مشتری",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discount_snapshots",
        verbose_name="سفارش",
    )
    order_detail = models.ForeignKey(
        "orders.OrderDetail",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discount_snapshots",
        verbose_name="آیتم سفارش",
    )
    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discount_snapshots",
        verbose_name="کد تخفیف",
    )
    basket = models.ForeignKey(
        DiscountBasket,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discount_snapshots",
        verbose_name="سبد تخفیف",
    )
    campaign = models.ForeignKey(
        DiscountCampaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discount_snapshots",
        verbose_name="کمپین",
    )
    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        default=SourceType.COUPON,
        verbose_name="نوع تخفیف",
    )
    code = models.CharField(max_length=120, blank=True, default="", verbose_name="کد/شناسه تخفیف")
    title = models.CharField(max_length=180, blank=True, default="", verbose_name="عنوان تخفیف")
    percent = models.PositiveIntegerField(default=0, verbose_name="درصد")
    discount_percent = models.PositiveIntegerField(default=0, verbose_name="درصد تخفیف")
    amount = models.PositiveIntegerField(default=0, verbose_name="مبلغ")
    discount_amount = models.PositiveIntegerField(default=0, verbose_name="مبلغ تخفیف")
    max_discount_amount = models.PositiveIntegerField(default=0, verbose_name="سقف مبلغ تخفیف")
    eligible_subtotal = models.PositiveIntegerField(default=0, verbose_name="مبلغ مشمول تخفیف")
    order_total_before_discount = models.PositiveIntegerField(default=0, verbose_name="مبلغ سفارش قبل از تخفیف")
    order_total_after_discount = models.PositiveIntegerField(default=0, verbose_name="مبلغ سفارش بعد از تخفیف")
    payload = models.JSONField(blank=True, default=dict, verbose_name="جزئیات محاسبه")
    metadata = models.JSONField(blank=True, default=dict, verbose_name="متادیتا")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین ویرایش")

    objects = DiscountTrackingManager()

    def __str__(self):
        return self.title or self.code or f"snapshot #{self.pk}"

    class Meta:
        verbose_name = "اسنپ‌شات تخفیف"
        verbose_name_plural = "اسنپ‌شات‌های تخفیف"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["order", "source_type"], name="disc_snap_order_source_idx"),
            models.Index(fields=["coupon", "customer"], name="disc_snap_coupon_customer_idx"),
        ]


class DiscountRedemption(models.Model):
    class SourceType(models.TextChoices):
        COUPON = DiscountType.COUPON
        BASKET = DiscountType.BASKET
        CAMPAIGN = DiscountType.CAMPAIGN
        MANUAL = DiscountType.MANUAL

    class Status(models.TextChoices):
        APPLIED = "applied", "اعمال‌شده"
        RESERVED = "reserved", "رزرو شده"
        CANCELLED = "cancelled", "لغو شده"
        REFUNDED = "refunded", "عودت شده"

    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discount_redemptions",
        verbose_name="سالن",
    )
    customer = models.ForeignKey(
        "accounts.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discount_redemptions",
        verbose_name="مشتری",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discount_redemptions",
        verbose_name="سفارش",
    )
    order_detail = models.ForeignKey(
        "orders.OrderDetail",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discount_redemptions",
        verbose_name="آیتم سفارش",
    )
    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="redemptions",
        verbose_name="کد تخفیف",
    )
    basket = models.ForeignKey(
        DiscountBasket,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="redemptions",
        verbose_name="سبد تخفیف",
    )
    campaign = models.ForeignKey(
        DiscountCampaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="redemptions",
        verbose_name="کمپین",
    )
    snapshot = models.ForeignKey(
        DiscountSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="redemptions",
        verbose_name="اسنپ‌شات تخفیف",
    )
    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        default=SourceType.COUPON,
        verbose_name="نوع تخفیف",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPLIED, verbose_name="وضعیت")
    code = models.CharField(max_length=120, blank=True, default="", verbose_name="کد/شناسه تخفیف")
    title = models.CharField(max_length=180, blank=True, default="", verbose_name="عنوان تخفیف")
    percent = models.PositiveIntegerField(default=0, verbose_name="درصد")
    discount_percent = models.PositiveIntegerField(default=0, verbose_name="درصد تخفیف")
    amount = models.PositiveIntegerField(default=0, verbose_name="مبلغ")
    discount_amount = models.PositiveIntegerField(default=0, verbose_name="مبلغ تخفیف")
    max_discount_amount = models.PositiveIntegerField(default=0, verbose_name="سقف مبلغ تخفیف")
    eligible_subtotal = models.PositiveIntegerField(default=0, verbose_name="مبلغ مشمول تخفیف")
    metadata = models.JSONField(blank=True, default=dict, verbose_name="متادیتا")
    redeemed_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ استفاده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین ویرایش")

    objects = DiscountTrackingManager()

    def __str__(self):
        return f"{self.code or self.title or self.source_type} - {self.discount_amount or self.amount}"

    class Meta:
        verbose_name = "استفاده از تخفیف"
        verbose_name_plural = "استفاده‌های تخفیف"
        ordering = ["-redeemed_at", "-id"]
        indexes = [
            models.Index(fields=["coupon", "customer"], name="disc_red_coupon_customer_idx"),
            models.Index(fields=["order", "source_type"], name="disc_red_order_source_idx"),
            models.Index(fields=["status", "redeemed_at"], name="disc_red_status_date_idx"),
        ]
