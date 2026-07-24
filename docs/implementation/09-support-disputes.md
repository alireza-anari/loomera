# مرحله 9 — پشتیبانی، تیکت‌ها و مدیریت اختلاف‌ها

## هدف

ارتقای بخش پشتیبانی Loomera از فرم تماس ساده به سیستم کامل Support + Dispute Management، بدون حذف یا شکستن مدل قبلی `SupportTicket` و بدون بازنویسی UI فعلی.

## تغییرات اصلی

- ارتقای `SupportTicket` با دسته‌بندی، اولویت، SLA، تیم مسئول، ارجاع، ارتباط با سالن/آرایشگر/نوبت/پرداخت/محتوا.
- اضافه‌شدن `SupportTicketMessage` برای گفت‌وگوی چندمرحله‌ای.
- اضافه‌شدن `SupportAttachment` برای پیوست چندگانه.
- اضافه‌شدن `SupportEvent` برای تاریخچه تغییرات تیکت.
- اضافه‌شدن `DisputeCase` برای پرونده رسمی اختلاف.
- اضافه‌شدن `DisputeEvent` برای تاریخچه پرونده اختلاف.
- اتصال `mark_disputed` در چرخه نوبت به ساخت پرونده اختلاف.
- اضافه‌شدن صفحات کاربر برای لیست، جزئیات، پاسخ و بستن تیکت.
- ارتقای پنل ادمین Loomera برای صف تیکت‌ها، جزئیات تیکت و پرونده‌های اختلاف.
- اضافه‌شدن command برای sync تیکت‌های legacy به ساختار پیام/رویداد.

## دستورات اجرا

```bash
python manage.py migrate
python manage.py check
python manage.py sync_support_threads --dry-run
python manage.py sync_support_threads
```

## مسیرهای جدید کاربر

```text
/main/support/tickets/
/main/support/tickets/<id>/
/main/support/tickets/<id>/reply/
/main/support/tickets/<id>/close/
```

## مسیرهای جدید پنل ادمین

```text
/platform/support/
/platform/support/<id>/
/platform/support/<id>/status/
/platform/disputes/
/platform/disputes/<id>/
/platform/disputes/<id>/action/
```

## نکات سازگاری

- فیلدهای قدیمی `description`, `attachment`, `admin_reply` حذف نشده‌اند.
- تیکت‌های قدیمی با command `sync_support_threads` به ساختار پیام و event متصل می‌شوند.
- حذف فیزیکی انجام نشده و تغییرات status-based هستند.
- UI عمومی فقط patch حداقلی دریافت کرده است.

## QA پیشنهادی

1. ثبت یک تیکت جدید از صفحه پشتیبانی.
2. مشاهده تیکت در `/main/support/tickets/<id>/`.
3. ارسال پاسخ کاربر با/بدون پیوست.
4. پاسخ ادمین از `/platform/support/<id>/`.
5. تغییر وضعیت تیکت و بررسی audit log.
6. ساخت اختلاف از چرخه نوبت با action `mark_disputed`.
7. مشاهده پرونده در `/platform/disputes/`.
8. تغییر وضعیت پرونده اختلاف و بررسی `DisputeEvent`.
