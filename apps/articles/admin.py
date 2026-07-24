from django.contrib import admin
from django.utils import timezone

from .models import (
    Article,
    ArticleBookmark,
    ArticleCategory,
    ArticleFAQ,
    ArticleGalleryImage,
    ArticleTag,
    ArticleView,
    ContentModerationEvent,
    ContentReport,
    SalonStory,
    StaffContentSubmission,
    SalonStoryItem,
    SalonStoryView,
)


@admin.action(description="انتشار آیتم‌های انتخاب‌شده")
def publish_items(modeladmin, request, queryset):
    queryset.update(
        status="published",
        published_at=timezone.now(),
        reviewed_by=request.user,
        reviewed_at=timezone.now(),
        rejection_reason="",
    )


@admin.action(description="ارسال به صف بررسی")
def send_to_review(modeladmin, request, queryset):
    queryset.update(status="pending_review")


@admin.action(description="آرشیو آیتم‌های انتخاب‌شده")
def archive_items(modeladmin, request, queryset):
    queryset.update(status="archived")


@admin.action(description="تعلیق محتوا تا بررسی")
def suspend_items(modeladmin, request, queryset):
    queryset.update(status="suspended", reviewed_by=request.user, reviewed_at=timezone.now())


@admin.action(description="حذف توسط لومرا")
def remove_by_loomera(modeladmin, request, queryset):
    queryset.update(status="removed_by_loomera", removed_by=request.user, removed_at=timezone.now(), reviewed_by=request.user, reviewed_at=timezone.now())


class ArticleFAQInline(admin.TabularInline):
    model = ArticleFAQ
    extra = 1
    fields = ("question", "answer", "sort_order", "is_active")


class ArticleGalleryImageInline(admin.TabularInline):
    model = ArticleGalleryImage
    extra = 1
    fields = ("image", "caption", "alt_text", "sort_order")


@admin.register(ArticleCategory)
class ArticleCategoryAdmin(admin.ModelAdmin):
    list_display = ("title", "parent", "is_active", "sort_order", "updated_at")
    list_filter = ("is_active", "parent")
    search_fields = ("title", "slug", "description")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("sort_order", "title")


@admin.register(ArticleTag)
class ArticleTagAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("title", "slug", "description")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "content_type",
        "status",
        "visibility",
        "author_display_name",
        "is_featured",
        "is_editor_pick",
        "published_at",
        "view_count",
        "report_count",
    )
    list_filter = (
        "status",
        "visibility",
        "content_type",
        "category",
        "is_featured",
        "is_editor_pick",
        "is_educational",
        "allow_indexing",
        "published_at",
    )
    search_fields = (
        "title",
        "slug",
        "summary",
        "content",
        "author_user__mobile_number",
        "author_user__name",
        "author_user__family",
        "author_salon__salon_name",
        "author_stylist__user__name",
        "author_stylist__user__family",
    )
    prepopulated_fields = {"slug": ("title",)}
    raw_id_fields = ("author_user", "author_stylist", "author_salon", "reviewed_by")
    readonly_fields = (
        "view_count",
        "like_count",
        "report_count",
        "reading_time_minutes",
        "created_at",
        "updated_at",
    )
    filter_horizontal = ("tags", "related_services", "related_service_groups")
    date_hierarchy = "published_at"
    actions = (publish_items, send_to_review, archive_items, suspend_items, remove_by_loomera)
    inlines = (ArticleFAQInline, ArticleGalleryImageInline)
    fieldsets = (
        (
            "محتوا",
            {
                "fields": (
                    "title",
                    "slug",
                    "summary",
                    "content",
                    "cover_image",
                    "content_type",
                    "category",
                    "tags",
                )
            },
        ),
        (
            "نویسنده و ارتباط‌ها",
            {
                "fields": (
                    "author_user",
                    "author_stylist",
                    "author_salon",
                    "related_services",
                    "related_service_groups",
                )
            },
        ),
        (
            "انتشار",
            {
                "fields": (
                    "status",
                    "visibility",
                    "published_at",
                    "is_featured",
                    "is_editor_pick",
                    "is_educational",
                    "allow_indexing",
                )
            },
        ),
        (
            "SEO",
            {"fields": ("seo_title", "seo_description", "canonical_url", "og_image")},
        ),
        ("بررسی", {"fields": ("reviewed_by", "reviewed_at", "rejection_reason")}),
        ("مسئولیت و کنترل محتوا", {"fields": ("professional_confirmed_responsibility", "professional_confirmed_at", "professional_terms_version", "manager_approved_responsibility", "manager_approved_by", "manager_approved_at", "manager_terms_version", "contains_identifiable_client", "client_consent_status", "moderation_note", "removed_by", "removed_at")}),
        (
            "آمار",
            {
                "fields": (
                    "reading_time_minutes",
                    "view_count",
                    "like_count",
                    "report_count",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


@admin.register(ArticleView)
class ArticleViewAdmin(admin.ModelAdmin):
    list_display = ("article", "user", "session_key", "viewed_at")
    list_filter = ("viewed_at",)
    search_fields = ("article__title", "user__mobile_number", "session_key", "ip_hash")
    readonly_fields = (
        "article",
        "user",
        "session_key",
        "ip_hash",
        "user_agent",
        "viewed_at",
    )
    date_hierarchy = "viewed_at"


@admin.register(ArticleBookmark)
class ArticleBookmarkAdmin(admin.ModelAdmin):
    list_display = ("article", "user", "created_at")
    search_fields = (
        "article__title",
        "user__mobile_number",
        "user__name",
        "user__family",
    )
    date_hierarchy = "created_at"


class SalonStoryItemInline(admin.TabularInline):
    model = SalonStoryItem
    extra = 1
    fields = (
        "media_type",
        "image",
        "video",
        "caption",
        "button_label",
        "button_url",
        "duration_seconds",
        "sort_order",
        "is_active",
    )


@admin.register(SalonStory)
class SalonStoryAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "salon",
        "stylist",
        "status",
        "visibility",
        "published_at",
        "expires_at",
        "view_count",
        "click_count",
        "report_count",
    )
    list_filter = ("status", "visibility", "cta_type", "published_at", "expires_at")
    search_fields = (
        "title",
        "summary",
        "salon__salon_name",
        "stylist__user__name",
        "stylist__user__family",
    )
    raw_id_fields = (
        "salon",
        "stylist",
        "related_article",
        "related_service",
        "related_service_group",
        "reviewed_by",
    )
    readonly_fields = ("view_count", "click_count", "report_count", "created_at", "updated_at")
    date_hierarchy = "published_at"
    actions = (publish_items, send_to_review, archive_items, suspend_items, remove_by_loomera)
    inlines = (SalonStoryItemInline,)
    fieldsets = (
        (
            "اطلاعات اصلی",
            {"fields": ("salon", "stylist", "title", "summary", "cover_image")},
        ),
        ("انتشار", {"fields": ("status", "visibility", "published_at", "expires_at")}),
        (
            "CTA و ارتباط‌ها",
            {
                "fields": (
                    "cta_type",
                    "cta_label",
                    "cta_url",
                    "related_article",
                    "related_service",
                    "related_service_group",
                )
            },
        ),
        ("بررسی", {"fields": ("reviewed_by", "reviewed_at", "rejection_reason")}),
        ("مسئولیت و کنترل محتوا", {"fields": ("professional_confirmed_responsibility", "professional_confirmed_at", "professional_terms_version", "manager_approved_responsibility", "manager_approved_by", "manager_approved_at", "manager_terms_version", "contains_identifiable_client", "client_consent_status", "moderation_note", "removed_by", "removed_at")}),
        ("آمار", {"fields": ("view_count", "click_count", "report_count", "created_at", "updated_at")}),
    )


@admin.register(SalonStoryView)
class SalonStoryViewAdmin(admin.ModelAdmin):
    list_display = ("story", "user", "last_item_seen", "viewed_at", "completed_at")
    list_filter = ("viewed_at", "completed_at")
    search_fields = ("story__title", "story__salon__salon_name", "user__mobile_number")
    readonly_fields = ("story", "user", "last_item_seen", "viewed_at", "completed_at")
    date_hierarchy = "viewed_at"


@admin.register(StaffContentSubmission)
class StaffContentSubmissionAdmin(admin.ModelAdmin):
    list_display = ("title", "submission_type", "salon", "stylist", "status", "professional_confirmed_responsibility", "manager_approved_responsibility", "created_at")
    list_filter = ("submission_type", "status", "professional_confirmed_responsibility", "manager_approved_responsibility")
    search_fields = ("title", "body", "salon__salon_name", "stylist__user__name", "stylist__user__family")
    raw_id_fields = ("salon", "stylist", "reviewed_by", "target_content_type")
    readonly_fields = ("created_at", "updated_at", "professional_confirmed_at", "reviewed_at")
    date_hierarchy = "created_at"


@admin.register(ContentReport)
class ContentReportAdmin(admin.ModelAdmin):
    list_display = ("target_object", "reason", "status", "reported_by", "reviewed_by", "created_at")
    list_filter = ("reason", "status", "created_at", "reviewed_at")
    search_fields = ("description", "resolution_note", "reported_by__mobile_number")
    raw_id_fields = ("target_content_type", "reported_by", "reviewed_by")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"


@admin.register(ContentModerationEvent)
class ContentModerationEventAdmin(admin.ModelAdmin):
    list_display = ("target_object", "event_type", "actor", "old_status", "new_status", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("note", "actor__mobile_number")
    raw_id_fields = ("target_content_type", "actor")
    readonly_fields = ("target_content_type", "target_object_id", "event_type", "actor", "old_status", "new_status", "note", "metadata", "created_at")
    date_hierarchy = "created_at"
