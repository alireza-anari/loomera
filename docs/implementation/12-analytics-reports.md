# مرحله 12: گزارش‌ها و Analytics مدیریتی

## هدف
اضافه شدن لایه مرکزی Analytics با رویکرد event + daily snapshot، بدون حذف گزارش‌های فعلی پروژه.

## پیاده‌سازی‌شده
- اپ جدید `apps.analytics`
- مدل‌های `AnalyticsEvent`, `DailyPlatformMetric`, `DailySalonMetric`, `DailyStaffMetric`, `DailyContentMetric`, `DailySearchMetric`, `ReportExportJob`
- سرویس‌های ساخت snapshot روزانه و خروجی CSV
- commandهای:

```bash
python manage.py build_daily_metrics --today
python manage.py build_daily_metrics --date 2026-05-07
python manage.py process_report_exports --limit 10
```

## پنل ادمین Loomera
مسیر جدید:

```text
/platform/analytics/
```

این صفحه snapshotهای پلتفرم، سالن، آرایشگر، محتوا، جستجو و خروجی‌های گزارش را نمایش می‌دهد.

## سازگاری
- گزارش‌های فعلی حذف نشدند.
- UI عمومی، داشبورد سالن، داشبورد آرایشگر و Tailwind فعلی تغییر نکردند.
- فقط یک صفحه جدید در پنل ادمین Loomera اضافه شد.

## بعد از اعمال مرحله
```bash
python manage.py migrate
python manage.py check
python manage.py build_daily_metrics --today
python manage.py process_report_exports --limit 10
```
