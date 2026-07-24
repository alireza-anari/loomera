# مرحله ۷: سیستم اعلان‌ها و پیام‌ها

## هدف

در این مرحله یک لایه‌ی اعلان یکپارچه، نقش‌محور و رویدادمحور به پروژه اضافه شد. مدل‌های قبلی `CustomerNotification` و `AppointmentNotification` حذف یا بازنویسی نشدند تا سازگاری فعلی پروژه حفظ شود؛ اما از این مرحله، اعلان‌های جدید می‌توانند روی مدل‌های عمومی زیر ثبت شوند:

- `Notification`
- `NotificationRecipient`
- `NotificationDelivery`
- `NotificationDeliveryAttempt`
- `NotificationTemplate`
- `NotificationPreference`

## تصمیم سازگاری

برای کم‌ریسک بودن migration، ساختارهای قدیمی باقی ماندند و bridge سبک اضافه شد:

- هنگام ساخت `CustomerNotification`، یک اعلان یکپارچه متناظر هم ایجاد می‌شود.
- هنگام ساخت `AppointmentNotification` از مسیر lifecycle، یک اعلان یکپارچه متناظر هم ایجاد می‌شود.
- command `sync_legacy_notifications` برای sync دستی رکوردهای قدیمی اضافه شد.

## قابلیت‌های اضافه‌شده

- dedupe با `dedupe_key`
- گیرنده‌های چندنقشه برای مشتری، آرایشگر، مدیر، ادمین
- تنظیمات اعلان بر اساس user/role/category/event/channel
- کانال‌های dashboard/email/sms/whatsapp/system
- delivery queue برای email/sms
- delivery attempt log
- مرکز اعلان عمومی `/notifications/`
- APIهای summary، mark-read و mark-all-read
- command پردازش ارسال‌ها
- admin برای مدیریت اعلان‌ها، templateها، preferenceها و deliveryها

## دستورات اجرایی

```bash
python manage.py migrate
python manage.py check
python manage.py sync_legacy_notifications --dry-run
python manage.py sync_legacy_notifications
python manage.py process_notification_deliveries --limit 50
```

## نکات UI

- هیچ layout یا template فعلی بازنویسی نشد.
- یک صفحه جدید عمومی برای اعلان‌ها اضافه شد.
- dropdown داشبورد مدیر و آرایشگر، در صورت وجود اعلان یکپارچه، چند اعلان جدید را هم نشان می‌دهد.

## کارهای بعدی

- در مراحل بعدی، رویدادهای مالی، محتوا، پشتیبانی، ادمین و عضویت باید مستقیماً از `apps.notifications.services.create_notification` استفاده کنند.
- پس از پایدار شدن، مدل‌های legacy می‌توانند فقط برای سازگاری باقی بمانند یا به‌تدریج حذف شوند.
