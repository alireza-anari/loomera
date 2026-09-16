from apps.main.ui_feedback import user_error_message
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from .models import (
    BookingPaymentPolicy,
    CancellationPolicy,
    CommissionPolicy,
    CustomerCompensation,
    ExtraCharge,
    FinancialAccount,
    FinancialAdjustment,
    LedgerEntry,
    OrderDetailFinancialSnapshot,
    Payment,
    PaymentProvider,
    PaymentTransaction,
    RefundRequest,
    SalonPaymentProviderConfig,
    SalonSettlement,
    StaffEarning,
    StaffPayoutRequest,
    SalonWallet,
    SalonWalletTransaction,
    SalonWalletWithdrawalRequest,
    StylistWallet,
    StylistWalletTransaction,
    StylistWalletWithdrawalRequest,
    Wallet,
    WalletTransaction,
    WalletWithdrawalRequest,
)


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_select_related = ("wallet__user", "order")
    list_display = ("wallet", "transaction_type", "amount", "running_balance", "order", "created_at")
    list_filter = ("transaction_type", "created_at")
    search_fields = ("wallet__user__mobile_number", "wallet__user__name", "order__id", "order__order_code")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SalonWalletTransaction)
class SalonWalletTransactionAdmin(admin.ModelAdmin):
    list_select_related = ("wallet__salon", "order")
    list_display = ("wallet", "transaction_type", "pending_delta", "available_delta", "pending_balance_after", "available_balance_after", "order", "created_at")
    list_filter = ("transaction_type", "created_at")
    search_fields = ("wallet__salon__salon_name", "order__id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_select_related = ("customer__user", "order",)
    list_display = (
        "id",
        "purpose",
        "provider",
        "state",
        "amount",
        "customer",
        "order",
        "gateway_track_id",
        "is_finally",
        "sandbox_mode",
        "verified_at",
        "register_date",
    )
    list_filter = ("purpose", "provider", "state", "sandbox_mode", "is_finally", "register_date")
    search_fields = (
        "ref_id",
        "gateway_track_id",
        "callback_token",
        "idempotency_key",
        "customer__user__mobile_number",
        "customer__user__name",
        "order__id",
        "order__order_number",
        "order__order_code",
    )
    readonly_fields = ("register_date", "update_date", "verified_at", "ref_id", "gateway_track_id", "callback_token", "idempotency_key", "meta", "status_code")


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "balance")
    search_fields = ("user__mobile_number", "user__name", "user__username")


@admin.register(SalonWallet)
class SalonWalletAdmin(admin.ModelAdmin):
    list_display = ("salon", "pending_balance", "available_balance", "total_balance", "updated_at")
    list_select_related = ("salon",)
    search_fields = ("salon__salon_name",)
    readonly_fields = ("created_at", "updated_at", "total_balance")


@admin.register(SalonSettlement)
class SalonSettlementAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "salon",
        "payment_method",
        "payment_provider",
        "paid_amount",
        "refund_amount",
        "platform_commission_amount",
        "net_amount_due_to_salon",
        "payout_state",
        "eligible_for_payout_at",
        "paid_out_at",
    )
    list_filter = ("payment_method", "payment_provider", "payout_state", "created_at")
    search_fields = ("order__id", "order__order_number", "order__order_code", "salon__salon_name", "customer__user__mobile_number", "payment__ref_id", "payment__gateway_track_id")
    readonly_fields = ("created_at", "updated_at", "policy_snapshot")


def approve_wallet_withdrawals(modeladmin, request, queryset):
    done = 0
    for item in queryset.select_related("wallet__user"):
        try:
            item.approve(note="تایید توسط تیم مالی")
            done += 1
        except ValidationError as exc:
            messages.error(request, f"درخواست {item.pk}: {user_error_message(exc)}")
    if done:
        messages.success(request, f"{done} درخواست برداشت مشتری تایید شد.")


def reject_wallet_withdrawals(modeladmin, request, queryset):
    done = 0
    for item in queryset.select_related("wallet__user"):
        try:
            item.reject(note="رد توسط تیم مالی و بازگشت خودکار موجودی")
            done += 1
        except ValidationError as exc:
            messages.error(request, f"درخواست {item.pk}: {user_error_message(exc)}")
    if done:
        messages.warning(request, f"{done} درخواست برداشت مشتری رد شد و موجودی آن‌ها برگشت داده شد.")


def approve_salon_withdrawals(modeladmin, request, queryset):
    done = 0
    for item in queryset.select_related("wallet__salon"):
        try:
            item.approve(note="تایید توسط تیم مالی")
            done += 1
        except ValidationError as exc:
            messages.error(request, f"درخواست {item.pk}: {user_error_message(exc)}")
    if done:
        messages.success(request, f"{done} درخواست برداشت سالن تایید شد.")


def reject_salon_withdrawals(modeladmin, request, queryset):
    done = 0
    for item in queryset.select_related("wallet__salon"):
        try:
            item.reject(note="رد توسط تیم مالی و بازگشت خودکار موجودی")
            done += 1
        except ValidationError as exc:
            messages.error(request, f"درخواست {item.pk}: {user_error_message(exc)}")
    if done:
        messages.warning(request, f"{done} درخواست برداشت سالن رد شد و موجودی آن‌ها برگشت داده شد.")


def cancel_wallet_withdrawals(modeladmin, request, queryset):
    done = 0
    for item in queryset.select_related("wallet__user"):
        try:
            item.cancel(note="لغو توسط تیم مالی و بازگشت خودکار موجودی")
            done += 1
        except ValidationError as exc:
            messages.error(request, f"درخواست {item.pk}: {user_error_message(exc)}")
    if done:
        messages.warning(request, f"{done} درخواست برداشت مشتری لغو شد و موجودی آن‌ها برگشت داده شد.")


def cancel_salon_withdrawals(modeladmin, request, queryset):
    done = 0
    for item in queryset.select_related("wallet__salon"):
        try:
            item.cancel(note="لغو توسط تیم مالی و بازگشت خودکار موجودی")
            done += 1
        except ValidationError as exc:
            messages.error(request, f"درخواست {item.pk}: {user_error_message(exc)}")
    if done:
        messages.warning(request, f"{done} درخواست برداشت سالن لغو شد و موجودی آن‌ها برگشت داده شد.")


approve_wallet_withdrawals.short_description = "تایید درخواست‌های برداشت انتخاب‌شده"
reject_wallet_withdrawals.short_description = "رد درخواست‌های برداشت و بازگرداندن موجودی"
cancel_wallet_withdrawals.short_description = "لغو درخواست‌های برداشت و بازگرداندن موجودی"
approve_salon_withdrawals.short_description = "تایید درخواست‌های برداشت سالن"
reject_salon_withdrawals.short_description = "رد درخواست‌های برداشت سالن و بازگرداندن موجودی"
cancel_salon_withdrawals.short_description = "لغو درخواست‌های برداشت سالن و بازگرداندن موجودی"


@admin.register(WalletWithdrawalRequest)
class WalletWithdrawalRequestAdmin(admin.ModelAdmin):
    list_select_related = ("wallet__user",)
    list_display = ("wallet", "amount", "status", "iban", "account_holder_name", "created_at", "reviewed_at")
    list_filter = ("status", "created_at", "reviewed_at")
    search_fields = (
        "wallet__user__mobile_number",
        "wallet__user__name",
        "iban",
        "account_holder_name",
    )
    readonly_fields = ("created_at", "updated_at", "reviewed_at", "legacy_destination_iban", "legacy_destination_account_holder_name", "legacy_destination_bank_name")
    actions = [approve_wallet_withdrawals, reject_wallet_withdrawals, cancel_wallet_withdrawals]


@admin.register(SalonWalletWithdrawalRequest)
class SalonWalletWithdrawalRequestAdmin(admin.ModelAdmin):
    list_select_related = ("wallet__salon",)
    list_display = ("wallet", "amount", "status", "iban", "account_holder_name", "created_at", "reviewed_at")
    list_filter = ("status", "created_at", "reviewed_at")
    search_fields = ("wallet__salon__salon_name", "iban", "account_holder_name")
    readonly_fields = ("created_at", "updated_at", "reviewed_at", "legacy_destination_iban", "legacy_destination_account_holder_name", "legacy_destination_bank_name")
    actions = [approve_salon_withdrawals, reject_salon_withdrawals, cancel_salon_withdrawals]


@admin.register(OrderDetailFinancialSnapshot)
class OrderDetailFinancialSnapshotAdmin(admin.ModelAdmin):
    list_select_related = (
        "order",
        "order_detail",
        "salon",
        "stylist__user",
        "service",
        "commission_rule",
    )
    list_display = (
        "order",
        "salon",
        "stylist",
        "service",
        "gross_amount",
        "platform_commission_allocated",
        "material_cost_total",
        "stylist_net_share",
        "salon_net_share",
        "salon_net_profit",
        "status",
        "finalized_at",
    )
    list_filter = (
        "status",
        "salon",
        "service",
        "payment_method",
        "created_at",
        "finalized_at",
    )
    search_fields = (
        "order__order_number",
        "order__order_code",
        "salon__salon_name",
        "stylist__user__name",
        "stylist__user__family",
        "stylist__user__mobile_number",
        "service__service_name",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "finalized_at",
        "reversed_at",
        "rule_snapshot",
        "material_snapshot",
        "calculation_snapshot",
    )
    raw_id_fields = (
        "order_detail",
        "order",
        "settlement",
        "salon",
        "stylist",
        "service",
        "commission_rule",
    )


@admin.register(StylistWallet)
class StylistWalletAdmin(admin.ModelAdmin):
    list_select_related = ("stylist__user",)
    list_display = (
        "stylist",
        "pending_balance",
        "available_balance",
        "total_balance",
        "updated_at",
    )
    search_fields = (
        "stylist__user__name",
        "stylist__user__family",
        "stylist__user__mobile_number",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "total_balance",
    )


@admin.register(StylistWalletTransaction)
class StylistWalletTransactionAdmin(admin.ModelAdmin):
    list_select_related = (
        "wallet__stylist__user",
        "order",
        "order_detail",
        "financial_snapshot",
    )
    list_display = (
        "wallet",
        "transaction_type",
        "pending_delta",
        "available_delta",
        "pending_balance_after",
        "available_balance_after",
        "order",
        "order_detail",
        "created_at",
    )
    list_filter = (
        "transaction_type",
        "created_at",
    )
    search_fields = (
        "wallet__stylist__user__name",
        "wallet__stylist__user__family",
        "wallet__stylist__user__mobile_number",
        "order__id",
        "order__order_number",
        "order__order_code",
    )
    readonly_fields = ("created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


def approve_stylist_withdrawals(modeladmin, request, queryset):
    done = 0

    for item in queryset.select_related("wallet__stylist__user"):
        try:
            item.approve(note="تایید توسط تیم مالی")
            done += 1
        except ValidationError as exc:
            messages.error(request, f"درخواست {item.pk}: {user_error_message(exc)}")

    if done:
        messages.success(request, f"{done} درخواست برداشت آرایشگر تایید شد.")


def reject_stylist_withdrawals(modeladmin, request, queryset):
    done = 0

    for item in queryset.select_related("wallet__stylist__user"):
        try:
            item.reject(note="رد توسط تیم مالی و بازگشت خودکار موجودی")
            done += 1
        except ValidationError as exc:
            messages.error(request, f"درخواست {item.pk}: {user_error_message(exc)}")

    if done:
        messages.warning(
            request, f"{done} درخواست برداشت آرایشگر رد شد و موجودی آن برگشت داده شد."
        )


def cancel_stylist_withdrawals(modeladmin, request, queryset):
    done = 0

    for item in queryset.select_related("wallet__stylist__user"):
        try:
            item.cancel(note="لغو توسط تیم مالی و بازگشت خودکار موجودی")
            done += 1
        except ValidationError as exc:
            messages.error(request, f"درخواست {item.pk}: {user_error_message(exc)}")

    if done:
        messages.warning(
            request, f"{done} درخواست برداشت آرایشگر لغو شد و موجودی آن برگشت داده شد."
        )


approve_stylist_withdrawals.short_description = "تایید درخواست‌های برداشت آرایشگر"
reject_stylist_withdrawals.short_description = (
    "رد درخواست‌های برداشت آرایشگر و بازگرداندن موجودی"
)
cancel_stylist_withdrawals.short_description = (
    "لغو درخواست‌های برداشت آرایشگر و بازگرداندن موجودی"
)


@admin.register(StylistWalletWithdrawalRequest)
class StylistWalletWithdrawalRequestAdmin(admin.ModelAdmin):
    list_select_related = ("wallet__stylist__user",)
    list_display = (
        "wallet",
        "amount",
        "status",
        "iban",
        "account_holder_name",
        "created_at",
        "reviewed_at",
        "payment_receipt",
    )
    list_filter = (
        "status",
        "created_at",
        "reviewed_at",
    )
    search_fields = (
        "wallet__stylist__user__name",
        "wallet__stylist__user__family",
        "wallet__stylist__user__mobile_number",
        "iban",
        "account_holder_name",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "reviewed_at",
    )
    actions = [
        approve_stylist_withdrawals,
        reject_stylist_withdrawals,
        cancel_stylist_withdrawals,
    ]


@admin.register(FinancialAccount)
class FinancialAccountAdmin(admin.ModelAdmin):
    list_display = ("account_type", "owner", "currency", "is_active", "created_at")
    list_filter = ("account_type", "is_active", "currency")
    search_fields = ("owner_object_id",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_select_related = ("account", "order", "order_detail", "created_by")
    list_display = ("entry_type", "direction", "amount", "account", "order", "order_detail", "status", "created_at")
    list_filter = ("entry_type", "direction", "status", "created_at")
    search_fields = ("order__id", "order__order_code", "order_detail__id", "group_id")
    readonly_fields = ("group_id", "created_at", "metadata")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CommissionPolicy)
class CommissionPolicyAdmin(admin.ModelAdmin):
    list_display = ("salon", "commission_type", "commission_value", "applies_to_new_client_only", "is_active", "effective_from", "effective_to")
    list_filter = ("is_active", "commission_type", "applies_to_new_client_only")
    search_fields = ("salon__salon_name",)


@admin.register(BookingPaymentPolicy)
class BookingPaymentPolicyAdmin(admin.ModelAdmin):
    list_display = ("salon", "service", "payment_mode", "deposit_type", "deposit_value", "is_enabled")
    list_filter = ("payment_mode", "deposit_type", "is_enabled")
    search_fields = ("salon__salon_name", "service__service_name")


@admin.register(CancellationPolicy)
class CancellationPolicyAdmin(admin.ModelAdmin):
    list_display = ("salon", "service", "free_cancellation_until_hours", "client_late_cancel_penalty_type", "client_late_cancel_penalty_value", "mirror_client_penalty_for_salon", "is_enabled")
    list_filter = ("is_enabled", "client_late_cancel_penalty_type", "no_show_penalty_type", "mirror_client_penalty_for_salon")
    search_fields = ("salon__salon_name", "service__service_name")


@admin.register(PaymentProvider)
class PaymentProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "provider_type", "is_active", "supports_deposit", "supports_full_payment", "supports_bnpl")
    list_filter = ("provider_type", "is_active", "supports_bnpl")
    search_fields = ("name", "code")


@admin.register(SalonPaymentProviderConfig)
class SalonPaymentProviderConfigAdmin(admin.ModelAdmin):
    list_display = ("salon", "provider", "is_enabled", "min_amount", "max_amount", "settlement_type")
    list_filter = ("is_enabled", "provider")
    search_fields = ("salon__salon_name", "provider__name", "provider__code")
    filter_horizontal = ("allowed_services",)


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ("order", "method", "provider", "amount", "status", "paid_at", "created_at")
    list_filter = ("method", "status", "provider", "created_at")
    search_fields = ("order__id", "order__order_code", "provider_reference")
    readonly_fields = ("provider_payload", "created_at", "updated_at")


@admin.register(ExtraCharge)
class ExtraChargeAdmin(admin.ModelAdmin):
    list_display = ("order_detail", "title", "amount", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "order_detail__id", "order_detail__order__order_code")


@admin.register(StaffEarning)
class StaffEarningAdmin(admin.ModelAdmin):
    list_select_related = ("salon", "stylist__user", "order_detail", "financial_snapshot")
    list_display = ("salon", "stylist", "order_detail", "gross_share", "material_deduction", "net_profit", "status", "calculated_at")
    list_filter = ("status", "salon", "created_at")
    search_fields = ("salon__salon_name", "stylist__user__name", "stylist__user__mobile_number", "order_detail__id")


@admin.register(StaffPayoutRequest)
class StaffPayoutRequestAdmin(admin.ModelAdmin):
    list_display = ("salon", "stylist", "requested_amount", "approved_amount", "status", "requested_at", "paid_at")
    list_filter = ("status", "salon", "requested_at")
    search_fields = ("salon__salon_name", "stylist__user__name", "stylist__user__mobile_number")
    filter_horizontal = ("earnings",)


@admin.register(FinancialAdjustment)
class FinancialAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("order", "order_detail", "amount", "target_field", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("order__id", "order__order_code", "reason", "target_field")


@admin.register(RefundRequest)
class RefundRequestAdmin(admin.ModelAdmin):
    list_display = ("order", "amount", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("order__id", "order__order_code", "reason")


@admin.register(CustomerCompensation)
class CustomerCompensationAdmin(admin.ModelAdmin):
    list_display = ("order", "salon", "customer", "amount", "status", "created_at")
    list_filter = ("status", "salon", "created_at")
    search_fields = ("order__id", "order__order_code", "salon__salon_name", "customer__user__mobile_number")
