from django.contrib import admin

from .models import (
    HelpArticle,
    HelpArticleChunk,
    HelpCategory,
    HelpConversation,
    HelpFeedback,
    HelpLegalDocument,
    HelpMessage,
    HelpPageContext,
)


@admin.register(HelpCategory)
class HelpCategoryAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "audience", "sort_order", "is_published", "updated_at")
    list_filter = ("audience", "is_published")
    list_editable = ("sort_order", "is_published")
    search_fields = ("title", "slug", "description")


class HelpArticleChunkInline(admin.TabularInline):
    model = HelpArticleChunk
    extra = 0
    can_delete = False
    fields = ("position", "heading", "content")
    readonly_fields = fields
    ordering = ("position",)

    def has_add_permission(self, request, obj=None):
        return False


class HelpPageContextInline(admin.TabularInline):
    model = HelpPageContext
    extra = 0
    fields = ("page_key", "role", "route_name", "path_pattern", "priority", "is_active")


@admin.register(HelpArticle)
class HelpArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "article_type", "key", "category", "audience", "is_featured", "is_published", "updated_at")
    list_filter = ("article_type", "audience", "is_featured", "is_published", "category")
    list_editable = ("is_featured", "is_published")
    search_fields = ("title", "key", "slug", "summary", "body", "keywords", "aliases")
    autocomplete_fields = ("category",)
    raw_id_fields = ("created_by", "updated_by")
    readonly_fields = ("created_at", "updated_at", "published_at")
    prepopulated_fields = {"slug": ("title",)}
    inlines = (HelpArticleChunkInline, HelpPageContextInline,)

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.created_by_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(HelpArticleChunk)
class HelpArticleChunkAdmin(admin.ModelAdmin):
    list_display = ("article", "position", "heading", "updated_at")
    list_filter = ("article__article_type", "article__audience")
    search_fields = ("article__title", "article__key", "heading", "content", "search_text")
    readonly_fields = ("article", "position", "heading", "content", "search_text", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(HelpPageContext)
class HelpPageContextAdmin(admin.ModelAdmin):
    list_display = ("page_key", "role", "route_name", "article", "priority", "is_active", "path_pattern")
    list_filter = ("role", "is_active")
    list_editable = ("priority", "is_active")
    search_fields = ("page_key", "route_name", "path_pattern", "article__title", "article__key")
    autocomplete_fields = ("article",)


@admin.register(HelpLegalDocument)
class HelpLegalDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "version", "status", "is_current", "effective_at", "updated_at")
    list_filter = ("status", "is_current", "audience")
    search_fields = ("title", "slug", "version", "summary", "content")
    readonly_fields = ("created_at", "updated_at", "published_at")
    raw_id_fields = ("created_by", "updated_by")

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.created_by_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


class HelpMessageInline(admin.TabularInline):
    model = HelpMessage
    extra = 0
    can_delete = False
    fields = ("created_at", "role", "content", "used_ai", "model_name")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(HelpConversation)
class HelpConversationAdmin(admin.ModelAdmin):
    list_display = ("public_id", "role", "user", "page_key", "page_route_name", "status", "support_ticket", "last_message_at", "created_at")
    list_filter = ("role", "status", "created_at")
    search_fields = ("public_id", "page_key", "page_path", "user__mobile_number", "user__email")
    raw_id_fields = ("user", "support_ticket")
    readonly_fields = ("public_id", "session_key_hash", "created_at", "updated_at", "last_message_at")
    inlines = (HelpMessageInline,)


@admin.register(HelpMessage)
class HelpMessageAdmin(admin.ModelAdmin):
    list_display = ("public_id", "conversation", "role", "used_ai", "model_name", "created_at")
    list_filter = ("role", "used_ai", "created_at")
    search_fields = ("public_id", "content", "conversation__public_id", "conversation__page_key")
    readonly_fields = ("public_id", "created_at")


@admin.register(HelpFeedback)
class HelpFeedbackAdmin(admin.ModelAdmin):
    list_display = ("message", "rating", "user", "created_at", "updated_at")
    list_filter = ("rating", "created_at")
    search_fields = ("message__content", "note", "user__mobile_number", "user__email")
    readonly_fields = ("created_at", "updated_at")
