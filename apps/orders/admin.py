from django.contrib import admin

from .models import AppointmentEvent, AppointmentMaterialUsage, DelayPolicy, Order, OrderDetail, PaymentType


class AppointmentMaterialUsageInline(admin.TabularInline):
    model = AppointmentMaterialUsage
    extra = 0
    fields = (
        "material",
        "quantity",
        "unit_cost",
        "total_cost",
        "paid_by",
        "recorded_by",
        "note",
    )
    readonly_fields = ("total_cost",)


class OrderDetailInline(admin.TabularInline):
    model = OrderDetail
    extra = 2


@admin.register(Order)
class OrderDeatailAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "salon",
        "register_date",
        "update_date",
        "is_finally",
        "is_paid",
        "status",
        "discount",
    )
    list_filter = ("status", "is_paid", "is_finally", "salon")
    search_fields = (
        "customer__user__name",
        "customer__user__family",
        "customer__user__mobile_number",
        "order_code",
    )
    inlines = [OrderDetailInline]


@admin.register(OrderDetail)
class OrderDetailAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "salon",
        "service",
        "stylist",
        "price",
        "date",
        "time",
        "end_time",
        "occupied_until",
        "lifecycle_status",
        "client_late_minutes",
        "service_overrun_minutes",
        "material_cost_total",
    )
    list_filter = ("salon", "service", "stylist", "date", "lifecycle_status", "confirmation_status")
    search_fields = (
        "order__order_code",
        "service__service_name",
        "salon__salon_name",
        "stylist__user__name",
        "stylist__user__family",
        "stylist__user__mobile_number",
    )
    raw_id_fields = ("order", "service", "stylist", "salon")
    inlines = [AppointmentMaterialUsageInline]
    readonly_fields = (
        "scheduled_duration_minutes",
        "buffer_minutes",
        "occupied_until",
        "client_late_recorded_at",
        "client_late_minutes",
        "no_show_pending_at",
        "no_show_dispute_until",
        "no_show_confirmed_at",
        "expected_service_completed_at",
        "service_overrun_recorded_at",
        "service_overrun_minutes",
        "disputed_at",
    )

    def material_cost_total(self, obj):
        return obj.get_material_cost_total()

    material_cost_total.short_description = "جمع هزینه مواد"


@admin.register(AppointmentMaterialUsage)
class AppointmentMaterialUsageAdmin(admin.ModelAdmin):
    list_display = (
        "order_detail",
        "material",
        "quantity",
        "unit_cost",
        "total_cost",
        "paid_by",
        "created_at",
    )
    list_filter = ("paid_by", "material__salon")
    search_fields = (
        "material__name",
        "order_detail__order__order_code",
        "order_detail__service__service_name",
    )
    raw_id_fields = ("order_detail", "source_template", "material", "recorded_by")
    readonly_fields = ("total_cost",)
    ordering = ("-created_at", "-id")


@admin.register(PaymentType)
class PaymentTypeAdmin(admin.ModelAdmin):
    list_display = ["payment_title"]


@admin.register(DelayPolicy)
class DelayPolicyAdmin(admin.ModelAdmin):
    list_display = ("salon", "grace_period_minutes", "no_show_after_minutes", "no_show_dispute_window_hours", "default_service_buffer_minutes", "updated_at")
    search_fields = ("salon__salon_name",)


@admin.register(AppointmentEvent)
class AppointmentEventAdmin(admin.ModelAdmin):
    list_display = ("order", "order_detail", "event_type", "actor", "old_status", "new_status", "created_at")
    list_filter = ("event_type", "salon", "created_at")
    search_fields = ("order__order_code", "order_detail__service__service_name", "salon__salon_name", "stylist__user__name", "stylist__user__family", "note")
    raw_id_fields = ("order", "order_detail", "salon", "stylist", "actor")
    readonly_fields = ("created_at",)
    ordering = ("-created_at", "-id")
