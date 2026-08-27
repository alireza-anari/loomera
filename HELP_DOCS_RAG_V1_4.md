# Help Docs RAG v1.4 — Knowledge Base Expansion

This update is cumulative over v1.3 and adds no database migration.

## Coverage
- 75 curated production articles
- 34 contextual prompt mappings
- 51 retrieval benchmarks
- manager team invitation/request/end-collaboration workflows
- schedule approval and one-day editing workflows
- online booking / quick-link troubleshooting
- manager appointment lifecycle and pay-in-salon settlement
- manager finance, withdrawals, cost/share and profit docs
- stylist income, withdrawals and quick links
- customer cancellation and payment troubleshooting
- account/password/deletion documentation
- customer/manager/stylist Bale communication settings
- support ticket follow-up documentation

## Apply
```powershell
python manage.py seed_help_center --refresh-defaults
python manage.py rebuild_help_chunks
python manage.py audit_help_coverage
python manage.py test apps.help_center.tests
python manage.py check
```

No new migration is expected.

## High-value QA
```text
چطور برای متخصص دعوت همکاری بفرستم؟
چرا نمی‌تونم همکاری متخصص رو پایان بدم؟
درخواست مرخصی متخصص رو چطور تایید کنم؟
چطور لینک مستقیم رزرو بسازم؟
چرا برای لینک رزرو هیچ ساعت آزادی نمیاد؟
چه زمانی دریافت وجه حضوری رو ثبت کنم؟
چطور از موجودی مجموعه برداشت کنم؟
چرا متخصص سابق هنوز تو گزارش مالی دیده میشه؟
چطور درخواست برداشت متخصص رو تایید کنم؟
پول از حسابم کم شده ولی نتیجه پرداخت مشخص نیست چیکار کنم؟
مهلت پرداخت تموم شده و وقتم آزاد شده، چیکار کنم؟
چطور بله رو به لومرا وصل کنم؟
چطور تیکت قبلیم رو پیگیری کنم؟
```
Ask these from unrelated pages too. Current page should not override topic retrieval.
