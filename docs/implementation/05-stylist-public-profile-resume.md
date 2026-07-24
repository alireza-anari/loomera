# مرحله ۵: پروفایل عمومی آرایشگر، رزومه و نمونه‌کارهای تأییدشده

## هدف

این مرحله پروفایل آرایشگر را در زمینه صفحه سالن قابل مشاهده می‌کند و پایه رزومه حرفه‌ای آرایشگر را بدون دست‌کاری نظرات و امتیازهای مشتریان فراهم می‌سازد.

## اصل‌های اجرایی

- UI فعلی بازنویسی نشده است.
- کارت تیم فقط به لینک پروفایل آرایشگر مجهز شده است.
- امتیازها، نظرات، تعداد نوبت‌های تکمیل‌شده و نمونه‌کارهای تأییدشده از داده‌های سیستمی خوانده می‌شوند و توسط آرایشگر قابل ویرایش نیستند.
- پروفایل آرایشگر داخل صفحه سالن فقط وقتی نمایش داده می‌شود که عضویت فعال و قابل نمایش باشد.
- ساختار رزومه ارسالی به سالن با snapshot ذخیره می‌شود تا تغییرات بعدی پروفایل، رزومه ارسال‌شده قبلی را تغییر ندهد.

## تغییرات اصلی

### مدل‌ها

- فیلدهای `resume_headline` و `resume_summary` به `Stylist` اضافه شد.
- مدل `ProfessionalResumeSubmission` به اپ `stylists` اضافه شد.

### سرویس‌ها

فایل جدید:

```text
apps/stylists/profile_services.py
```

توابع اصلی:

- `can_show_stylist_on_salon_profile`
- `get_stylist_services_for_salon`
- `get_public_work_samples`
- `get_stylist_reviews`
- `get_stylist_rating_summary`
- `get_completed_appointment_count`
- `build_resume_snapshot`
- `build_salon_stylist_profile_context`

### صفحات عمومی

مسیر جدید:

```text
/detail_salon/<salon_id>/stylists/<stylist_id>/
```

View:

```text
SalonStylistProfileView
```

Template:

```text
templates/pages/salon_stylist_profile.html
```

### کارت تیم سالن

`templates/components/team_member.html` فقط با patch حداقلی تغییر کرد تا اگر `stylist.salon_profile_url` موجود بود، کارت به پروفایل آرایشگر لینک شود.

### رزومه ارسالی

Endpoint آماده برای ارسال رزومه:

```text
POST /stylists/resume/submit/<salon_id>/
```

این endpoint برای فاز کاریابی آینده آماده است و فعلاً UI جدیدی به پروژه اضافه نمی‌کند.

## دستورات پس از اعمال

```bash
python manage.py migrate
python manage.py check
```

## QA پیشنهادی

1. صفحه جزئیات سالن را باز کنید و بررسی کنید کارت آرایشگرها همچنان ظاهر قبلی را دارد.
2. روی کارت آرایشگر کلیک کنید و صفحه پروفایل آرایشگر داخل سالن باز شود.
3. اگر آرایشگر `public_visibility=hidden` داشته باشد، پروفایل نمایش داده نشود.
4. اگر عضویت آرایشگر در سالن غیرفعال باشد، پروفایل نمایش داده نشود.
5. نمونه‌کارها فقط اگر `is_active=True`, `is_public=True` و `review_status` مناسب داشته باشند نمایش داده شوند.
6. نظرات نمایش داده‌شده فقط نظرات فعال همان آرایشگر در همان سالن باشند.
7. امتیازها و تعداد نوبت‌ها از داده‌های سیستمی خوانده شوند.
