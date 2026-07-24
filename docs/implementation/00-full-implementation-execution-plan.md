# Loomera Full Implementation Execution Plan

این فایل نقطه شروع فاز پیاده‌سازی کامل Loomera است. هدف این فاز پیاده‌سازی کامل اسناد توسعه است، اما تغییرات باید مرحله‌ای، migration-safe و بدون تخریب UI فعلی انجام شوند.

## قوانین ثابت توسعه

1. UI فعلی، layoutها، پالت رنگی، برندینگ، spacing، radius، shadow و کلاس‌های Tailwind موجود حفظ شوند.
2. هیچ template عمومی بدون نیاز واقعی بازنویسی نشود؛ فقط patch حداقلی انجام شود.
3. global CSS فقط با دلیل روشن تغییر کند.
4. تغییرات دیتابیس باید backward-compatible و migration-safe باشند.
5. داده‌های فعلی پروژه نباید حذف یا invalid شوند.
6. عملیات حساس باید audit log داشته باشد.
7. قابلیت‌های مالی/پرداختی پرریسک باید پشت feature flag بمانند.
8. هر بخش باید با service layer پیاده شود، نه منطق پراکنده داخل view/template.
9. بعد از هر بخش باید `python manage.py check` و سناریوهای دستی مرتبط اجرا شود.
10. هر خروجی باید فایل‌های تغییرکرده، migrationها و ریسک‌ها را گزارش کند.

## ترتیب اجرای کامل

1. امنیت، feature flags، audit، زیرساخت پایه و health check
2. نقش‌ها، SalonMembership، دسترسی‌ها و احراز سالن
3. چرخه کامل نوبت، تأخیر، no-show، بافر و overrun
4. مالی کامل، Ledger، Snapshot، مواد، سهم آرایشگر، بیعانه، withdrawal و providerها
5. داشبورد آرایشگر کامل
6. پروفایل عمومی آرایشگر، رزومه و کاریابی آینده
7. مقالات، استوری، نمونه‌کار و کنترل محتوا
8. اعلان‌ها و پیام‌ها
9. پنل ادمین Loomera
10. پشتیبانی، تیکت و اختلاف‌ها
11. جستجو، AvailabilityService، RankingService و کشف سالن‌ها
12. تخفیف‌ها، کمپین‌ها و پیشنهادهای ویژه
13. Analytics و گزارش‌های مدیریتی
14. SEO، صفحات عمومی و رشد ارگانیک
15. زیرساخت پیشرفته، background jobs، cache و performance
16. تست، QA، مانیتورینگ و آماده‌سازی انتشار

## وضعیت مرحله 0/1

در اولین تغییر امن، موارد زیر اضافه شدند:

- feature flagهای مرکزی در settings
- PlatformSetting برای تنظیمات عملیاتی کم‌ریسک
- AdminAuditLog و SecurityAuditLog پایه
- UserConsent برای ثبت پذیرش قوانین/حریم خصوصی
- AccountDeletionRequest و حذف حساب مبتنی بر anonymization به جای hard delete
- HealthCheckView در `/health/`
- اصلاح سرو media تا فقط در DEBUG یا SERVE_MEDIA_INSECURELY فعال باشد
- rate limit سبک برای ثبت تیکت پشتیبانی
- command `pre_beta_check`

## نکته اجرا

در محیط فعلی این sandbox، وابستگی‌های Django نصب نیستند؛ بنابراین validation با `py_compile` انجام شده و اجرای `manage.py check` باید در محیط پروژه انجام شود.
