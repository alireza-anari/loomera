from django.contrib import admin

from .models import (
    MessagingAccountConnection,
    MessagingActionExecution,
    MessagingIdentity,
    MessagingMessageLog,
    MessagingProvider,
    MessagingToken,
    MessagingWebhookEvent,
)


@admin.register(MessagingProvider)
class MessagingProviderAdmin(admin.ModelAdmin):
    list_display = ("key", "title", "is_active", "supports_webhook", "supports_callback", "supports_outbound")
    list_filter = ("is_active", "supports_webhook", "supports_callback", "supports_outbound")
    search_fields = ("key", "title")
    readonly_fields = ("created_at", "updated_at")


@admin.register(MessagingIdentity)
class MessagingIdentityAdmin(admin.ModelAdmin):
    list_display = ("provider", "provider_user_id", "chat_id", "user", "status", "last_seen_at", "updated_at")
    list_filter = ("provider", "status", "created_at", "updated_at")
    search_fields = ("provider_user_id", "chat_id", "phone_number", "username", "display_name", "user__mobile_number")
    readonly_fields = ("first_seen_at", "last_seen_at", "connected_at", "disconnected_at", "created_at", "updated_at", "raw_profile")
    date_hierarchy = "created_at"


@admin.register(MessagingAccountConnection)
class MessagingAccountConnectionAdmin(admin.ModelAdmin):
    list_display = ("provider", "identity", "user", "status", "connected_at", "disconnected_at")
    list_filter = ("provider", "status", "connected_at")
    search_fields = ("identity__provider_user_id", "identity__chat_id", "user__mobile_number", "user__email")
    readonly_fields = ("connected_at", "disconnected_at", "metadata")
    date_hierarchy = "connected_at"


@admin.register(MessagingToken)
class MessagingTokenAdmin(admin.ModelAdmin):
    list_display = ("purpose", "token_prefix", "provider", "identity", "user", "action_key", "audience_role", "salon_id", "expires_at", "used_at", "revoked_at")
    list_filter = ("purpose", "provider", "audience_role", "expires_at", "used_at", "revoked_at")
    search_fields = ("token_prefix", "action_key", "identity__provider_user_id", "identity__chat_id", "user__mobile_number")
    readonly_fields = ("token_hash", "token_prefix", "created_at", "used_at", "revoked_at", "metadata", "related_content_type", "related_object_id")
    date_hierarchy = "created_at"


@admin.register(MessagingWebhookEvent)
class MessagingWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("provider", "event_type", "event_id", "update_id", "identity", "status", "received_at", "processed_at")
    list_filter = ("provider", "status", "event_type", "received_at")
    search_fields = ("event_id", "update_id", "identity__provider_user_id", "identity__chat_id", "error_message")
    readonly_fields = ("payload", "headers", "received_at", "processed_at", "error_message")
    date_hierarchy = "received_at"


@admin.register(MessagingMessageLog)
class MessagingMessageLogAdmin(admin.ModelAdmin):
    list_display = ("provider", "identity", "direction", "status", "external_message_id", "created_at")
    list_filter = ("provider", "direction", "status", "created_at")
    search_fields = ("external_message_id", "identity__provider_user_id", "identity__chat_id", "text", "error_message")
    readonly_fields = ("payload", "provider_response", "error_message", "created_at", "sent_at", "received_at")
    date_hierarchy = "created_at"


@admin.register(MessagingActionExecution)
class MessagingActionExecutionAdmin(admin.ModelAdmin):
    list_display = ("action_key", "provider", "identity", "user", "status", "created_at", "finished_at")
    list_filter = ("provider", "status", "action_key", "created_at")
    search_fields = ("action_key", "identity__provider_user_id", "identity__chat_id", "user__mobile_number", "error_message")
    readonly_fields = ("token", "related_content_type", "related_object_id", "result", "error_message", "created_at", "finished_at")
    date_hierarchy = "created_at"
