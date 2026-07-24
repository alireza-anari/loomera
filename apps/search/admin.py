from django.contrib import admin

from apps.search.models import SearchAlias, SearchConversion, SearchLog, SearchResultClick


@admin.register(SearchLog)
class SearchLogAdmin(admin.ModelAdmin):
    list_display = ("query", "location", "sort", "results_count", "no_result", "created_at")
    list_filter = ("no_result", "sort", "q_type", "created_at")
    search_fields = ("query", "normalized_query", "location", "session_key")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"


@admin.register(SearchResultClick)
class SearchResultClickAdmin(admin.ModelAdmin):
    list_display = ("salon", "rank", "source", "created_at")
    list_filter = ("source", "created_at")
    search_fields = ("salon__salon_name",)
    readonly_fields = ("created_at",)


@admin.register(SearchConversion)
class SearchConversionAdmin(admin.ModelAdmin):
    list_display = ("conversion_type", "salon", "order", "created_at")
    list_filter = ("conversion_type", "created_at")
    search_fields = ("salon__salon_name", "order__order_code")
    readonly_fields = ("created_at",)


@admin.register(SearchAlias)
class SearchAliasAdmin(admin.ModelAdmin):
    list_display = ("keyword", "target_type", "target_id", "is_active", "updated_at")
    list_filter = ("target_type", "is_active")
    search_fields = ("keyword", "normalized_keyword")
    readonly_fields = ("normalized_keyword", "created_at", "updated_at")
