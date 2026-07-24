# Loomera Release Readiness Checklist

این چک‌لیست قبل از هر انتشار staging/production اجرا شود. هدف این مرحله جلوگیری از regression در رزرو، مالی، نقش‌ها، داشبوردها و UI فعلی Loomera است.

## 1. دستورات اجباری

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py infrastructure_preflight_check
python manage.py pre_beta_check
python manage.py release_readiness_check --skip-operational-dry-runs
```

برای اجرای کامل‌تر:

```bash
python manage.py release_readiness_check --run-tests
```

اگر محیط staging داده واقعی/نیمه‌واقعی دارد:

```bash
python manage.py release_readiness_check --run-tests
```

## 2. قواعد UI و Tailwind

- هیچ template عمومی نباید بدون دلیل بازنویسی شود.
- کلاس‌های فعلی Tailwind، spacing، radius، shadow، رنگ‌های برند و layout حفظ شوند.
- هر patch فرانت باید محدود، قابل rollback و مطابق ساختار فعلی باشد.
- اگر CSS global تغییر کرد، باید دلیل و اسکرین‌شات قبل/بعد ثبت شود.

## 3. قواعد migration

- نام index و constraint حداکثر ۳۰ کاراکتر باشد.
- migrationهای داده‌ای باید idempotent باشند.
- migration نباید داده رزرو، مالی، کاربر یا سالن را حذف کند.
- فیلدهای جدید روی داده‌های قدیمی default امن داشته باشند.

## 4. معیار قبولی انتشار

- `manage.py check` بدون خطا باشد.
- migration dry-run بدون تغییر جدید باشد.
- health check کامل سالم باشد: `/health/?full=1`.
- مسیرهای عمومی اصلی باز شوند: صفحه اصلی، سالن‌ها، جستجو، صفحه سالن، مجله.
- داشبورد مدیر سالن و آرایشگر بدون 500 باز شوند.
- پنل `/platform/` با superuser باز شود.
- هیچ خطای critical در log وجود نداشته باشد.
