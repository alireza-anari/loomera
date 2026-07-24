# Payment Live Smoke Test - Loomera

این چک‌لیست باید دقیقاً بعد از تنظیم env لایو و قبل از باز کردن سیستم برای کاربران واقعی اجرا شود.

> Terminology note: در این فایل برای روشن‌ماندن implementation بعضی واژه‌های فنی مثل `salon wallet` حفظ شده‌اند، اما scope محصولی Loomera broader از salon-only است.

---

## A) Wallet Charge

### A1) شارژ موفق کیف پول
- [ ] ورود به حساب مشتری
- [ ] رفتن به صفحه شارژ کیف پول
- [ ] انتخاب مبلغ کم
- [ ] انتقال به درگاه
- [ ] پرداخت موفق
- [ ] بازگشت صحیح به پروژه
- [ ] افزایش موجودی کیف پول
- [ ] ثبت Payment موفق
- [ ] عدم double-credit

### A2) لغو شارژ کیف پول
- [ ] شروع شارژ
- [ ] لغو در درگاه
- [ ] برگشت صحیح به پروژه
- [ ] عدم افزایش موجودی
- [ ] ثبت Payment cancelled/failed

### A3) verify تکراری
- [ ] بعد از پرداخت موفق، callback/result را دوباره باز کن
- [ ] موجودی کیف پول نباید دوباره زیاد شود

---

## B) Appointment Payment

### B1) رزرو آنلاین موفق
- [ ] انتخاب خدمت
- [ ] checkout
- [ ] پرداخت موفق
- [ ] ثبت Order با وضعیت paid
- [ ] ثبت Payment موفق
- [ ] ثبت settlement
- [ ] نمایش نوبت در appointments

### B2) لغو پرداخت رزرو
- [ ] شروع checkout
- [ ] لغو در درگاه
- [ ] برگشت به پروژه
- [ ] عدم ثبت رزرو paid
- [ ] وضعیت سفارش cancelled/clean

### B3) پرداخت ناموفق
- [ ] simulate fail / verify fail
- [ ] عدم ثبت paid
- [ ] result page قابل‌فهم، صریح و بدون ambiguity

---

## C) Wallet Payment for Booking

### C1) پرداخت رزرو با کیف پول
- [ ] موجودی کافی
- [ ] checkout با wallet
- [ ] کسر مبلغ از کیف پول
- [ ] ثبت Payment با provider=wallet
- [ ] ثبت order paid
- [ ] settlement sync

---

## D) Refund / Cancellation

### D1) لغو رزرو دیجیتال
- [ ] لغو رزرو آنلاین یا wallet
- [ ] refund طبق policy
- [ ] افزایش کیف پول مشتری
- [ ] به‌روزرسانی settlement
- [ ] به‌روزرسانی provider / salon wallet

### D2) لغو رزرو pay-in-salon
- [ ] لغو
- [ ] عدم refund خودکار

---

## E) First Visit Rule

### E1) اولین مراجعه
- [ ] برای اولین مراجعه به provider فقط digital payment مجاز باشد

### E2) مراجعه تکراری
- [ ] برای مراجعه تکراری pay-in-salon هم قابل انتخاب باشد

---

## F) Operations / Finance

### F1) درخواست برداشت مشتری
- [ ] ثبت درخواست
- [ ] کسر موجودی
- [ ] approve / reject
- [ ] restore صحیح در صورت reject/cancel

### F2) درخواست برداشت provider
- [ ] ثبت درخواست
- [ ] کسر available balance
- [ ] approve / reject
- [ ] restore صحیح در صورت reject/cancel

### F3) Reconciliation
- [ ] گزارش مالی provider
- [ ] گزارش مالی پلتفرم
- [ ] عدم mismatch غیرمنتظره

---

## G) Final Manual Review

- [ ] logها بدون نشت اطلاعات حساس
- [ ] callback URLها روی دامنه‌ی واقعی صحیح هستند
- [ ] PAYMENT_PUBLIC_BASE_URL درست کار می‌کند
- [ ] sandbox خاموش است
- [ ] payment provider واقعی فعال است
