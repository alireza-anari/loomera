# Phase 9 Closure Patch

این بسته Closure رسمی فاز ۹ Loomera را اضافه می‌کند.

## اجرا

فایل `apply_phase9_closure.py` را در ریشه پروژه، کنار `manage.py` قرار بده و اجرا کن:

```powershell
python apply_phase9_closure.py
```

سپس تست‌ها:

```powershell
python -m py_compile `
  apps/main/phase9_closure.py `
  apps/main/test_phase9_closure_manifest.py `
  apps/main/release_readiness.py
```

```powershell
python manage.py test `
  apps.main.test_phase9_acceptance_registry `
  apps.main.test_phase9_closure_manifest `
  apps.main.test_regression_suite_registry `
  --keepdb
```

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
```

اجرای Closure نهایی:

```powershell
python manage.py local_beta_acceptance_check `
  --keepdb `
  --failfast
```

پس از اعمال Patch، فایل موقت `apply_phase9_closure.py` را می‌توانی حذف کنی.
