from django.contrib import admin

from .models import (
    StylistSchedule,
    StylistTimeOff,
    StaffLeaveRequest,
    StaffScheduleRequest,
    ProfessionalResumeSubmission,
)


# --------------------------------------------------------------------------
@admin.register(StylistSchedule)
class StylistWeeklyScheduleAdmin(admin.ModelAdmin):
    list_display = ["stylist", "salon", "service"]


# --------------------------------------------------------------------------
@admin.register(StylistTimeOff)
class StylistTimeOffAdmin(admin.ModelAdmin):
    list_display = ["stylist", "date", "reason"]


@admin.register(StaffLeaveRequest)
class StaffLeaveRequestAdmin(admin.ModelAdmin):
    list_display = ["stylist", "salon", "date", "start_time", "end_time", "status", "created_at"]
    list_filter = ["status", "salon", "date"]
    search_fields = ["stylist__user__name", "stylist__user__family", "stylist__user__mobile_number", "salon__salon_name", "reason"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(StaffScheduleRequest)
class StaffScheduleRequestAdmin(admin.ModelAdmin):
    list_display = [
        "stylist",
        "salon",
        "service",
        "date",
        "start_time",
        "end_time",
        "status",
        "created_at",
    ]
    list_filter = ["status", "salon", "date"]
    search_fields = [
        "stylist__user__name",
        "stylist__user__family",
        "stylist__user__mobile_number",
        "salon__salon_name",
        "note",
        "review_note",
    ]
    readonly_fields = ["created_schedule", "created_at", "updated_at"]


@admin.register(ProfessionalResumeSubmission)
class ProfessionalResumeSubmissionAdmin(admin.ModelAdmin):
    list_display = ["stylist", "salon", "status", "created_at", "viewed_at", "responded_at"]
    list_filter = ["status", "salon", "created_at"]
    search_fields = [
        "stylist__user__name",
        "stylist__user__family",
        "stylist__user__mobile_number",
        "salon__salon_name",
        "message",
    ]
    readonly_fields = ["resume_snapshot", "created_at", "updated_at"]
