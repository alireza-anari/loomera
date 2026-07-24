from django.contrib.gis import admin
from .models import (
    BankAccount,
    CustomerNote,
    MembershipEvent,
    Salon,
    SalonMembership,
    SalonOpeningHours,
    SalonsGallery,
    SalonVerification,
    SalonVerificationDocument,
    StaffDashboardPermission,
    SupplementaryInfoView,
)


# ----------------------------------------------------------------------------------------------
class SalonsGalleryInline(admin.TabularInline):
    model = SalonsGallery
    extra = 1


@admin.register(Salon)
class SalonAdmin(admin.GISModelAdmin):
    list_display = [
        "salon_name",
        "slug",
        "is_active",
        "verification_status",
        "zone",
        "salon_manager",
        "show_salon_service",
        "show_salon_stylist",
        "registere_date",
    ]
    list_filter = ["zone", "registere_date", "is_active", "verification_status", "allow_indexing"]
    search_fields = ["salon_name", "slug", "seo_title", "salon_manager__user__mobile_number", "stylists__user__mobile_number"]
    ordering = ["registere_date", "salon_name"]
    prepopulated_fields = {"slug": ("salon_name",)}
    inlines = [
        SalonsGalleryInline,
    ]

    def show_salon_service(self, obj):
        return " , ".join([service.service_name for service in obj.services.all()])

    def show_salon_stylist(self, obj):
        stylist_names = ", ".join([stylist.user.name for stylist in obj.stylists.all()])
        return stylist_names

    show_salon_service.short_description = "خدمات سالن"
    show_salon_stylist.short_description = "آرایشکران سالن "


# --------------------------------------------------------------------------------------------------
@admin.register(SalonOpeningHours)
class SalonOpeningHoursAdmin(admin.ModelAdmin):
    list_display = ["salon", "day_of_week", "is_closed"]


# ---------------------------------------------------------------------------------------------------
@admin.register(SupplementaryInfoView)
class SupplementaryInfoAdmin(admin.ModelAdmin):
    list_display = ["salon", "title", "is_active"]

    def salon(self, obj):
        return obj.salon.salon_name if obj.salon else None


# --------------------------------------------------------------------------------------------------
@admin.register(CustomerNote)
class CustomerNoteAdmin(admin.ModelAdmin):
    list_display = ["customer", "note", "created_at"]

    def customer(self, obj):
        return obj.customer.name if obj.customer else None


# --------------------------------------------------------------------------------------------------
class StaffDashboardPermissionInline(admin.StackedInline):
    model = StaffDashboardPermission
    extra = 0
    can_delete = False


@admin.register(SalonMembership)
class SalonMembershipAdmin(admin.ModelAdmin):
    list_display = ["salon", "stylist", "status", "role_title", "show_on_salon_profile", "created_at"]
    list_filter = ["status", "show_on_salon_profile", "created_at"]
    search_fields = [
        "salon__salon_name",
        "stylist__user__name",
        "stylist__user__family",
        "stylist__user__mobile_number",
        "invited_phone",
        "invited_email",
    ]
    readonly_fields = ["created_at", "updated_at", "accepted_at", "ended_at"]
    inlines = [StaffDashboardPermissionInline]


@admin.register(MembershipEvent)
class MembershipEventAdmin(admin.ModelAdmin):
    list_display = ["membership", "event_type", "old_status", "new_status", "actor", "created_at"]
    list_filter = ["event_type", "new_status", "created_at"]
    search_fields = ["membership__salon__salon_name", "membership__invited_phone", "note"]
    readonly_fields = ["membership", "actor", "event_type", "old_status", "new_status", "note", "metadata", "created_at"]


class SalonVerificationDocumentInline(admin.TabularInline):
    model = SalonVerificationDocument
    extra = 0
    readonly_fields = ["created_at", "updated_at", "reviewed_at"]


@admin.register(SalonVerification)
class SalonVerificationAdmin(admin.ModelAdmin):
    list_display = ["salon", "status", "identity_status", "business_info_status", "bank_account_status", "contract_status", "updated_at"]
    list_filter = ["status", "identity_status", "business_info_status", "bank_account_status", "contract_status"]
    search_fields = ["salon__salon_name", "salon__payout_iban", "salon__payout_account_holder_name"]
    readonly_fields = ["created_at", "updated_at", "reviewed_at"]
    inlines = [SalonVerificationDocumentInline]


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ["salon", "masked_iban", "account_owner_name", "bank_name", "is_verified", "is_default", "created_at"]
    list_filter = ["is_verified", "is_default", "bank_name", "created_at"]
    search_fields = ["salon__salon_name", "iban", "account_owner_name"]
    readonly_fields = ["created_at", "updated_at", "verified_at"]

    def masked_iban(self, obj):
        iban = obj.iban or ""
        if len(iban) <= 8:
            return iban
        return f"{iban[:4]}…{iban[-4:]}"

    masked_iban.short_description = "شبا"
