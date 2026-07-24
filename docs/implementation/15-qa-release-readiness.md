# مرحله 15 - QA، تست، مانیتورینگ کیفیت و آماده‌سازی انتشار

## هدف

این مرحله ابزارها و اسناد لازم برای کنترل کیفیت Loomera را اضافه می‌کند، بدون اینکه UI، Tailwind یا layout فعلی تغییر کند.

## خروجی‌های مرحله

- `release_readiness_check` برای اجرای مجموعه‌ای از checkهای انتشار.
- تست سبک `apps.main.test_release_quality` برای smoke testهای release.
- چک‌لیست انتشار.
- چک‌لیست E2E دستی.
- ماتریس regression.

## دستور اصلی

```bash
python manage.py release_readiness_check --run-tests
```

برای اجرای سریع‌تر بدون dry-runهای عملیاتی:

```bash
python manage.py release_readiness_check --run-tests --skip-operational-dry-runs
```

## تست‌های اضافه‌شده

- resolve شدن routeهای عملیاتی اصلی.
- وجود feature flagهای حیاتی.
- کوتاه بودن نام index و constraintها برای جلوگیری از خطای دیتابیس.
- وجود اسناد QA.
- guard پایه برای media serving.

## نکته مهم

این مرحله جایگزین تست‌های end-to-end واقعی نیست. هدف آن ایجاد حداقل quality gate پایدار است. برای انتشار production باید تست‌های کامل‌تر booking، finance، permissions، support و notifications مرحله‌به‌مرحله گسترش پیدا کنند.
