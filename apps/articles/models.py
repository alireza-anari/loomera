from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class PublishableQuerySet(models.QuerySet):
    def published(self):
        now = timezone.now()
        return self.filter(
            status="published",
            published_at__isnull=False,
            published_at__lte=now,
        )


class ArticleCategory(models.Model):
    title = models.CharField(max_length=120, verbose_name="عنوان دسته‌بندی")
    slug = models.SlugField(
        max_length=160,
        unique=True,
        allow_unicode=True,
        verbose_name="اسلاگ",
        help_text="برای URL پایدار دسته‌بندی استفاده می‌شود.",
    )
    description = models.TextField(blank=True, default="", verbose_name="توضیحات")
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="دسته والد",
    )
    image = models.ImageField(
        upload_to="images/articles/categories/",
        blank=True,
        null=True,
        verbose_name="تصویر دسته‌بندی",
    )
    seo_title = models.CharField(
        max_length=160, blank=True, default="", verbose_name="عنوان SEO"
    )
    seo_description = models.CharField(
        max_length=220,
        blank=True,
        default="",
        verbose_name="توضیحات SEO",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        ordering = ["sort_order", "title"]
        verbose_name = "دسته‌بندی مقاله"
        verbose_name_plural = "دسته‌بندی‌های مقاله"
        db_table = "articles_category"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("articles:category_detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)[:150]
        super().save(*args, **kwargs)


class ArticleTag(models.Model):
    title = models.CharField(max_length=80, verbose_name="عنوان تگ")
    slug = models.SlugField(
        max_length=120, unique=True, allow_unicode=True, verbose_name="اسلاگ"
    )
    description = models.TextField(blank=True, default="", verbose_name="توضیحات")
    seo_title = models.CharField(
        max_length=160, blank=True, default="", verbose_name="عنوان SEO"
    )
    seo_description = models.CharField(
        max_length=220, blank=True, default="", verbose_name="توضیحات SEO"
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        ordering = ["title"]
        verbose_name = "تگ مقاله"
        verbose_name_plural = "تگ‌های مقاله"
        db_table = "articles_tag"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("articles:tag_detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)[:110]
        super().save(*args, **kwargs)


class Article(models.Model):
    class ContentType(models.TextChoices):
        EDUCATIONAL = "educational", "آموزشی"
        GUIDE = "guide", "راهنمای انتخاب خدمت"
        CASE_STUDY = "case_study", "تحلیل نمونه‌کار"
        Q_AND_A = "qa", "پرسش و پاسخ"
        TREND = "trend", "ترند و ایده"
        NEWS = "news", "خبر و اطلاع‌رسانی"

    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PENDING_REVIEW = "pending_review", "در انتظار بررسی"
        NEEDS_REVISION = "needs_revision", "نیازمند اصلاح"
        APPROVED = "approved", "تأیید شده"
        PUBLISHED = "published", "منتشر شده"
        REJECTED = "rejected", "رد شده"
        ARCHIVED = "archived", "آرشیو شده"
        HIDDEN_BY_SALON = "hidden_by_salon", "مخفی شده توسط سالن"
        REPORTED = "reported", "گزارش شده"
        SUSPENDED = "suspended", "تعلیق شده"
        REMOVED_BY_LOOMERA = "removed_by_loomera", "حذف شده توسط لومرا"

    class Visibility(models.TextChoices):
        PUBLIC = "public", "عمومی"
        UNLISTED = "unlisted", "غیرقابل فهرست"
        SALON_FOLLOWERS = "salon_followers", "فقط دنبال‌کنندگان/علاقه‌مندان سالن"

    title = models.CharField(max_length=220, verbose_name="عنوان مقاله")
    slug = models.SlugField(
        max_length=240, unique=True, allow_unicode=True, verbose_name="اسلاگ"
    )
    summary = models.TextField(verbose_name="خلاصه مقاله")
    content = models.TextField(verbose_name="متن مقاله")
    cover_image = models.ImageField(
        upload_to="images/articles/covers/",
        blank=True,
        null=True,
        verbose_name="تصویر شاخص",
    )
    content_type = models.CharField(
        max_length=30,
        choices=ContentType.choices,
        default=ContentType.EDUCATIONAL,
        verbose_name="نوع محتوا",
    )
    category = models.ForeignKey(
        ArticleCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name="دسته‌بندی",
    )
    tags = models.ManyToManyField(
        ArticleTag,
        blank=True,
        related_name="articles",
        verbose_name="تگ‌ها",
    )
    author_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_articles",
        verbose_name="نویسنده کاربری",
    )
    author_stylist = models.ForeignKey(
        "accounts.Stylist",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name="متخصص نویسنده",
    )
    author_salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name="سالن مرتبط",
    )
    related_services = models.ManyToManyField(
        "services.Services",
        blank=True,
        related_name="related_articles",
        verbose_name="خدمات مرتبط",
    )
    related_service_groups = models.ManyToManyField(
        "services.GroupServices",
        blank=True,
        related_name="related_articles",
        verbose_name="گروه‌های خدمات مرتبط",
    )
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name="وضعیت",
    )
    visibility = models.CharField(
        max_length=24,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
        verbose_name="نمایش",
    )
    is_featured = models.BooleanField(default=False, verbose_name="ویژه")
    is_editor_pick = models.BooleanField(default=False, verbose_name="منتخب سردبیر")
    is_educational = models.BooleanField(default=True, verbose_name="محتوای آموزشی")
    allow_indexing = models.BooleanField(default=True, verbose_name="اجازه ایندکس SEO")
    seo_title = models.CharField(
        max_length=160, blank=True, default="", verbose_name="عنوان SEO"
    )
    seo_description = models.CharField(
        max_length=220, blank=True, default="", verbose_name="توضیحات SEO"
    )
    canonical_url = models.URLField(
        blank=True, default="", verbose_name="Canonical URL"
    )
    og_image = models.ImageField(
        upload_to="images/articles/og/",
        blank=True,
        null=True,
        verbose_name="تصویر Open Graph",
    )
    reading_time_minutes = models.PositiveSmallIntegerField(
        default=1, verbose_name="زمان مطالعه تقریبی"
    )
    view_count = models.PositiveIntegerField(default=0, verbose_name="تعداد بازدید")
    like_count = models.PositiveIntegerField(default=0, verbose_name="تعداد پسندیدن")
    rejection_reason = models.TextField(
        blank=True, default="", verbose_name="دلیل رد شدن"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_articles",
        verbose_name="بررسی‌شده توسط",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان بررسی")
    professional_confirmed_responsibility = models.BooleanField(default=False, verbose_name="تأیید مسئولیت توسط آرایشگر")
    professional_confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان تأیید آرایشگر")
    professional_terms_version = models.CharField(max_length=32, blank=True, default="", verbose_name="نسخه قوانین آرایشگر")
    manager_approved_responsibility = models.BooleanField(default=False, verbose_name="تأیید مسئولیت توسط مدیر سالن")
    manager_approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="manager_approved_articles", verbose_name="تأیید مسئولیت توسط")
    manager_approved_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان تأیید مدیر")
    manager_terms_version = models.CharField(max_length=32, blank=True, default="", verbose_name="نسخه قوانین مدیر")
    contains_identifiable_client = models.BooleanField(default=False, verbose_name="دارای هویت قابل تشخیص مشتری")
    client_consent_status = models.CharField(max_length=64, default="not_required", verbose_name="وضعیت رضایت مشتری")
    report_count = models.PositiveIntegerField(default=0, verbose_name="تعداد گزارش")
    moderation_note = models.TextField(blank=True, default="", verbose_name="یادداشت بررسی محتوا")
    removed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="removed_articles", verbose_name="حذف‌شده توسط")
    removed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان حذف/تعلیق")
    published_at = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name="زمان انتشار"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    objects = PublishableQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at", "-created_at"]
        verbose_name = "مقاله"
        verbose_name_plural = "مقالات"
        db_table = "articles_article"
        indexes = [
            models.Index(fields=["status", "published_at"]),
            models.Index(fields=["is_featured", "status"]),
            models.Index(fields=["content_type", "status"]),
        ]

    def __str__(self):
        return self.title

    @property
    def is_published(self):
        return (
            self.status == self.Status.PUBLISHED
            and self.published_at is not None
            and self.published_at <= timezone.now()
        )

    @property
    def author_display_name(self):
        if self.author_stylist_id:
            return self.author_stylist.get_fullName()
        if self.author_salon_id:
            return self.author_salon.salon_name
        if self.author_user_id:
            if hasattr(self.author_user, "get_fullName"):
                return self.author_user.get_fullName() or getattr(
                    self.author_user, "mobile_number", ""
                )
            return str(self.author_user)
        return "تیم لومرا"

    @property
    def effective_seo_title(self):
        return self.seo_title or self.title

    @property
    def effective_seo_description(self):
        return self.seo_description or self.summary[:210]

    def get_absolute_url(self):
        return reverse("articles:article_detail", kwargs={"slug": self.slug})

    def calculate_reading_time(self):
        words_count = len((self.content or "").split())
        return max(1, round(words_count / 220))

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)[:220]
        self.reading_time_minutes = self.calculate_reading_time()
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        if self.status in {
            self.Status.DRAFT,
            self.Status.PENDING_REVIEW,
            self.Status.NEEDS_REVISION,
            self.Status.REJECTED,
            self.Status.REPORTED,
            self.Status.SUSPENDED,
            self.Status.REMOVED_BY_LOOMERA,
        }:
            self.allow_indexing = False
        super().save(*args, **kwargs)


class ArticleFAQ(models.Model):
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="faqs",
        verbose_name="مقاله",
    )
    question = models.CharField(max_length=220, verbose_name="سؤال")
    answer = models.TextField(verbose_name="پاسخ")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "پرسش پرتکرار مقاله"
        verbose_name_plural = "پرسش‌های پرتکرار مقاله"
        db_table = "articles_faq"

    def __str__(self):
        return self.question


class ArticleGalleryImage(models.Model):
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="gallery_images",
        verbose_name="مقاله",
    )
    image = models.ImageField(
        upload_to="images/articles/gallery/", verbose_name="تصویر"
    )
    caption = models.CharField(
        max_length=180, blank=True, default="", verbose_name="کپشن"
    )
    alt_text = models.CharField(
        max_length=160, blank=True, default="", verbose_name="متن جایگزین تصویر"
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "تصویر گالری مقاله"
        verbose_name_plural = "تصاویر گالری مقاله"
        db_table = "articles_gallery_image"

    def __str__(self):
        return self.caption or self.article.title


class ArticleView(models.Model):
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="views",
        verbose_name="مقاله",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="article_views",
        verbose_name="کاربر",
    )
    session_key = models.CharField(
        max_length=80, blank=True, default="", verbose_name="کلید نشست"
    )
    ip_hash = models.CharField(
        max_length=64, blank=True, default="", verbose_name="هش IP"
    )
    user_agent = models.CharField(
        max_length=255, blank=True, default="", verbose_name="مرورگر"
    )
    viewed_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان بازدید")

    class Meta:
        ordering = ["-viewed_at"]
        verbose_name = "بازدید مقاله"
        verbose_name_plural = "بازدیدهای مقاله"
        db_table = "articles_view"

    def __str__(self):
        return f"{self.article} - {self.viewed_at:%Y-%m-%d}"


class ArticleBookmark(models.Model):
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="bookmarks",
        verbose_name="مقاله",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="article_bookmarks",
        verbose_name="کاربر",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ذخیره")

    class Meta:
        unique_together = ("article", "user")
        ordering = ["-created_at"]
        verbose_name = "ذخیره مقاله"
        verbose_name_plural = "ذخیره‌های مقاله"
        db_table = "articles_bookmark"

    def __str__(self):
        return f"{self.user} - {self.article}"


class SalonStory(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PENDING_REVIEW = "pending_review", "در انتظار بررسی"
        NEEDS_REVISION = "needs_revision", "نیازمند اصلاح"
        APPROVED = "approved", "تأیید شده"
        PUBLISHED = "published", "منتشر شده"
        REJECTED = "rejected", "رد شده"
        EXPIRED = "expired", "منقضی شده"
        ARCHIVED = "archived", "آرشیو شده"
        HIDDEN_BY_SALON = "hidden_by_salon", "مخفی شده توسط سالن"
        REPORTED = "reported", "گزارش شده"
        SUSPENDED = "suspended", "تعلیق شده"
        REMOVED_BY_LOOMERA = "removed_by_loomera", "حذف شده توسط لومرا"

    class Visibility(models.TextChoices):
        PUBLIC = "public", "عمومی"
        FAVORITES_ONLY = "favorites_only", "فقط مشتریان علاقه‌مند به سالن"
        SALON_PAGE_ONLY = "salon_page_only", "فقط صفحه سالن"

    class CTAType(models.TextChoices):
        NONE = "none", "بدون دکمه"
        SALON = "salon", "مشاهده سالن"
        BOOKING = "booking", "رزرو"
        ARTICLE = "article", "مطالعه مقاله"
        SERVICE = "service", "مشاهده خدمت"
        CUSTOM = "custom", "لینک سفارشی"

    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.CASCADE,
        related_name="stories",
        verbose_name="سالن",
    )
    stylist = models.ForeignKey(
        "accounts.Stylist",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stories",
        verbose_name="متخصص مرتبط",
    )
    title = models.CharField(max_length=140, verbose_name="عنوان استوری")
    summary = models.CharField(
        max_length=220, blank=True, default="", verbose_name="توضیح کوتاه"
    )
    cover_image = models.ImageField(
        upload_to="images/articles/stories/covers/",
        blank=True,
        null=True,
        verbose_name="کاور استوری",
    )
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name="وضعیت",
    )
    visibility = models.CharField(
        max_length=24,
        choices=Visibility.choices,
        default=Visibility.FAVORITES_ONLY,
        verbose_name="نمایش",
    )
    published_at = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name="زمان انتشار"
    )
    expires_at = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name="زمان انقضا"
    )
    cta_type = models.CharField(
        max_length=20,
        choices=CTAType.choices,
        default=CTAType.SALON,
        verbose_name="نوع CTA",
    )
    cta_label = models.CharField(
        max_length=80, blank=True, default="", verbose_name="متن دکمه"
    )
    cta_url = models.CharField(
        max_length=300, blank=True, default="", verbose_name="لینک سفارشی"
    )
    related_article = models.ForeignKey(
        Article,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stories",
        verbose_name="مقاله مرتبط",
    )
    related_service = models.ForeignKey(
        "services.Services",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stories",
        verbose_name="خدمت مرتبط",
    )
    related_service_group = models.ForeignKey(
        "services.GroupServices",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stories",
        verbose_name="گروه خدمت مرتبط",
    )
    view_count = models.PositiveIntegerField(default=0, verbose_name="تعداد بازدید")
    click_count = models.PositiveIntegerField(default=0, verbose_name="تعداد کلیک CTA")
    rejection_reason = models.TextField(
        blank=True, default="", verbose_name="دلیل رد شدن"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_stories",
        verbose_name="بررسی‌شده توسط",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان بررسی")
    professional_confirmed_responsibility = models.BooleanField(default=False, verbose_name="تأیید مسئولیت توسط آرایشگر")
    professional_confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان تأیید آرایشگر")
    professional_terms_version = models.CharField(max_length=32, blank=True, default="", verbose_name="نسخه قوانین آرایشگر")
    manager_approved_responsibility = models.BooleanField(default=False, verbose_name="تأیید مسئولیت توسط مدیر سالن")
    manager_approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="manager_approved_stories", verbose_name="تأیید مسئولیت توسط")
    manager_approved_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان تأیید مدیر")
    manager_terms_version = models.CharField(max_length=32, blank=True, default="", verbose_name="نسخه قوانین مدیر")
    contains_identifiable_client = models.BooleanField(default=False, verbose_name="دارای هویت قابل تشخیص مشتری")
    client_consent_status = models.CharField(max_length=64, default="not_required", verbose_name="وضعیت رضایت مشتری")
    report_count = models.PositiveIntegerField(default=0, verbose_name="تعداد گزارش")
    moderation_note = models.TextField(blank=True, default="", verbose_name="یادداشت بررسی محتوا")
    removed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="removed_stories", verbose_name="حذف‌شده توسط")
    removed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان حذف/تعلیق")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    objects = PublishableQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at", "-created_at"]
        verbose_name = "استوری سالن"
        verbose_name_plural = "استوری‌های سالن"
        db_table = "articles_salon_story"
        indexes = [
            models.Index(fields=["status", "published_at", "expires_at"]),
            models.Index(fields=["salon", "status"]),
            models.Index(fields=["visibility", "status"]),
        ]

    def __str__(self):
        return f"{self.salon} - {self.title}"

    @property
    def is_live(self):
        now = timezone.now()
        return (
            self.status == self.Status.PUBLISHED
            and self.published_at is not None
            and self.published_at <= now
            and (self.expires_at is None or self.expires_at >= now)
        )

    @property
    def item_count(self):
        return self.items.count()

    def save(self, *args, **kwargs):
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        if self.status == self.Status.PUBLISHED and not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)

    def get_cta_url(self):
        if self.cta_type == self.CTAType.CUSTOM and self.cta_url:
            return self.cta_url
        if self.cta_type == self.CTAType.ARTICLE and self.related_article_id:
            return self.related_article.get_absolute_url()
        if self.cta_type == self.CTAType.SALON and self.salon_id:
            return self.salon.get_absolute_url()
        if self.cta_type == self.CTAType.BOOKING and self.salon_id:
            return (
                self.salon.get_absolute_url()
                + "#services"
            )
        if self.cta_type == self.CTAType.SERVICE and self.related_service_id:
            return (
                reverse("search:search_page")
                + f"?q={self.related_service.service_name}"
            )
        return ""


class SalonStoryItem(models.Model):
    class MediaType(models.TextChoices):
        IMAGE = "image", "تصویر"
        VIDEO = "video", "ویدیو"

    story = models.ForeignKey(
        SalonStory,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="استوری",
    )
    media_type = models.CharField(
        max_length=12,
        choices=MediaType.choices,
        default=MediaType.IMAGE,
        verbose_name="نوع رسانه",
    )
    image = models.ImageField(
        upload_to="images/articles/stories/items/",
        blank=True,
        null=True,
        verbose_name="تصویر",
    )
    video = models.FileField(
        upload_to="videos/articles/stories/",
        blank=True,
        null=True,
        verbose_name="ویدیو",
    )
    caption = models.CharField(
        max_length=260, blank=True, default="", verbose_name="کپشن"
    )
    button_label = models.CharField(
        max_length=80, blank=True, default="", verbose_name="متن دکمه اسلاید"
    )
    button_url = models.CharField(
        max_length=300, blank=True, default="", verbose_name="لینک دکمه اسلاید"
    )
    duration_seconds = models.PositiveSmallIntegerField(
        default=5, verbose_name="مدت نمایش"
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "آیتم استوری سالن"
        verbose_name_plural = "آیتم‌های استوری سالن"
        db_table = "articles_salon_story_item"

    def __str__(self):
        return f"{self.story} - {self.sort_order}"


class SalonStoryView(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="story_views",
        verbose_name="کاربر",
    )
    story = models.ForeignKey(
        SalonStory,
        on_delete=models.CASCADE,
        related_name="views",
        verbose_name="استوری",
    )
    last_item_seen = models.ForeignKey(
        SalonStoryItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="last_seen_views",
        verbose_name="آخرین آیتم دیده‌شده",
    )
    viewed_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بازدید")
    completed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="زمان تکمیل مشاهده"
    )

    class Meta:
        unique_together = ("user", "story")
        ordering = ["-viewed_at"]
        verbose_name = "بازدید استوری سالن"
        verbose_name_plural = "بازدیدهای استوری سالن"
        db_table = "articles_salon_story_view"

    def __str__(self):
        return f"{self.user} - {self.story}"


class StaffContentSubmission(models.Model):
    class SubmissionType(models.TextChoices):
        ARTICLE = "article", "مقاله"
        STORY = "story", "استوری"
        PORTFOLIO = "portfolio", "نمونه‌کار"
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PENDING_REVIEW = "pending_review", "در انتظار بررسی"
        NEEDS_REVISION = "needs_revision", "نیازمند اصلاح"
        APPROVED = "approved", "تأیید شده"
        REJECTED = "rejected", "رد شده"
        PUBLISHED = "published", "منتشر شده"
        ARCHIVED = "archived", "آرشیو شده"
    salon = models.ForeignKey("salons.Salon", on_delete=models.CASCADE, related_name="staff_content_submissions", verbose_name="سالن")
    stylist = models.ForeignKey("accounts.Stylist", on_delete=models.CASCADE, related_name="content_submissions", verbose_name="آرایشگر")
    submission_type = models.CharField(max_length=32, choices=SubmissionType.choices, verbose_name="نوع محتوا")
    title = models.CharField(max_length=255, blank=True, default="", verbose_name="عنوان")
    body = models.TextField(blank=True, default="", verbose_name="متن/توضیح")
    media = models.FileField(upload_to="staff_content/submissions/", null=True, blank=True, verbose_name="فایل محتوا")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name="وضعیت")
    target_content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL, related_name="staff_content_submission_targets", verbose_name="نوع محتوای منتشرشده")
    target_object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="شناسه محتوای منتشرشده")
    target_object = GenericForeignKey("target_content_type", "target_object_id")
    professional_confirmed_responsibility = models.BooleanField(default=False, verbose_name="تأیید مسئولیت توسط آرایشگر")
    professional_confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان تأیید آرایشگر")
    manager_approved_responsibility = models.BooleanField(default=False, verbose_name="تأیید مسئولیت توسط مدیر سالن")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_staff_content_submissions", verbose_name="بررسی‌شده توسط")
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان بررسی")
    review_note = models.TextField(blank=True, default="", verbose_name="یادداشت بررسی")
    contains_identifiable_client = models.BooleanField(default=False, verbose_name="دارای هویت قابل تشخیص مشتری")
    client_consent_status = models.CharField(max_length=64, default="not_required", verbose_name="وضعیت رضایت مشتری")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "محتوای پیشنهادی آرایشگر"
        verbose_name_plural = "محتواهای پیشنهادی آرایشگران"
        db_table = "articles_staff_content_submission"
        indexes = [
            models.Index(fields=["salon", "status"], name="staffcont_salon_stat_idx"),
            models.Index(fields=["stylist", "status"], name="staffcont_sty_stat_idx"),
        ]
    def __str__(self):
        return self.title or f"{self.get_submission_type_display()} #{self.pk or ''}"


class ContentReport(models.Model):
    class Reason(models.TextChoices):
        INAPPROPRIATE = "inappropriate", "محتوای نامناسب"
        NO_PERMISSION = "no_permission", "تصویر یا محتوا بدون اجازه"
        MISLEADING = "misleading", "گمراه‌کننده یا نادرست"
        PERSONAL_INFO = "personal_info", "نمایش اطلاعات شخصی"
        OFF_PLATFORM = "off_platform", "تبلیغ خارج از لومرا"
        COPYRIGHT = "copyright", "نقض مالکیت محتوا"
        OTHER = "other", "سایر"
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار بررسی"
        REVIEWED = "reviewed", "بررسی شده"
        ACCEPTED = "accepted", "پذیرفته شده"
        REJECTED = "rejected", "رد شده"
    target_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="content_reports", verbose_name="نوع محتوا")
    target_object_id = models.PositiveIntegerField(verbose_name="شناسه محتوا")
    target_object = GenericForeignKey("target_content_type", "target_object_id")
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="content_reports", verbose_name="گزارش‌دهنده")
    reason = models.CharField(max_length=64, choices=Reason.choices, verbose_name="دلیل گزارش")
    description = models.TextField(blank=True, default="", verbose_name="توضیح")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING, db_index=True, verbose_name="وضعیت")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_content_reports", verbose_name="بررسی‌شده توسط")
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان بررسی")
    resolution_note = models.TextField(blank=True, default="", verbose_name="نتیجه بررسی")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ گزارش")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "گزارش محتوا"
        verbose_name_plural = "گزارش‌های محتوا"
        db_table = "articles_content_report"
        indexes = [
            models.Index(fields=["status", "created_at"], name="contrept_status_idx"),
            models.Index(fields=["target_content_type", "target_object_id"], name="contrept_target_idx"),
        ]
    def __str__(self):
        return f"{self.get_reason_display()} - {self.status}"


class ContentModerationEvent(models.Model):
    target_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="content_moderation_events", verbose_name="نوع محتوا")
    target_object_id = models.PositiveIntegerField(verbose_name="شناسه محتوا")
    target_object = GenericForeignKey("target_content_type", "target_object_id")
    event_type = models.CharField(max_length=64, verbose_name="نوع رویداد")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="content_moderation_events", verbose_name="کاربر عامل")
    old_status = models.CharField(max_length=64, blank=True, default="", verbose_name="وضعیت قبلی")
    new_status = models.CharField(max_length=64, blank=True, default="", verbose_name="وضعیت جدید")
    note = models.TextField(blank=True, default="", verbose_name="یادداشت")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="متادیتا")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "رویداد بررسی محتوا"
        verbose_name_plural = "رویدادهای بررسی محتوا"
        db_table = "articles_content_moderation_event"
        indexes = [
            models.Index(fields=["target_content_type", "target_object_id"], name="contmode_target_idx"),
            models.Index(fields=["event_type", "created_at"], name="contmode_event_idx"),
        ]
    def __str__(self):
        return f"{self.event_type} - {self.created_at:%Y-%m-%d}"
