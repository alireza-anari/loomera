# مرحله 14 — زیرساخت، Performance، Cache، Background Jobs و Monitoring

این مرحله لایه‌ی زیرساختی پروژه Loomera را تکمیل می‌کند، بدون تغییر در UI عمومی یا داشبوردهای فعلی.

## اهداف

- آماده‌سازی Redis/cache برای production و rate limitها
- آماده‌سازی Celery به‌صورت اختیاری، بدون اجبار در محیط local
- ثبت اجرای jobهای عملیاتی در دیتابیس
- ساخت command تجمیعی برای cron-safe scheduled tasks
- افزودن health check کامل‌تر
- افزودن زیرساخت پردازش تصاویر و thumbnail/webp
- افزودن cleanup command برای داده‌های عملیاتی
- افزودن صفحه مانیتورینگ زیرساخت در پنل ادمین Loomera
- آماده‌سازی Sentry و WhiteNoise به‌صورت اختیاری

## تصمیم‌های سازگاری

- برای جلوگیری از پیچیدگی ناگهانی، Celery به‌صورت optional اضافه شده است.
- در local و تا زمانی که `LOOMERA_ENABLE_CELERY=False` باشد، همان cron + management commands کافی است.
- UI فعلی پروژه بازنویسی نشده است.
- سرو media در production همچنان باید توسط Nginx/CDN/Object Storage انجام شود.

## مدل‌های جدید

### OperationalJobRun
ثبت اجرای jobهای زیرساختی و commandهای دوره‌ای.

### MediaProcessingJob
ثبت پردازش تصاویر، thumbnail، فایل optimized و وضعیت پردازش.

## commandهای جدید

```bash
python manage.py run_scheduled_tasks
python manage.py run_scheduled_tasks --dry-run
python manage.py process_media_jobs --limit 25
python manage.py cleanup_operational_data --dry-run
python manage.py infrastructure_preflight_check
```

## تنظیمات جدید

```env
LOOMERA_ENVIRONMENT=local
LOOMERA_ENABLE_CELERY=False
CELERY_BROKER_URL=redis://127.0.0.1:6379/1
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
SENTRY_DSN=
LOOMERA_MAX_UPLOAD_SIZE_MB=8
LOOMERA_IMAGE_MAX_WIDTH=1920
LOOMERA_IMAGE_THUMBNAIL_WIDTH=640
LOOMERA_MEDIA_PROCESSING_ENABLED=True
```

## مسیرهای جدید

```text
/platform/infrastructure/
/health/?full=1
```

## مراحل اجرا بعد از دریافت فایل

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py infrastructure_preflight_check
python manage.py run_scheduled_tasks --dry-run
python manage.py process_media_jobs --limit 10
```

## مسیر پیشنهادی deploy

### قبل از Celery

- Redis برای cache
- cron برای `run_scheduled_tasks`
- cron برای `cleanup_operational_data`
- cron برای `process_media_jobs`
- Sentry برای خطاها
- Nginx برای static/media

### بعد از آماده شدن production

- Celery worker
- Celery Beat
- Sentry فعال
- Object Storage/CDN برای media
- job dashboard یا Flower

## QA دستی

- `/health/` باید status ok بدهد.
- `/health/?full=1` باید runtime غیرحساس را نشان دهد.
- `/platform/infrastructure/` باید برای superuser باز شود.
- `run_scheduled_tasks --dry-run` نباید خطا بدهد.
- `infrastructure_preflight_check` در local warning می‌دهد ولی نباید خطای بحرانی داشته باشد مگر cache/db مشکل داشته باشد.
