from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone

from .forms import CustomUserChangeForm, CustomUserCreationForm
from .models import (
    AccountDeletionRequest,
    Customer,
    CustomerNotification,
    CustomUser,
    SalonManager,
    Stylist,
    UserConsent,
    WorkSamples,
)

try:
    from .models import CustomerAddress
except ImportError:
    CustomerAddress = None


# -------------------------------------------------------------------------
# Custom User Admin
class CustomUserAdmin(UserAdmin):
    forms = CustomUserChangeForm
    add_forms = CustomUserCreationForm

    list_display = ["mobile_number", "email", "name", "family"]
    list_filter = ("is_active", "is_admin")
    search_fields = ("name", "family", "mobile_number", "email")
    ordering = ("name", "family")
    filter_horizontal = ("user_permissions", "groups")

    fieldsets = (
        (None, {"fields": ("mobile_number", "password")}),
        ("Personal Info", {"fields": ("name", "family", "email")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_admin", "groups", "user_permissions")},
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "fields": (
                    "mobile_number",
                    "email",
                    "name",
                    "family",
                    "is_active",
                    "is_admin",
                    "password1",
                    "password2",
                )
            },
        ),
    )


admin.site.register(CustomUser, CustomUserAdmin)


# ------------------------------------------------------------------------------------------------------------------------------
# Customer Admin
@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("user", "address", "profile_image")


if CustomerAddress is not None:
    @admin.register(CustomerAddress)
    class CustomerAddressAdmin(admin.ModelAdmin):
        list_display = ("customer", "title", "city", "phone_number", "is_default", "updated_at")
        list_filter = ("is_default", "city")
        search_fields = ("customer__user__name", "customer__user__family", "phone_number", "address_line")



@admin.register(CustomerNotification)
class CustomerNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "user",
        "customer",
        "category",
        "priority",
        "is_read",
        "created_at",
    )
    list_filter = ("category", "priority", "is_read", "created_at")
    search_fields = (
        "title",
        "body",
        "user__mobile_number",
        "user__name",
        "user__family",
        "customer__user__mobile_number",
    )
    readonly_fields = ("created_at", "read_at")
    date_hierarchy = "created_at"
    ordering = ("-created_at", "-id")
    list_select_related = ("user", "customer", "customer__user")
    actions = ("mark_as_read", "mark_as_unread")

    @admin.action(description="علامت‌گذاری به عنوان خوانده‌شده")
    def mark_as_read(self, request, queryset):
        queryset.filter(is_read=False).update(is_read=True, read_at=timezone.now())

    @admin.action(description="علامت‌گذاری به عنوان خوانده‌نشده")
    def mark_as_unread(self, request, queryset):
        queryset.update(is_read=False, read_at=None)



@admin.register(UserConsent)
class UserConsentAdmin(admin.ModelAdmin):
    list_display = ("user", "consent_type", "version", "is_granted", "source", "created_at")
    list_filter = ("consent_type", "is_granted", "source", "created_at")
    search_fields = ("user__mobile_number", "user__name", "user__family", "version")
    readonly_fields = ("user", "consent_type", "version", "is_granted", "source", "ip_address", "user_agent", "metadata", "created_at")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AccountDeletionRequest)
class AccountDeletionRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "original_user_id", "original_mobile_number", "reason", "status", "requested_at", "anonymized_at")
    list_filter = ("status", "reason", "requested_at", "anonymized_at")
    search_fields = ("original_mobile_number", "original_email", "original_user_id")
    readonly_fields = (
        "user",
        "original_user_id",
        "original_mobile_number",
        "original_email",
        "reason",
        "status",
        "requested_at",
        "anonymized_at",
        "completed_at",
        "metadata",
    )
    date_hierarchy = "requested_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# --------------------------------------------------------------------------------------------------------------------------------
# Stylist Admin
@admin.register(Stylist)
class StylistAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "professional_name",
        "show_expert",
        "public_visibility",
        "is_verified_professional",
        "is_active",
    ]
    list_filter = ["is_active", "public_visibility", "is_verified_professional", "address"]
    search_fields = ["user__name", "user__family", "user__mobile_number", "display_name", "expert", "address"]
    readonly_fields = ["profile_locked_note"]

    def professional_name(self, obj):
        return obj.professional_display_name

    professional_name.short_description = "نام حرفه‌ای"

    def show_expert(self, obj):
        return " , ".join([service.service_name for service in obj.services_of_stylist.all()])

    show_expert.short_description = "تخصص ها "


# --------------------------------------------------------------------------------------------------------------------------------
# Salon Manager Admin
@admin.register(SalonManager)
class SalonManagerAdmin(admin.ModelAdmin):
    list_display = ["user", "address", "profile_image", "salon_number", "is_active"]
    list_filter = ["is_active", "address"]
    search_fields = ["user", "address"]


# --------------------------------------------------------------------------------------------------------------------------------
# Work Samples
@admin.register(WorkSamples)
class WorkSamplesAdmin(admin.ModelAdmin):
    list_display = ["stylist", "salon", "service", "is_active", "is_public", "is_verified_work", "review_status"]
    list_filter = ["is_active", "is_public", "is_verified_work", "review_status", "client_consent_status"]
    search_fields = ["stylist__user__name", "stylist__user__family", "salon__salon_name", "service__service_name", "description"]
