from django.contrib import admin

from .models import (
    Notification,
    NotificationDelivery,
    NotificationDeliveryAttempt,
    NotificationPreference,
    NotificationRecipient,
    NotificationTemplate,
)


class NotificationRecipientInline(admin.TabularInline):
    model = NotificationRecipient
    extra = 0
    readonly_fields = ("user", "audience_role", "is_read", "read_at", "is_archived", "created_at")
    can_delete = False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "event_type", "category", "priority", "salon", "created_at")
    list_filter = ("category", "priority", "event_type", "created_at")
    search_fields = ("title", "body", "event_type", "dedupe_key")
    readonly_fields = ("created_at", "related_content_type", "related_object_id", "metadata")
    inlines = [NotificationRecipientInline]
    date_hierarchy = "created_at"


@admin.register(NotificationRecipient)
class NotificationRecipientAdmin(admin.ModelAdmin):
    list_display = ("notification", "user", "audience_role", "is_read", "is_archived", "created_at")
    list_filter = ("audience_role", "is_read", "is_archived", "created_at")
    search_fields = ("notification__title", "user__mobile_number", "user__email")
    readonly_fields = ("notification", "user", "created_at", "read_at", "archived_at")
    date_hierarchy = "created_at"


class NotificationDeliveryAttemptInline(admin.TabularInline):
    model = NotificationDeliveryAttempt
    extra = 0
    readonly_fields = ("attempt_number", "status", "provider", "provider_response", "error_message", "created_at")
    can_delete = False


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    list_display = ("recipient", "channel", "status", "provider", "attempt_count", "created_at")
    list_filter = ("channel", "status", "provider", "created_at")
    search_fields = ("recipient__notification__title", "recipient__user__mobile_number", "recipient__user__email")
    readonly_fields = ("recipient", "created_at", "updated_at", "sent_at", "failed_at", "metadata")
    inlines = [NotificationDeliveryAttemptInline]
    date_hierarchy = "created_at"


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ("event_type", "audience_role", "channel", "category", "priority", "is_active")
    list_filter = ("channel", "category", "priority", "is_active")
    search_fields = ("event_type", "title_template", "body_template")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "audience_role", "category", "event_type", "channel", "is_enabled")
    list_filter = ("audience_role", "category", "channel", "is_enabled")
    search_fields = ("user__mobile_number", "user__email", "event_type")


@admin.register(NotificationDeliveryAttempt)
class NotificationDeliveryAttemptAdmin(admin.ModelAdmin):
    list_display = ("delivery", "attempt_number", "status", "provider", "created_at")
    list_filter = ("status", "provider", "created_at")
    search_fields = ("delivery__recipient__notification__title", "error_message")
    readonly_fields = ("delivery", "attempt_number", "status", "provider", "provider_response", "error_message", "created_at")
    date_hierarchy = "created_at"
