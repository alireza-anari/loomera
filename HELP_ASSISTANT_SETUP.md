# Loomera Help Assistant MVP

این نسخه بدون migration و بدون dependency جدید Python اجرا می‌شود.

## 1) فایل‌ها را کپی کن

کل پوشه‌های `apps/help_center/`، `templates/help_center/`، فایل
`templates/dashboards/partials/dashboard_help_fab.html` و staticهای جدید را
در مسیرهای متناظر پروژه قرار بده.

## 2) URL اصلی را اضافه کن

در `loomera/urls.py` داخل `urlpatterns` این خط را اضافه کن:

```python
path("help/", include("apps.help_center.urls", namespace="help_center")),
```

`include` از قبل در فایل پروژه import شده است.

## 3) Groq API

برای حالت AI در `.env` لوکال:

```env
HELP_AI_ENABLED=true
GROQ_API_KEY=YOUR_KEY
HELP_AI_MODEL=qwen/qwen3-32b
HELP_AI_TIMEOUT_SECONDS=12

HELP_CHAT_GUEST_LIMIT=10
HELP_CHAT_USER_LIMIT=30
HELP_CHAT_RATE_WINDOW_SECONDS=3600
```

اگر `GROQ_API_KEY` تنظیم نشده باشد، چت از پاسخ محلی مستندات استفاده می‌کند و
feature از کار نمی‌افتد.

## 4) تست

```powershell
python -m py_compile apps/help_center/knowledge.py `
                         apps/help_center/ai.py `
                         apps/help_center/services.py `
                         apps/help_center/views.py `
                         apps/help_center/urls.py

python manage.py check
python manage.py runserver
```

صفحات:
- `/help/`
- `/help/search/?q=متخصص`

و FAB را روی چند صفحه تست کن.

## 5) Liara staging

متغیرهای بالا را در Environment Variables اپ staging وارد کن.
API key را commit نکن.

## فاز بعد

پس از تأیید UI/API:
- مدل‌های HelpCategory / HelpArticle / HelpFeedback / HelpConversation
- Django Admin به‌عنوان CMS
- انتقال registry به database
- اسناد Legal versioned
- feedback 👍/👎
- ساخت تیکت همراه با context چت
