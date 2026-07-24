from django.contrib import admin

from .models import Coupon, DiscountBasket, DiscountBasketDetails, DiscountCampaign, DiscountRedemption, DiscountSnapshot, DiscountStackingPolicy


# -----------------------------------------------------------------------------------
@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("coupon_code", "salon", "start_date", "end_date", "discount", "max_discount_amount", "is_active")
    list_filter = ("is_active",)


# -----------------------------------------------------------------------------------
class DiscountBasketDetailsInline(admin.TabularInline):
    model = DiscountBasketDetails
    extra = 3


@admin.register(DiscountBasket)
class DiscountBasketAdmin(admin.ModelAdmin):
    list_display = ("discount_title", "salon", "start_date", "end_date", "discount", "max_discount_amount", "is_active")
    list_filter = ("is_active",)
    inlines = [
        DiscountBasketDetailsInline,
    ]


@admin.register(DiscountCampaign)
class DiscountCampaignAdmin(admin.ModelAdmin):
    list_display = ("title", "salon", "campaign_type", "start_date", "end_date", "is_active", "is_archived")
    list_filter = ("campaign_type", "is_active", "is_archived")
    filter_horizontal = ("coupons", "baskets")


@admin.register(DiscountSnapshot)
class DiscountSnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "source_type", "code", "title", "order", "customer", "discount_amount", "created_at")
    list_filter = ("source_type", "created_at")
    search_fields = ("code", "title", "order__order_code")
    readonly_fields = ("created_at", "updated_at")


@admin.register(DiscountRedemption)
class DiscountRedemptionAdmin(admin.ModelAdmin):
    list_display = ("id", "source_type", "code", "order", "customer", "discount_amount", "status", "redeemed_at")
    list_filter = ("source_type", "status", "redeemed_at")
    search_fields = ("code", "title", "order__order_code")
    readonly_fields = ("redeemed_at", "created_at", "updated_at")


@admin.register(DiscountStackingPolicy)
class DiscountStackingPolicyAdmin(admin.ModelAdmin):
    list_display = ("title", "salon", "policy", "stacking_mode", "max_discount_sources", "priority", "is_active")
    list_filter = ("policy", "stacking_mode", "is_active")
    search_fields = ("title", "salon__salon_name")
    readonly_fields = ("created_at", "updated_at")
