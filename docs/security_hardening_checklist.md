# Loomera Production Security Hardening Checklist

## 1) Core settings
- [ ] DEBUG=False
- [ ] ALLOWED_HOSTS روی دامنه واقعی تنظیم شده
- [ ] CSRF_TRUSTED_ORIGINS روی https دامنه واقعی تنظیم شده
- [ ] SECRET_KEY فقط روی سرور واقعی ست شده و داخل repo نیست

## 2) HTTPS / Proxy
- [ ] SECURE_PROXY_SSL_HEADER درست تنظیم شده
- [ ] USE_X_FORWARDED_HOST=True
- [ ] SECURE_SSL_REDIRECT=True
- [ ] دامنه اصلی با HTTPS درست بالا می‌آید

## 3) Cookies
- [ ] SESSION_COOKIE_SECURE=True
- [ ] CSRF_COOKIE_SECURE=True
- [ ] SESSION_COOKIE_HTTPONLY=True
- [ ] CSRF_COOKIE_HTTPONLY طبق نیاز پروژه بررسی شده
- [ ] SESSION_COOKIE_SAMESITE=Lax
- [ ] CSRF_COOKIE_SAMESITE=Lax

## 4) Browser hardening
- [ ] SECURE_CONTENT_TYPE_NOSNIFF=True
- [ ] X_FRAME_OPTIONS=DENY
- [ ] SECURE_REFERRER_POLICY تنظیم شده
- [ ] SECURE_CROSS_ORIGIN_OPENER_POLICY تنظیم شده

## 5) HSTS
- [ ] قبل از فعال‌سازی HSTS، دامنه با HTTPS کامل تست شده
- [ ] SECURE_HSTS_SECONDS فقط بعد از تست روشن می‌شود
- [ ] HSTS includeSubdomains/preload فقط در صورت آمادگی کامل فعال می‌شود

## 6) Static / Media
- [ ] media در production با Django serve نمی‌شود
- [ ] media با Nginx/Apache یا storage مناسب سرو می‌شود
- [ ] static strategy نهایی مشخص شده

## 7) Secrets / third-party keys
- [ ] SMS provider keys rotate شده‌اند
- [ ] payment keys rotate شده‌اند
- [ ] map provider key rotate شده است
- [ ] هیچ secret داخل repo یا artifact deploy نیست

## 8) Logging
- [ ] print/debug logهای توسعه‌ای حذف شده‌اند
- [ ] logها داده حساس نشت نمی‌دهند
- [ ] خطاهای payment / OTP / callback قابل ردیابی هستند

## 9) Final checks
- [ ] payment_preflight_check پاس می‌شود
- [ ] smoke test پرداخت انجام شده
- [ ] مسیرهای callback و result روی دامنه واقعی تست شده‌اند