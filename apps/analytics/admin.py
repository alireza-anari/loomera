from django.contrib import admin

from .models import (
    AnalyticsEvent,
    DailyContentMetric,
    DailyPlatformMetric,
    DailySalonMetric,
    DailySearchMetric,
    DailyStaffMetric,
    ReportExportJob,
)


class OptimizedAnalyticsAdmin(admin.ModelAdmin):
    """Shared performance defaults for analytics changelists."""

    # Prevent Django Admin from executing an additional unfiltered
    # COUNT query solely for the "Show all results" label.
    show_full_result_count = False

    # Keep each admin page bounded as analytics tables grow.
    list_per_page = 50

    list_select_related = ()

    def get_queryset(self, request):
        """Apply eager loading before the changelist is rendered."""

        queryset = super().get_queryset(request)

        related_fields = self.get_list_select_related(request)

        if related_fields is True:
            return queryset.select_related()

        if related_fields:
            return queryset.select_related(*related_fields)

        return queryset


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(OptimizedAnalyticsAdmin):
    list_display = (
        "category",
        "event_type",
        "salon",
        "stylist",
        "occurred_at",
    )
    list_filter = (
        "category",
        "event_type",
        "occurred_at",
    )
    search_fields = (
        "event_type",
        "source",
        "session_key",
    )
    date_hierarchy = "occurred_at"

    # Stylist.__str__ accesses stylist.user, so both levels must
    # be loaded in the original query.
    list_select_related = (
        "salon",
        "stylist__user",
    )


@admin.register(DailyPlatformMetric)
class DailyPlatformMetricAdmin(OptimizedAnalyticsAdmin):
    list_display = (
        "date",
        "appointments_count",
        "completed_count",
        "gross_revenue",
        "searches_count",
        "support_open_count",
    )
    date_hierarchy = "date"


@admin.register(DailySalonMetric)
class DailySalonMetricAdmin(OptimizedAnalyticsAdmin):
    list_display = (
        "salon",
        "date",
        "appointments_count",
        "completed_count",
        "gross_revenue",
        "salon_net_profit",
    )
    search_fields = ("salon__salon_name",)
    date_hierarchy = "date"

    list_select_related = ("salon",)


@admin.register(DailyStaffMetric)
class DailyStaffMetricAdmin(OptimizedAnalyticsAdmin):
    list_display = (
        "stylist",
        "salon",
        "date",
        "appointments_count",
        "completed_count",
        "net_profit",
    )
    search_fields = (
        "stylist__user__mobile_number",
        "stylist__user__name",
        "salon__salon_name",
    )
    date_hierarchy = "date"

    list_select_related = (
        "stylist__user",
        "salon",
    )


@admin.register(DailyContentMetric)
class DailyContentMetricAdmin(OptimizedAnalyticsAdmin):
    list_display = (
        "content_kind",
        "object_id",
        "salon",
        "date",
        "views",
        "cta_clicks",
        "reports_count",
    )
    list_filter = (
        "content_kind",
        "date",
    )
    date_hierarchy = "date"

    list_select_related = ("salon",)


@admin.register(DailySearchMetric)
class DailySearchMetricAdmin(OptimizedAnalyticsAdmin):
    list_display = (
        "date",
        "normalized_query",
        "searches_count",
        "no_result_count",
        "clicks_count",
        "booking_completed",
    )
    search_fields = (
        "normalized_query",
        "query",
    )
    date_hierarchy = "date"


@admin.register(ReportExportJob)
class ReportExportJobAdmin(OptimizedAnalyticsAdmin):
    list_display = (
        "report_type",
        "status",
        "requested_by",
        "rows_count",
        "created_at",
        "completed_at",
    )
    list_filter = (
        "report_type",
        "status",
        "created_at",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
    )

    list_select_related = ("requested_by",)
