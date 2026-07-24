from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from .models import AdminAuditLog, AdminRoleAssignment, DisputeCase, DisputeEvent, MediaProcessingJob, OperationalJobRun, PlatformSetting, SecurityAuditLog, SupportAttachment, SupportEvent, SupportTicket, SupportTicketMessage, SuspensionRecord
from apps.accounts.notifications import notify_support_reply


@admin.register(PlatformSetting)
class PlatformSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value_type", "is_sensitive", "is_runtime_editable", "updated_by", "updated_at")
    list_filter = ("value_type", "is_sensitive", "is_runtime_editable")
    search_fields = ("key", "description")
    readonly_fields = ("created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        previous = {}
        if change and obj.pk:
            previous = (
                PlatformSetting.objects.filter(pk=obj.pk)
                .values("key", "value", "value_type", "is_sensitive", "is_runtime_editable")
                .first()
                or {}
            )
        obj.updated_by = request.user if request.user.is_authenticated else None
        super().save_model(request, obj, form, change)
        AdminAuditLog.objects.create(
            actor=request.user if request.user.is_authenticated else None,
            action="platform_setting.updated" if change else "platform_setting.created",
            target_content_type=ContentType.objects.get_for_model(obj),
            target_object_id=obj.pk,
            old_value=previous,
            new_value={
                "key": obj.key,
                "value": "***" if obj.is_sensitive else obj.value,
                "value_type": obj.value_type,
                "is_sensitive": obj.is_sensitive,
                "is_runtime_editable": obj.is_runtime_editable,
            },
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )


@admin.register(AdminAuditLog)
class AdminAuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "actor", "target_content_type", "target_object_id", "created_at")
    list_filter = ("action", "target_content_type", "created_at")
    search_fields = ("action", "reason", "actor__mobile_number", "actor__name", "actor__family")
    readonly_fields = (
        "actor",
        "action",
        "target_content_type",
        "target_object_id",
        "old_value",
        "new_value",
        "reason",
        "metadata",
        "ip_address",
        "user_agent",
        "created_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(SecurityAuditLog)
class SecurityAuditLogAdmin(admin.ModelAdmin):
    list_display = ("event_type", "severity", "actor", "ip_address", "created_at")
    list_filter = ("event_type", "severity", "created_at")
    search_fields = ("event_type", "actor__mobile_number", "actor__name", "actor__family", "ip_address")
    readonly_fields = (
        "actor",
        "event_type",
        "severity",
        "target_content_type",
        "target_object_id",
        "metadata",
        "ip_address",
        "user_agent",
        "created_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(AdminRoleAssignment)
class AdminRoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "is_active", "assigned_by", "updated_at")
    list_filter = ("role", "is_active")
    search_fields = ("user__mobile_number", "user__name", "user__family", "note")
    readonly_fields = ("created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if not obj.assigned_by_id:
            obj.assigned_by = request.user if request.user.is_authenticated else None
        super().save_model(request, obj, form, change)
        AdminAuditLog.objects.create(
            actor=request.user if request.user.is_authenticated else None,
            action="admin_role.updated" if change else "admin_role.created",
            target_content_type=ContentType.objects.get_for_model(obj),
            target_object_id=obj.pk,
            new_value={"user_id": obj.user_id, "role": obj.role, "is_active": obj.is_active},
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )


@admin.register(SuspensionRecord)
class SuspensionRecordAdmin(admin.ModelAdmin):
    list_display = ("target_object", "status", "reason", "created_by", "created_at", "expires_at")
    list_filter = ("status", "created_at", "expires_at")
    search_fields = ("reason", "internal_note", "user_facing_reason")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user if request.user.is_authenticated else None
        super().save_model(request, obj, form, change)
        AdminAuditLog.objects.create(
            actor=request.user if request.user.is_authenticated else None,
            action="suspension.updated" if change else "suspension.created",
            target_content_type=ContentType.objects.get_for_model(obj),
            target_object_id=obj.pk,
            new_value={"target": str(obj.target_object), "status": obj.status, "reason": obj.reason},
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )


@admin.register(OperationalJobRun)
class OperationalJobRunAdmin(admin.ModelAdmin):
    list_display = ("job_name", "status", "started_at", "finished_at", "duration_ms", "summary")
    list_filter = ("job_name", "status", "started_at")
    search_fields = ("job_name", "summary", "error_message")
    readonly_fields = ("job_name", "status", "started_at", "finished_at", "duration_ms", "summary", "error_message", "metadata")
    date_hierarchy = "started_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(MediaProcessingJob)
class MediaProcessingJobAdmin(admin.ModelAdmin):
    list_display = ("id", "file_kind", "status", "size_bytes", "attempts", "created_at", "processed_at")
    list_filter = ("file_kind", "status", "created_at")
    search_fields = ("source_file", "processed_file", "thumbnail_file", "error_message")
    readonly_fields = ("created_at", "updated_at", "processed_at")
    date_hierarchy = "created_at"


class SupportTicketMessageInline(admin.TabularInline):
    model = SupportTicketMessage
    extra = 0
    readonly_fields = ("created_at",)
    fields = ("sender", "sender_role", "message_type", "body", "created_at")


class SupportAttachmentInline(admin.TabularInline):
    model = SupportAttachment
    extra = 0
    readonly_fields = ("created_at",)
    fields = ("message", "file", "uploaded_by", "file_type", "created_at")


class SupportEventInline(admin.TabularInline):
    model = SupportEvent
    extra = 0
    readonly_fields = ("created_at",)
    fields = ("event_type", "actor", "old_value", "new_value", "note", "created_at")


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "full_name", "email", "category", "priority", "status", "assigned_team", "updated_at", "created_at")
    list_filter = ("category", "priority", "assigned_team", "status", "issue_type", "created_at", "updated_at")
    search_fields = ("full_name", "email", "mobile", "subject", "description", "admin_reply")
    readonly_fields = ("created_at", "updated_at", "first_response_at", "resolved_at", "closed_at", "last_response_at")
    date_hierarchy = "created_at"
    inlines = [SupportTicketMessageInline, SupportAttachmentInline, SupportEventInline]
    fieldsets = (
        (None, {"fields": ("user", "requester_role", "full_name", "email", "mobile", "city")}),
        ("درخواست", {"fields": ("issue_type", "category", "sub_category", "support_reason", "subject", "description", "attachment")}),
        ("ارتباط", {"fields": ("salon", "stylist", "order", "order_detail", "related_content_type", "related_object_id")}),
        ("پیگیری", {"fields": ("status", "priority", "assigned_team", "assigned_to", "admin_reply", "sla_due_at", "first_response_at", "resolved_at", "closed_at", "last_response_by", "last_response_at")}),
        ("زمان", {"fields": ("created_at", "updated_at")}),
    )

    def save_model(self, request, obj, form, change):
        previous_reply = ""
        previous_status = ""
        if change and obj.pk:
            previous = (
                SupportTicket.objects.filter(pk=obj.pk)
                .values("admin_reply", "status")
                .first()
                or {}
            )
            previous_reply = (previous.get("admin_reply") or "").strip()
            previous_status = previous.get("status") or ""

        super().save_model(request, obj, form, change)

        current_reply = (obj.admin_reply or "").strip()
        should_notify_reply = bool(obj.user_id and current_reply and current_reply != previous_reply)
        if should_notify_reply:
            from .support_services import add_support_message

            add_support_message(
                ticket=obj,
                sender=request.user,
                sender_role="support_admin",
                body=current_reply,
                message_type=SupportTicketMessage.MESSAGE_TYPE_PUBLIC,
                request=request,
            )
            transaction.on_commit(
                lambda ticket=obj: notify_support_reply(
                    user=ticket.user,
                    ticket=ticket,
                    action_url=f"/main/support/tickets/{ticket.pk}/",
                )
            )

        if change and previous_status != obj.status:
            AdminAuditLog.objects.create(
                actor=request.user if request.user.is_authenticated else None,
                action="support_ticket.status_changed",
                target_content_type=ContentType.objects.get_for_model(obj),
                target_object_id=obj.pk,
                old_value={"status": previous_status},
                new_value={"status": obj.status},
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )


@admin.register(SupportTicketMessage)
class SupportTicketMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket", "sender", "sender_role", "message_type", "created_at")
    list_filter = ("sender_role", "message_type", "created_at")
    search_fields = ("ticket__id", "body", "sender__mobile_number", "sender__email")
    readonly_fields = ("created_at",)


@admin.register(SupportAttachment)
class SupportAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket", "message", "uploaded_by", "file_type", "created_at")
    list_filter = ("file_type", "created_at")
    search_fields = ("ticket__id", "uploaded_by__mobile_number", "uploaded_by__email")
    readonly_fields = ("created_at",)


@admin.register(SupportEvent)
class SupportEventAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket", "event_type", "actor", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("ticket__id", "note", "actor__mobile_number", "actor__email")
    readonly_fields = ("created_at",)


class DisputeEventInline(admin.TabularInline):
    model = DisputeEvent
    extra = 0
    readonly_fields = ("created_at",)
    fields = ("event_type", "actor", "old_status", "new_status", "note", "created_at")


@admin.register(DisputeCase)
class DisputeCaseAdmin(admin.ModelAdmin):
    list_display = ("id", "dispute_type", "status", "priority", "salon", "stylist", "order_detail", "updated_at", "created_at")
    list_filter = ("dispute_type", "status", "priority", "created_at", "updated_at")
    search_fields = ("subject", "description", "salon__salon_name", "stylist__user__mobile_number", "order__id", "order_detail__id")
    readonly_fields = ("created_at", "updated_at", "resolved_at")
    inlines = [DisputeEventInline]


@admin.register(DisputeEvent)
class DisputeEventAdmin(admin.ModelAdmin):
    list_display = ("id", "dispute", "event_type", "actor", "old_status", "new_status", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("dispute__id", "note", "actor__mobile_number", "actor__email")
    readonly_fields = ("created_at",)
