# مرحله 8 — پنل ادمین عملیاتی Loomera

## هدف

این مرحله یک پنل عملیاتی جدا از Django Admin اضافه می‌کند تا تیم Loomera بتواند سالن‌ها، احراز، کاربران، نوبت‌های حساس، محتوا، مالی، اعلان‌ها، پشتیبانی، تنظیمات و audit log را مدیریت کند؛ بدون اینکه داشبورد سالن/آرایشگر یا UI عمومی بازنویسی شود.

## تصمیم‌های سازگاری

- Django Admin حذف یا جایگزین نشد.
- مسیر جدید پنل عملیاتی `/platform/` است.
- مدل‌های audit و تنظیمات قبلی حفظ شدند.
- نقش‌های داخلی ادمین روی مدل `AdminRoleAssignment` اضافه شدند.
- تعلیق‌ها با `SuspensionRecord` ثبت می‌شوند و حذف فیزیکی انجام نمی‌شود.
- تمام عملیات حساس از طریق `AdminAuditLog` ثبت می‌شوند.

## مدل‌های اضافه‌شده

در `apps.main.models`:

- `AdminRoleAssignment`
- `SuspensionRecord`

## اپ اضافه‌شده

`apps.platform_admin`

شامل:

- `permissions.py`
- `audit.py`
- `forms.py`
- `views.py`
- `urls.py`

## مسیرهای اصلی

- `/platform/` داشبورد اصلی
- `/platform/salons/` مدیریت سالن‌ها
- `/platform/users/` مدیریت کاربران
- `/platform/appointments/` صف نوبت‌ها و اختلاف‌ها
- `/platform/content/reports/` گزارش‌های محتوا
- `/platform/finance/` نمای مالی
- `/platform/notifications/` مانیتورینگ اعلان‌ها
- `/platform/support/` پشتیبانی
- `/platform/settings/` تنظیمات پلتفرم
- `/platform/audit/` لاگ عملیات حساس

## نقش‌های داخلی

- Super Admin
- Support Admin
- Finance Admin
- Content Moderator
- Verification Admin
- Read-only Admin

کاربر superuser همیشه دسترسی کامل دارد. کاربرهای legacy با `is_admin=True` تا زمانی که نقش‌های دقیق تعریف شوند دسترسی broad دارند تا پروژه قبلی نشکند.

## ماژول‌های پیاده‌سازی‌شده

### داشبورد اصلی

نمایش KPIهای عملیاتی:

- سالن‌ها
- سالن‌های در انتظار احراز
- کاربران
- نوبت‌های امروز
- no-show/disputed
- گزارش‌های محتوا
- تیکت‌های باز
- اعلان‌های ناموفق
- پرچم‌های feature flag

### مدیریت سالن‌ها

- جستجو و فیلتر سالن
- مشاهده جزئیات سالن
- مشاهده عضویت‌های آرایشگران
- مشاهده نوبت‌های اخیر
- تغییر وضعیت احراز سالن با audit log

### مدیریت کاربران

- فیلتر نقش مشتری/آرایشگر/مدیر/ادمین
- مشاهده عضویت‌های آرایشگر
- مشاهده سالن‌های مدیریت‌شده
- ثبت تعلیق کاربر با `SuspensionRecord`
- ثبت audit log برای تعلیق

### محتوا و moderation

- مشاهده گزارش‌های محتوا
- پذیرش/رد گزارش
- تعلیق محتوا
- حذف توسط Loomera با status-based removal
- ثبت audit log

### مالی

- نمای پرداخت‌ها
- تراکنش‌های payment provider
- درخواست‌های پرداخت آرایشگر
- اصلاحات مالی
- refundها
- compensationها
- Ledger total

### اعلان‌ها

- نمایش deliveryها
- فیلتر status
- مشاهده اعلان‌های ناموفق

### پشتیبانی

- نمایش تیکت‌ها
- تغییر وضعیت
- ثبت پاسخ ادمین
- audit log تغییر وضعیت/پاسخ

### تنظیمات

- نمایش feature flagهای محیط
- مشاهده و ویرایش `PlatformSetting`
- audit log ویرایش تنظیم

### Audit

- مشاهده `AdminAuditLog`
- فیلتر بر اساس action

## دستورات اجرا

```bash
python manage.py migrate
python manage.py check
```

## نکات QA

1. با superuser وارد `/platform/` شوید.
2. فهرست سالن‌ها باز شود.
3. وضعیت احراز یک سالن را تغییر دهید و لاگ را در `/platform/audit/` ببینید.
4. یک کاربر را تعلیق کنید و `SuspensionRecord` و audit log را بررسی کنید.
5. گزارش محتوا را بررسی و تعلیق کنید.
6. در بخش مالی، لیست پرداخت‌ها/درخواست‌ها بدون خطا باز شود.
7. navigation داخلی پنل در موبایل و دسکتاپ قابل استفاده باشد.

## موارد عمدی که در این مرحله انجام نشد

- workflow کامل refund/withdrawal در UI عملیاتی
- نقش‌بندی خیلی ریز سطح field
- نمودارهای پیشرفته ادمین
- dashboardهای analytics عمیق

این موارد در مراحل Analytics، پشتیبانی/اختلاف کامل و مالی پیشرفته تکمیل می‌شوند.
