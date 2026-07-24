from django.db import models
from django.db.models import Avg
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from middlewares.middlewares import RequestMiddleware
from utils import File_Uploader
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError


def _unique_slug_for_model(instance, source_value, field_name="slug", max_length=180):
    base_slug = slugify(source_value or "item", allow_unicode=True).strip("-") or "item"
    base_slug = base_slug[:max_length].strip("-") or "item"
    slug = base_slug
    counter = 2
    model = instance.__class__
    while model.objects.filter(**{field_name: slug}).exclude(pk=instance.pk).exists():
        suffix = f"-{counter}"
        slug = f"{base_slug[: max_length - len(suffix)]}{suffix}"
        counter += 1
    return slug


# -------------------------------------------------------------------------------------------
# گروه خدمات
class GroupServices(models.Model):
    group_title = models.CharField(max_length=50, verbose_name="عنوان گروه خدمات ")
    slug = models.SlugField(max_length=160, unique=True, allow_unicode=True, blank=True, verbose_name="اسلاگ")
    seo_title = models.CharField(max_length=160, blank=True, default="", verbose_name="عنوان SEO")
    seo_description = models.CharField(max_length=220, blank=True, default="", verbose_name="توضیحات SEO")
    canonical_url = models.URLField(blank=True, default="", verbose_name="Canonical URL")
    allow_indexing = models.BooleanField(default=True, verbose_name="اجازه ایندکس SEO")
    file_upload = File_Uploader("images", "GroupServices")
    group_image = models.ImageField(
        upload_to=file_upload, verbose_name="تصویر گروه خدمات"
    )
    descriptions = models.TextField(blank=True, null=True, verbose_name="توضیحات گروه خدمات ")
    is_active = models.BooleanField(default=True, verbose_name="وضعیت فعال/ غیرفعال", blank=True)
    group_parent = models.ForeignKey(
        "GroupServices",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        verbose_name="والد گروه خدمات",
        related_name="groups",
    )
    registere_date = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")
    published_date = models.DateTimeField(default=timezone.now, verbose_name="زمان انتشار ")
    updated_date = models.DateTimeField(auto_now=True, verbose_name="زمان آخرین ویرایش")

    def get_all_parent_ids(self):
        ids = [self.id]
        parent = self.group_parent
        while parent:
            ids.append(parent.id)
            parent = parent.group_parent
        return ids


    @property
    def effective_seo_title(self):
        return self.seo_title or f"{self.group_title} | خدمات زیبایی در Loomera"

    @property
    def effective_seo_description(self):
        return self.seo_description or (self.descriptions or f"مشاهده خدمات {self.group_title}، قیمت‌ها و سالن‌های ارائه‌دهنده در Loomera.")[:220]

    def get_absolute_url(self):
        return reverse("services:group_services_slug", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug_for_model(self, self.group_title, max_length=150)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.group_title

    class Meta:
        verbose_name = "گروه خدمات"
        verbose_name_plural = "گروه های خدمات "
        db_table = "s_groupservices"


# -------------------------------------------------------------------------------------------
# ویژگی ها
class Feature(models.Model):
    feature_name = models.CharField(max_length=100, verbose_name="نام ویژگی ")
    product_group = models.ManyToManyField(
        GroupServices, verbose_name="گروه خدمات", related_name="features_of_groups"
    )

    def __str__(self):
        return self.feature_name

    class Meta:
        verbose_name = "ویژگی"
        verbose_name_plural = "ویژگی ها"
        db_table = "s_feature"


# -------------------------------------------------------------------------------------------
# خدمات
class Services(models.Model):
    service_name = models.CharField(max_length=500, verbose_name="نام خدمات")
    slug = models.SlugField(max_length=200, unique=True, allow_unicode=True, blank=True, verbose_name="اسلاگ")
    seo_title = models.CharField(max_length=160, blank=True, default="", verbose_name="عنوان SEO")
    seo_description = models.CharField(max_length=220, blank=True, default="", verbose_name="توضیحات SEO")
    canonical_url = models.URLField(blank=True, default="", verbose_name="Canonical URL")
    allow_indexing = models.BooleanField(default=True, verbose_name="اجازه ایندکس SEO")
    is_platform_catalog = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="خدمت کاتالوگ پلتفرم",
        help_text="اگر غیرفعال باشد، این رکورد نسخه اختصاصی یک مجموعه از خدمت پایه است و در کاتالوگ عمومی سایت نمایش داده نمی‌شود.",
    )
    catalog_source = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salon_custom_versions",
        verbose_name="خدمت پایه پلتفرم",
    )
    summery_description = models.TextField(
        default="", verbose_name="توضیحات خلاصه خدمات", blank=True, null=True
    )
    description = models.TextField(blank=True, verbose_name="توضیحات کامل خدمات", null=True)
    file_upload = File_Uploader("images", "services")
    service_image = models.ImageField(
        upload_to=file_upload, verbose_name="تصویر خدمات", null=True
    )
    is_active = models.BooleanField(
        default=True, blank=True, verbose_name="وضعیت فعال / غیرفعال", null=True
    )
    service_group = models.ManyToManyField(
        GroupServices, verbose_name="گروه خدمات", related_name="services_of_group"
    )
    stylists = models.ManyToManyField(
        "accounts.Stylist", verbose_name="آرایشگران", related_name="services_of_stylist"
    )
    view_count = models.IntegerField(default=0, verbose_name="تعداد بازدید")
    duration_minutes = models.PositiveIntegerField(
        verbose_name="مدت زمان خدمت (دقیقه)", default=30
    )
    base_price = models.PositiveIntegerField(
        verbose_name="قیمت پایه خدمت (تومان)",
        default=0,
        help_text="این قیمت پایه حتی قبل از اتصال عضو تیم به خدمت نگهداری می‌شود.",
    )
    buffer_minutes = models.PositiveIntegerField(
        verbose_name="بافر تاخیر/آماده‌سازی بعد از خدمت (دقیقه)",
        default=10,
        help_text="این زمان بعد از پایان خدمت برای آماده‌سازی، جمع‌بندی و جلوگیری از تداخل نوبت بعدی رزرو می‌شود.",
    )
    registere_date = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")
    published_date = models.DateTimeField(default=timezone.now, verbose_name="زمان انتشار")
    updated_date = models.DateTimeField(auto_now=True, verbose_name="زمان آخرین ویرایش")
    features = models.ManyToManyField(Feature, through="ServiceFeature")

    @property
    def effective_seo_title(self):
        return self.seo_title or f"رزرو {self.service_name} | مقایسه سالن‌ها در Loomera"

    @property
    def effective_seo_description(self):
        return self.seo_description or (self.summery_description or f"سالن‌های ارائه‌دهنده {self.service_name} را ببین، قیمت‌ها و نظرات را مقایسه کن و آنلاین رزرو کن.")[:220]

    def __str__(self):
        return f"{self.service_name}"

    def get_absolute_url(self):
        return reverse("services:service_detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug_for_model(self, self.service_name, max_length=190)
        super().save(*args, **kwargs)

    def get_user_score(self):
        request = RequestMiddleware(get_response=None)
        request = request.thread_local.current_request
        score = 0
        user_score = self.scoring_services.filter(scoring_user=request.user)  # type: ignore
        if user_score.count() > 0:
            score = user_score[0].score
        return score

    def get_average_score(self):
        avg_score = self.scoring_services.all().aggregate(Avg("score"))["score__avg"]  # type: ignore
        if avg_score is None:
            avg_score = 0
        return avg_score

    def get_user_favorite(self):
        request = RequestMiddleware(get_response=None)
        request = request.thread_local.current_request
        flag = self.favorite_services.filter(favorite_user=request.user).exists()  # type: ignore
        return flag

    def get_min_max_price(self):
        prices = []
        for stylist in self.stylists.all():
            price = stylist.get_price_for_service(self)
            if price is not None:
                prices.append(price)

        if not prices and self.base_price:
            prices.append(self.base_price)

        min_price = min(prices) if prices else None
        max_price = max(prices) if prices else None
        return min_price, max_price

    class Meta:
        verbose_name = "خدمات"
        verbose_name_plural = "خدمات"
        db_table = "s_services"


# ----------------------------------------------------------------------------------------------------------
# مقدار ویژگی
class FeatureValue(models.Model):
    value_title = models.CharField(max_length=100, verbose_name="عنوان مقدار")
    feature = models.ForeignKey(
        Feature,
        null=True,
        blank=True,
        verbose_name="ویژگی",
        on_delete=models.CASCADE,
        related_name="feature_values",
    )

    def __str__(self):
        return self.value_title

    class Meta:
        verbose_name = "مقدار ویژگی"
        verbose_name_plural = "مقادیر ویژگی ها "


# ---------------------------------------------------------------------------------------------------------
# ویژگی خدمات
class ServiceFeature(models.Model):
    service = models.ForeignKey(
        Services,
        on_delete=models.CASCADE,
        verbose_name="خدمات",
        related_name="service_features",
    )
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, verbose_name="ویژگی")
    value = models.CharField(max_length=100, verbose_name="مقدار")
    filter_value = models.ForeignKey(
        FeatureValue,
        on_delete=models.CASCADE,
        verbose_name="مقدار فیلتر",
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.feature} - {self.service} : {self.value}"

    class Meta:
        verbose_name = "ویژگی خدمات"
        verbose_name_plural = "ویژگی های خدمات"


# -------------------------------------------------------------------------------------------------------------
# گالری خدمات
class ServiceGallery(models.Model):
    service = models.ForeignKey(
        Services,
        on_delete=models.CASCADE,
        verbose_name="خدمات",
        related_name="gallery_images",
        null=True,
    )
    file_upload = File_Uploader("images", "services_gallery")
    service_image = models.ImageField(
        upload_to=file_upload, verbose_name="تصویر خدمات", null=True
    )

    class Meta:
        verbose_name = "تصویر خدمات"
        verbose_name_plural = "تصاویر خدمات"


# -------------------------------------------------------------------------------------------------------
class ServicePrice(models.Model):
    stylist = models.ForeignKey(
        "accounts.Stylist", on_delete=models.CASCADE, related_name="stylist_prices"
    )
    service = models.ForeignKey(Services, on_delete=models.CASCADE, related_name="service_prices")
    price = models.IntegerField(default=0, verbose_name="قیمت")

    class Meta:
        verbose_name = "قیمت خدمت"
        verbose_name_plural = "قیمت های خدمت"
        unique_together = ("service", "stylist")


# ----------------------------------------------------------------------------------------------------
# مواد مصرفی سالن
class MaterialItem(models.Model):
    class Unit(models.TextChoices):
        PIECE = "piece", "عدد"
        GRAM = "gram", "گرم"
        MILLILITER = "milliliter", "میلی‌لیتر"
        SESSION = "session", "نوبت"
        OTHER = "other", "سایر"

    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.CASCADE,
        related_name="material_items",
        verbose_name="سالن",
    )
    name = models.CharField(max_length=120, verbose_name="نام ماده مصرفی")
    unit = models.CharField(
        max_length=20,
        choices=Unit.choices,
        default=Unit.PIECE,
        verbose_name="واحد",
    )
    default_unit_cost = models.PositiveIntegerField(
        default=0,
        verbose_name="هزینه پیش‌فرض هر واحد",
        help_text="مبلغ به تومان",
    )
    sku = models.CharField(
        max_length=80,
        blank=True,
        default="",
        verbose_name="کد داخلی / SKU",
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="توضیحات",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    def __str__(self):
        return f"{self.name} - {self.salon}"

    class Meta:
        verbose_name = "ماده مصرفی"
        verbose_name_plural = "مواد مصرفی"
        db_table = "s_material_item"
        constraints = [
            models.UniqueConstraint(
                fields=["salon", "name"],
                name="unique_material_name_per_salon",
            ),
            models.CheckConstraint(
                check=models.Q(default_unit_cost__gte=0),
                name="mat_def_unit_cost_gte0",
            ),
        ]
        indexes = [
            models.Index(fields=["salon", "is_active"], name="mat_salon_active_idx"),
        ]


# -------------------------------------------------------------------------------------------------------
# قالب مواد مصرفی هر خدمت
class ServiceMaterialTemplate(models.Model):
    class PaidBy(models.TextChoices):
        SALON = "salon", "هزینه با سالن"
        STYLIST = "stylist", "هزینه با آرایشگر"
        SHARED = "shared", "هزینه مشترک"

    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.CASCADE,
        related_name="service_material_templates",
        verbose_name="سالن",
    )
    service = models.ForeignKey(
        Services,
        on_delete=models.CASCADE,
        related_name="material_templates",
        verbose_name="خدمت",
    )
    material = models.ForeignKey(
        MaterialItem,
        on_delete=models.PROTECT,
        related_name="service_templates",
        verbose_name="ماده مصرفی",
    )
    default_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1.00"),
        verbose_name="مقدار پیش‌فرض مصرف",
    )
    unit_cost = models.PositiveIntegerField(
        default=0,
        verbose_name="هزینه هر واحد",
        help_text="اگر صفر باشد، از هزینه پیش‌فرض ماده مصرفی استفاده می‌شود.",
    )
    paid_by = models.CharField(
        max_length=20,
        choices=PaidBy.choices,
        default=PaidBy.SALON,
        verbose_name="پرداخت‌کننده هزینه مواد",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    @property
    def resolved_unit_cost(self):
        return int(self.unit_cost or self.material.default_unit_cost or 0)

    @property
    def estimated_total_cost(self):
        amount = Decimal(self.default_quantity or 0) * Decimal(self.resolved_unit_cost)
        return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def clean(self):
        super().clean()

        if (
            self.material_id
            and self.salon_id
            and self.material.salon_id != self.salon_id
        ):
            raise ValidationError("ماده مصرفی باید متعلق به همین سالن باشد.")

        if self.service_id and self.salon_id:
            if not self.service.services_of_salon.filter(pk=self.salon_id).exists():
                raise ValidationError("این خدمت به سالن انتخاب‌شده متصل نیست.")

        if self.default_quantity is not None and self.default_quantity < 0:
            raise ValidationError("مقدار مصرف نمی‌تواند منفی باشد.")

    def save(self, *args, **kwargs):
        if not self.unit_cost and self.material_id:
            self.unit_cost = int(self.material.default_unit_cost or 0)
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.service} / {self.material}"

    class Meta:
        verbose_name = "قالب مواد مصرفی خدمت"
        verbose_name_plural = "قالب‌های مواد مصرفی خدمات"
        db_table = "s_service_material_template"
        constraints = [
            models.UniqueConstraint(
                fields=["salon", "service", "material"],
                name="uniq_mat_tpl_service",
            ),
            models.CheckConstraint(
                check=models.Q(default_quantity__gte=0),
                name="service_material_qty_gte_zero",
            ),
            models.CheckConstraint(
                check=models.Q(unit_cost__gte=0),
                name="srv_mat_unit_cost_gte0",
            ),
        ]
        indexes = [
            models.Index(
                fields=["salon", "service", "is_active"], name="svc_mat_tpl_lookup_idx"
            ),
        ]


# -------------------------------------------------------------------------------------------------------
# قانون سهم آرایشگر برای هر خدمت
class StylistCommissionRule(models.Model):
    class CommissionType(models.TextChoices):
        PERCENT = "percent", "درصدی"
        FIXED = "fixed", "مبلغ ثابت"

    class ShareBase(models.TextChoices):
        GROSS_AFTER_DISCOUNT = "gross_after_discount", "بعد از تخفیف"
        AFTER_PLATFORM_COMMISSION = "after_platform_commission", "بعد از کارمزد پلتفرم"
        NET_AFTER_MATERIALS = "net_after_materials", "سود خالص بعد از مواد"

    class MaterialCostPolicy(models.TextChoices):
        SALON_PAYS = "salon_pays", "هزینه مواد با سالن"
        STYLIST_PAYS = "stylist_pays", "هزینه مواد با آرایشگر"
        SPLIT = "split", "هزینه مواد مشترک"

    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.CASCADE,
        related_name="stylist_commission_rules",
        verbose_name="سالن",
    )
    stylist = models.ForeignKey(
        "accounts.Stylist",
        on_delete=models.CASCADE,
        related_name="commission_rules",
        verbose_name="آرایشگر",
    )
    service = models.ForeignKey(
        Services,
        on_delete=models.CASCADE,
        related_name="commission_rules",
        verbose_name="خدمت",
    )
    commission_type = models.CharField(
        max_length=20,
        choices=CommissionType.choices,
        default=CommissionType.PERCENT,
        verbose_name="نوع سهم",
    )
    percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="درصد سهم آرایشگر",
    )
    fixed_amount = models.PositiveIntegerField(
        default=0,
        verbose_name="مبلغ ثابت سهم آرایشگر",
    )
    share_base = models.CharField(
        max_length=32,
        choices=ShareBase.choices,
        default=ShareBase.NET_AFTER_MATERIALS,
        verbose_name="مبنای محاسبه سهم",
    )
    material_cost_policy = models.CharField(
        max_length=20,
        choices=MaterialCostPolicy.choices,
        default=MaterialCostPolicy.SALON_PAYS,
        verbose_name="سیاست هزینه مواد",
    )
    stylist_material_cost_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="درصد هزینه مواد با آرایشگر",
        help_text="فقط وقتی سیاست هزینه مواد مشترک باشد استفاده می‌شود.",
    )
    effective_from = models.DateField(
        null=True,
        blank=True,
        verbose_name="شروع اعتبار",
    )
    effective_to = models.DateField(
        null=True,
        blank=True,
        verbose_name="پایان اعتبار",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    note = models.TextField(blank=True, default="", verbose_name="یادداشت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    @classmethod
    def get_active_for(cls, *, salon, stylist, service, at_date=None):
        at_date = at_date or timezone.localdate()
        return (
            cls.objects.filter(
                salon=salon,
                stylist=stylist,
                service=service,
                is_active=True,
            )
            .filter(
                models.Q(effective_from__isnull=True)
                | models.Q(effective_from__lte=at_date),
                models.Q(effective_to__isnull=True)
                | models.Q(effective_to__gte=at_date),
            )
            .order_by("-effective_from", "-id")
            .first()
        )

    def clean(self):
        super().clean()

        if self.salon_id and self.stylist_id:
            if not self.stylist.stylists_of_salon.filter(pk=self.salon_id).exists():
                raise ValidationError("این آرایشگر عضو سالن انتخاب‌شده نیست.")

        if self.salon_id and self.service_id:
            if not self.service.services_of_salon.filter(pk=self.salon_id).exists():
                raise ValidationError("این خدمت برای سالن انتخاب‌شده فعال نیست.")

        if self.service_id and self.stylist_id:
            if not self.service.stylists.filter(pk=self.stylist_id).exists():
                raise ValidationError("این آرایشگر ارائه‌دهنده این خدمت نیست.")

        if (
            self.effective_from
            and self.effective_to
            and self.effective_to < self.effective_from
        ):
            raise ValidationError("تاریخ پایان اعتبار نمی‌تواند قبل از تاریخ شروع باشد.")

        if self.commission_type == self.CommissionType.PERCENT:
            if self.percent <= 0:
                raise ValidationError(
                    "برای سهم درصدی، درصد سهم آرایشگر باید بیشتر از صفر باشد."
                )
            if self.percent > 100:
                raise ValidationError("درصد سهم آرایشگر نمی‌تواند بیشتر از ۱۰۰ باشد.")

        if self.commission_type == self.CommissionType.FIXED:
            if self.fixed_amount <= 0:
                raise ValidationError(
                    "برای سهم ثابت، مبلغ سهم آرایشگر باید بیشتر از صفر باشد."
                )

        if (
            self.stylist_material_cost_percent < 0
            or self.stylist_material_cost_percent > 100
        ):
            raise ValidationError("درصد هزینه مواد با آرایشگر باید بین ۰ تا ۱۰۰ باشد.")

        if self.material_cost_policy != self.MaterialCostPolicy.SPLIT:
            self.stylist_material_cost_percent = Decimal("0.00")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.salon} / {self.stylist} / {self.service}"

    class Meta:
        verbose_name = "قانون سهم آرایشگر"
        verbose_name_plural = "قوانین سهم آرایشگران"
        db_table = "s_stylist_commission_rule"
        constraints = [
            models.CheckConstraint(
                check=models.Q(percent__gte=0) & models.Q(percent__lte=100),
                name="sty_comm_pct_range",
            ),
            models.CheckConstraint(
                check=models.Q(fixed_amount__gte=0),
                name="sty_comm_fixed_gte0",
            ),
            models.CheckConstraint(
                check=models.Q(stylist_material_cost_percent__gte=0)
                & models.Q(stylist_material_cost_percent__lte=100),
                name="stylist_material_percent_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=["salon", "service", "stylist", "is_active"],
                name="sty_comm_lookup_idx",
            ),
            models.Index(
                fields=["effective_from", "effective_to"], name="sty_comm_dates_idx"
            ),
        ]
