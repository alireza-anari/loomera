# مرحله ۱۱: تخفیف‌ها، کمپین‌ها و پیشنهادهای ویژه

## هدف

این مرحله ساختار تخفیف‌های Loomera را از «کد و سبد ساده» به یک سیستم قابل گزارش، امن و قابل توسعه برای کمپین، محدودیت استفاده، اسنپ‌شات مالی و تحلیل کمپین ارتقا می‌دهد؛ بدون حذف ساختار قبلی `Coupon` و `DiscountBasket`.

## تصمیم‌های سازگاری

- مدل‌های قبلی `Coupon`, `DiscountBasket`, `DiscountBasketDetails` حفظ شدند.
- حذف فیزیکی کد/سبد در داشبورد سالن به آرشیو نرم تبدیل شد.
- Checkout فعلی حفظ شد، اما اعتبارسنجی کد تخفیف به `DiscountEligibilityService` منتقل شد.
- استفاده واقعی از تخفیف در `DiscountRedemption` ثبت می‌شود.
- قوانین تخفیف روی سفارش در `discount_rules_snapshot` و `DiscountSnapshot` ذخیره می‌شود.

## مدل‌های جدید

- `DiscountCampaign`
- `DiscountTarget`
- `DiscountRedemption`
- `DiscountSnapshot`

## فیلدهای جدید مهم

برای `Coupon` و `DiscountBasket`:

- `campaign`
- `discount_type`
- `discount_value`
- `min_order_amount`
- `visibility`
- `funded_by`
- `salon_funding_percent`
- `platform_funding_percent`
- `stacking_policy`
- `staff_share_impact`
- `is_archived`
- `archived_at`
- `terms_text`
- `metadata`

برای `Coupon` علاوه بر موارد بالا:

- `max_order_amount`
- `total_usage_limit`
- `per_customer_usage_limit`
- `first_booking_only`
- `first_salon_booking_only`
- `eligible_payment_methods`

برای `Order`:

- `discount_rules_snapshot`

## سرویس‌ها

فایل جدید:

```text
apps/discounts/services.py
```

توابع اصلی:

- `DiscountEligibilityService.get_coupon`
- `DiscountEligibilityService.validate_coupon`
- `calculate_discount_amount`
- `build_coupon_snapshot`
- `build_basket_snapshot`
- `build_order_discount_snapshot`
- `persist_order_discount_records`
- `archive_discount_object`

## تغییرات checkout

- اعتبارسنجی کد تخفیف دیگر فقط فعال بودن و بازه زمانی نیست.
- محدودیت استفاده کل، محدودیت هر مشتری، اولین رزرو و حداقل/حداکثر مبلغ لحاظ می‌شود.
- تخفیف مبلغ ثابت هم پشتیبانی می‌شود.
- پس از ساخت سفارش، `DiscountSnapshot` و `DiscountRedemption` ثبت می‌شود.

## داشبورد سالن

- حذف کد تخفیف و سبد تخفیف به آرشیو تبدیل شد.
- لیست‌های داشبورد موارد آرشیوشده را نمایش نمی‌دهند.
- ظاهر فعلی داشبورد و Tailwind تغییر نکرد.

## Command جدید

```bash
python manage.py sync_discount_records --dry-run
python manage.py sync_discount_records
```

برای ساخت snapshot سبک برای سفارش‌های قدیمی دارای تخفیف.

## QA پیشنهادی

```bash
python manage.py migrate
python manage.py check
python manage.py sync_discount_records --dry-run
```

سناریوهای دستی:

1. ساخت کد تخفیف درصدی و اعمال در checkout.
2. ساخت کد تخفیف مبلغ ثابت از Django Admin و اعمال در checkout.
3. تست محدودیت استفاده هر مشتری.
4. تست آرشیو کد تخفیف از داشبورد سالن.
5. بررسی ثبت `DiscountRedemption` و `DiscountSnapshot` بعد از ثبت رزرو.
6. بررسی گزارش مالی موجود برای سازگاری با فیلدهای تخفیف قبلی.
