# Help Docs RAG v1.2 — Grounding hardening

This update does not add a migration.

Changes:
- groups up to two relevant chunks from the same article under one source number
- stronger no-inference / no-navigation-guess prompt
- preserves negative conditions and caveats
- removes invalid citation numbers and Markdown bold markers
- corrects exact UI guidance for regular shifts and coupon creation from staging

Apply the changed files, then refresh code-seeded docs:

```powershell
python manage.py seed_help_center --refresh-defaults
python manage.py rebuild_help_chunks
python manage.py audit_help_coverage
python manage.py test apps.help_center.tests
```

`--refresh-defaults` is intentional for this update because the corrected production
documents already exist and normal seed mode preserves published content.

Then restart:

```powershell
python manage.py runserver
```

Retest:
- چطور متخصص جدید اضافه کنم؟
- چرا متخصصی که اضافه کردم برای رزرو نمایش داده نمی‌شود؟
- چطور کد تخفیف بسازم؟
- چطور شیفت ثابت برای متخصص بگذارم؟
- متخصص رو اضافه کردم و براش شیفت گذاشتم ولی مشتری هنوز نمی‌تونه رزروش کنه، چی رو بررسی کنم؟
- بهترین مدل گوشی امسال چیه؟
