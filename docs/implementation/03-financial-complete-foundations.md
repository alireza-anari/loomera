# مرحله 3: پیاده‌سازی پایه کامل مالی Loomera

این مرحله بدون تغییر در UI و بدون حذف ساختارهای مالی فعلی انجام شده است. هدف، اضافه‌کردن لایه رسمی و قابل توسعه مالی روی ساختار موجود است.

## تغییرات اصلی

- اضافه شدن `FinancialAccount` برای حساب‌های داخلی.
- اضافه شدن `LedgerEntry` برای دفتر مالی قابل audit.
- اضافه شدن سیاست‌های مالی:
  - `CommissionPolicy`
  - `BookingPaymentPolicy`
  - `CancellationPolicy`
- اضافه شدن زیرساخت providerهای پرداخت:
  - `PaymentProvider`
  - `SalonPaymentProviderConfig`
  - `PaymentTransaction`
- اضافه شدن `ExtraCharge` برای هزینه‌های اضافه با تأیید مشتری/مدیر.
- اضافه شدن `StaffEarning` برای ثبت مطالبه آرایشگر از سالن.
- اضافه شدن `StaffPayoutRequest` برای درخواست پرداخت سهم آرایشگر از سالن.
- اضافه شدن `FinancialAdjustment` برای اصلاحات مالی بدون حذف تراکنش.
- اضافه شدن `RefundRequest` و `CustomerCompensation` برای برگشت وجه و جبران مشتری.
- توسعه `OrderDetailFinancialSnapshot` با فیلدهای:
  - `extra_charges_amount`
  - `total_customer_paid`
  - `salon_customer_compensation`
  - `salon_refund_amount`
- اتصال finalize مالی موجود به:
  - ساخت/به‌روزرسانی `StaffEarning`
  - ثبت Ledger تراز برای snapshot نهایی

## سازگاری با ساختار فعلی

این مرحله موارد فعلی را حذف نکرده است:

- `Payment`
- `Wallet`
- `SalonWallet`
- `StylistWallet`
- `OrderDetailFinancialSnapshot`
- گزارش‌ها و viewهای مالی فعلی

لایه جدید به‌صورت سازگار اضافه شده تا بعداً بدون شکستن داشبوردهای فعلی، گزارش‌ها و فرآیندهای جدید مالی روی Ledger و policyها ساخته شوند.

## دستورات پیشنهادی بعد از اعمال

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py sync_financial_ledger --dry-run
python manage.py sync_financial_ledger
```

## نکات QA

- یک نوبت کامل را تا پایان خدمت جلو ببرید.
- مواد مصرفی واقعی را ثبت کنید.
- مالی نوبت را نهایی کنید.
- بررسی کنید `OrderDetailFinancialSnapshot` ساخته/نهایی شود.
- بررسی کنید `StaffEarning` برای آرایشگر ساخته شود.
- بررسی کنید `LedgerEntry` برای snapshot ساخته شود و سند تراز باشد.
- بررسی کنید walletهای قدیمی همچنان مثل قبل کار کنند.
- بررسی کنید هیچ template یا Tailwind تغییر نکرده باشد.
