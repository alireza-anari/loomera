# Stage 1 Manual Test Checklist — Limited Beta Core Stability

این چک‌لیست مخصوص مرحله 1 است؛ یعنی همان هسته‌ای که قبل از ورود به setup واقعی providerها باید قابل اتکا شود.

> Terminology note: برای خوانایی محصولی، این سند از واژه‌هایی مثل provider/detail page/specialist هم استفاده می‌کند. implementation فعلی هنوز در بخش‌هایی بر پایه‌ی `salon` و `stylist` است.

---

## 1) Auth / OTP / Password Reset

### 1.1 ثبت‌نام مشتری
- [x] ثبت‌نام با شماره‌ی جدید موفق است
- [x] کاربر غیرفعال ساخته می‌شود تا OTP تأیید شود
- [x] بعد از تأیید OTP، کاربر فعال و لاگین می‌شود
- [x] تلاش با شماره‌ی تکراری رفتار درست دارد
- [x] در حالت demo/sandbox هیچ dead-end وجود ندارد

### 1.2 ورود
- [x] کاربر فعال با رمز درست وارد می‌شود
- [x] کاربر غیرفعال وارد نمی‌شود
- [x] کاربر با رمز اشتباه پیام خطای واضح می‌گیرد

### 1.3 OTP
- [x] OTP درست تأیید می‌شود
- [x] OTP اشتباه، attempt را کم می‌کند
- [x] OTP منقضی‌شده رد می‌شود
- [x] resend قبل از cooldown رد می‌شود

### 1.4 فراموشی رمز
- [x] با شماره‌ی معتبر OTP بازیابی ارسال می‌شود
- [x] بعد از OTP معتبر، صفحه‌ی تغییر رمز باز می‌شود
- [x] بعد از تغییر رمز، ورود با رمز جدید ممکن است
- [x] session منقضی‌شده اجازه‌ی تغییر رمز نمی‌دهد

---

## 2) Search / Provider Detail / Service / Specialist / Time

### 2.1 جست‌وجوی provider
- [x] provider فعال در لیست دیده می‌شود
- [x] provider ناقص باعث dead-end در flow رزرو نمی‌شود
- [x] لینک صفحه‌ی provider سالم است

### 2.2 صفحه‌ی provider
- [x] خدمات فعال نمایش داده می‌شوند
- [x] متخصص‌های مرتبط نمایش داده می‌شوند
- [x] قیمت و مدت‌زمان خدمت قابل فهم است

### 2.3 انتخاب خدمت و متخصص
- [x] خدمت بدون متخصص معتبر قابل checkout نیست
- [x] متخصص نامرتبط برای خدمت انتخاب نمی‌شود
- [x] انتخاب any stylist/specialist در صورت وجود زمان آزاد به گزینه‌ی مناسب resolve می‌شود

### 2.4 انتخاب زمان
- [x] slot بیرون از schedule رد می‌شود
- [x] slot هم‌پوشان با time off رد می‌شود
- [x] slot هم‌پوشان با booking موجود رد می‌شود
- [x] انتخاب چند خدمت در یک روز باید ترتیبی باشد

---

## 3) Checkout / Payment / Booking Creation

### 3.1 checkout پایه
- [x] summary رزرو درست است
- [x] subtotal درست است
- [x] coupon نامعتبر dead-end ایجاد نمی‌کند

### 3.2 first visit rule
- [x] مراجعه‌ی اول فقط online یا wallet را می‌پذیرد
- [x] مراجعه‌ی تکراری pay-in-salon را هم می‌پذیرد

### 3.3 wallet payment
- [x] با موجودی کافی رزرو paid می‌شود
- [x] موجودی کیف پول کم می‌شود
- [x] Payment با provider=wallet ثبت می‌شود
- [x] WalletTransaction نوع PURCHASE ثبت می‌شود

### 3.4 online payment
- [x] Payment pending ساخته می‌شود
- [x] redirect به gateway/result درست است
- [x] verify موفق، order را paid می‌کند
- [x] verify fail/cancel رزرو را به وضعیت ناسازگار نمی‌برد

### 3.5 pay in salon
- [x] رزرو ساخته می‌شود
- [x] order is_finally=True می‌شود
- [x] وضعیت برای تأیید/پیگیری provider قابل فهم است

---

## 4) Cancellation / Refund / Reschedule / Rebook

### 4.1 cancellation
- [x] فقط owner رزرو می‌تواند لغو کند
- [x] رزرو خارج از پنجره‌ی لغو، cancel نمی‌شود
- [x] رزرو digital طبق policy به wallet refund می‌شود
- [x] رزرو pay-in-salon refund خودکار نمی‌گیرد
- [x] cancel تکراری double refund نمی‌دهد

### 4.2 reschedule
- [x] owner می‌تواند زمان جدید معتبر انتخاب کند
- [x] زمان هم‌پوشان رد می‌شود
- [x] order detailها با زمان جدید sync می‌شوند

### 4.3 rebook
- [x] rebook از رزرو قبلی payload معتبر می‌سازد
- [x] اگر متخصص قبلی unavailable باشد، fallback معقول دارد

---

## 5) Access Control

- [x] مشتری فقط نوبت‌ها و پروفایل خودش را می‌بیند
- [x] مدیر provider به customer panel هدایت نمی‌شود
- [x] متخصص به customer panel هدایت نمی‌شود
- [x] مشتری به dashboard manager/stylist دسترسی غیرمجاز ندارد
- [x] cancel/reschedule روی رزرو دیگران ممکن نیست

---

## 6) Logging / Observability

- [x] خطاهای checkout/payment در log ثبت می‌شوند
- [x] خطاها اطلاعات حساس نشت نمی‌دهند
- [x] Payment callback failure در log قابل ردیابی است
- [x] wallet / refund / settlement eventها قابل بررسی هستند

---

## ابزارهای پیشنهادی

### خودکار
- Django test runner
- coverage.py

### دستی
- Browser DevTools Network tab
- پنل دیتابیس یا Django admin
- بررسی log اپلیکیشن روی Liara یا محیط محلی

---

## دستورات پیشنهادی اجرا

```bash
export DJANGO_SETTINGS_MODULE=loomera.settings.test
export SECRET_KEY=test-secret-key
export SPATIALITE_LIBRARY_PATH=libspatialite.so.8
python manage.py test apps.accounts.test_stage1_auth_access apps.orders.test_stage1_booking_finance
```

برای پوشش بیشتر:

```bash
coverage run manage.py test apps.accounts.test_stage1_auth_access apps.orders.test_stage1_booking_finance
coverage report -m
```

> اگر در محیط local شما از PostGIS استفاده می‌شود، می‌توانید به‌جای `loomera.settings.test` یک test settings مبتنی بر همان DB خودتان بسازید.
