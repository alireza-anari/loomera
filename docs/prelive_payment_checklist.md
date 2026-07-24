# Loomera Pre-Live Payment Checklist

> Terminology note: this checklist is written for Loomera's current scope across beauty, treatments, massage, and wellness. Internal implementation may still refer to `salon` in settings, reports, and finance records.

## 1) Environment
- [ ] DEBUG=False
- [ ] ALLOWED_HOSTS روی دامنه‌ی واقعی تنظیم شده
- [ ] CSRF_TRUSTED_ORIGINS روی https دامنه‌ی واقعی تنظیم شده
- [ ] PAYMENT_PUBLIC_BASE_URL روی دامنه‌ی واقعی https تنظیم شده
- [ ] PAYMENT_CALLBACK_URL به‌صورت relative path یا https معتبر تنظیم شده
- [ ] PAYMENT_MODE=live
- [ ] SANDBOX=False
- [ ] ZIBAL_MERCHANT روی مرچنت واقعی تنظیم شده

## 2) Security
- [ ] SECURE_SSL_REDIRECT=True
- [ ] SESSION_COOKIE_SECURE=True
- [ ] CSRF_COOKIE_SECURE=True
- [ ] Reverse proxy header درست ست شده
- [ ] Secrets روی سرور واقعی ست شده و داخل repo نیستند

## 3) Wallet Charge
- [ ] شروع شارژ کیف پول
- [ ] موفقیت پرداخت
- [ ] لغو پرداخت
- [ ] verify تکراری بدون double-credit
- [ ] callback بدون session شکننده

## 4) Appointment Payment
- [ ] شروع پرداخت رزرو
- [ ] موفقیت پرداخت
- [ ] fail / cancel
- [ ] result page قابل‌فهم و آرام است
- [ ] settlement snapshot ثبت می‌شود
- [ ] first-visit digital-only rule درست کار می‌کند

## 5) Refund / Wallet / Settlement
- [ ] refund after cancel
- [ ] customer wallet updated
- [ ] provider settlement updated
- [ ] provider wallet updated
- [ ] withdrawal request flow هنوز سالم است

## 6) Go-live smoke test
- [ ] یک پرداخت واقعی کم‌مبلغ برای شارژ کیف پول
- [ ] یک پرداخت واقعی کم‌مبلغ برای رزرو
- [ ] بررسی لاگ‌ها بعد از تست
- [ ] بررسی callback URL و result URL روی دامنه‌ی واقعی
