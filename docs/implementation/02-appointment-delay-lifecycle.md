# مرحله ۲: چرخه نوبت، تأخیر، no-show، بافر و service_overrun

## هدف

این مرحله هسته عملیاتی رزرو را کامل‌تر می‌کند تا آرایشگر بتواند وضعیت نوبت را مرحله‌به‌مرحله اجرا کند و سیستم بدون جابه‌جا کردن نوبت‌های بعدی، تأخیر مشتری، عدم حضور، طولانی‌شدن خدمت و تاریخچه رویدادها را ثبت کند.

## اصول اجرا

- UI و Tailwind فعلی بازنویسی نشده است.
- ساختار قدیمی `Order`, `OrderDetail` و اکشن‌های فعلی حفظ شده‌اند.
- قابلیت‌های جدید به صورت افزایشی و backward-compatible اضافه شده‌اند.
- بافر خدمت در زمان اشغال تقویم لحاظ می‌شود، اما زمان پایان خدمت همچنان پایان واقعی خدمت است.
- ثبت no-show به صورت `pending review` انجام می‌شود و تایید نهایی جداست.

## تغییرات مدل‌ها

### Services

- `buffer_minutes`: بافر بعد از پایان خدمت برای آماده‌سازی و جلوگیری از تداخل نوبت بعدی.

### OrderDetail

- `scheduled_duration_minutes`
- `buffer_minutes`
- `occupied_until`
- `client_late_recorded_at`
- `client_late_minutes`
- `no_show_pending_at`
- `no_show_dispute_until`
- `no_show_confirmed_at`
- `no_show_confirmed_by`
- `expected_service_completed_at`
- `service_overrun_recorded_at`
- `service_overrun_minutes`
- `service_overrun_reason`
- `disputed_at`
- `operational_note`

وضعیت‌های جدید lifecycle:

- `client_late`
- `no_show_pending_review`
- `no_show_confirmed`
- `service_overrun`
- `disputed`

### DelayPolicy

مدل جدید برای قوانین تأخیر سالن:

- `grace_period_minutes`
- `no_show_after_minutes`
- `no_show_dispute_window_hours`
- `default_service_buffer_minutes`
- `customer_facing_text`

### AppointmentEvent

مدل جدید برای ثبت تاریخچه رویدادهای نوبت:

- ثبت رزرو
- تأیید/رد آرایشگر
- تأخیر مشتری
- رسیدن مشتری
- شروع خدمت
- طولانی‌شدن خدمت
- پایان خدمت
- no-show pending/confirmed
- disputed

## سرویس‌های جدید

فایل:

```text
apps/orders/appointment_lifecycle.py
```

توابع اصلی:

- `confirm_order_detail`
- `reject_order_detail`
- `mark_client_late`
- `mark_customer_arrived`
- `start_service`
- `mark_service_overrun`
- `complete_service`
- `mark_no_show_pending`
- `confirm_no_show`
- `mark_disputed`

## تغییرات Availability

در `apps/orders/booking_utils.py`:

- مدت خدمت و بافر جدا محاسبه می‌شوند.
- اسلات قابل نمایش به مشتری پایان خدمت را نشان می‌دهد.
- برای جلوگیری از تداخل، `occupied_until` یا مدت خدمت + بافر بررسی می‌شود.
- رزروهای موجود با `occupied_until` برای overlap بررسی می‌شوند.

## تغییرات داشبورد آرایشگر

بدون تغییر قالب، اکشن‌های جدید به لیست عملیاتی اضافه شده‌اند:

- ثبت تأخیر مشتری
- ثبت عدم حضور برای بررسی
- تأیید نهایی عدم حضور
- ارسال برای بررسی اختلاف
- ثبت طولانی‌شدن خدمت

## Background Command

Command جدید:

```bash
python manage.py confirm_no_show_after_window
```

گزینه‌ها:

```bash
python manage.py confirm_no_show_after_window --dry-run
python manage.py confirm_no_show_after_window --limit 200
```

## فایل‌های تغییرکرده

- `apps/services/models.py`
- `apps/services/forms.py`
- `apps/services/admin.py`
- `apps/services/migrations/0010_services_buffer_minutes.py`
- `apps/orders/models.py`
- `apps/orders/booking_utils.py`
- `apps/orders/appointment_lifecycle.py`
- `apps/orders/signals.py`
- `apps/orders/apps.py`
- `apps/orders/admin.py`
- `apps/orders/migrations/0012_delay_policy_appointment_events.py`
- `apps/orders/management/commands/confirm_no_show_after_window.py`
- `apps/dashboards/views.py`

## دستورات اجرا

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py confirm_no_show_after_window --dry-run
```

## سناریوهای QA دستی

1. ساخت خدمت با بافر و بررسی ذخیره شدن `buffer_minutes`.
2. ساخت رزرو و بررسی `scheduled_duration_minutes`, `buffer_minutes`, `occupied_until`.
3. بررسی اینکه نوبت بعدی داخل بازه بافر قابل رزرو نباشد.
4. تأیید نوبت توسط آرایشگر.
5. ثبت تأخیر مشتری.
6. ثبت رسیدن مشتری بعد از تأخیر.
7. شروع خدمت و بررسی `expected_service_completed_at`.
8. ثبت طولانی‌شدن خدمت.
9. پایان خدمت و ثبت خودکار overrun در صورت عبور از زمان مورد انتظار.
10. ثبت no-show بعد از زمان مجاز.
11. تأیید نهایی no-show بعد از مهلت بررسی.
12. بررسی تایم‌لاین رویدادها در صفحه جزئیات نوبت آرایشگر.

## نکته‌های مهم

- اجرای خدمت با پذیرش تأخیر برای جابه‌جایی نوبت‌های بعدی اضافه نشده است.
- no-show مستقیم final نمی‌شود و ابتدا در وضعیت بررسی قرار می‌گیرد.
- اگر مشتری برسد، ثبت no-show مجاز نیست.
- اگر خدمت شروع شده باشد، ثبت no-show مجاز نیست.
