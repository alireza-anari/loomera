# Loomera Help Center — Phase 2

این پکیج فاز اول را ارتقا می‌دهد و CMS دیتابیسی، Admin، ذخیره امن گفتگو،
feedback، اسناد حقوقی نسخه‌بندی‌شده و handoff به SupportTicket فعلی پروژه را اضافه می‌کند.

## 1) App را به INSTALLED_APPS اضافه کن

در `loomera/settings/base.py`:

```python
"apps.main.apps.MainConfig",
"apps.help_center.apps.HelpCenterConfig",
"apps.accounts.apps.AccountsConfig",
```

## 2) تنظیمات Help/AI را به base.py اضافه کن

```python
HELP_AI_ENABLED = env.bool("HELP_AI_ENABLED", default=True)
GROQ_API_KEY = env("GROQ_API_KEY", default="").strip()
HELP_AI_MODEL = env("HELP_AI_MODEL", default="qwen/qwen3-32b").strip()
HELP_AI_TIMEOUT_SECONDS = env.int("HELP_AI_TIMEOUT_SECONDS", default=12)

HELP_CHAT_GUEST_LIMIT = env.int("HELP_CHAT_GUEST_LIMIT", default=10)
HELP_CHAT_USER_LIMIT = env.int("HELP_CHAT_USER_LIMIT", default=30)
HELP_CHAT_RATE_WINDOW_SECONDS = env.int("HELP_CHAT_RATE_WINDOW_SECONDS", default=3600)

HELP_SUPPORT_HANDOFF_LIMIT = env.int("HELP_SUPPORT_HANDOFF_LIMIT", default=3)
HELP_SUPPORT_HANDOFF_WINDOW_SECONDS = env.int(
    "HELP_SUPPORT_HANDOFF_WINDOW_SECONDS", default=3600
)
HELP_CONVERSATION_RETENTION_DAYS = env.int(
    "HELP_CONVERSATION_RETENTION_DAYS", default=30
)
```

## 3) Route فاز اول باید وجود داشته باشد

در `loomera/urls.py`:

```python
path("help/", include("apps.help_center.urls", namespace="help_center")),
```

## 4) Migration و Seed

```powershell
python manage.py migrate help_center
python manage.py seed_help_center
python manage.py check
```

`seed_help_center` قابل تکرار است و داده‌های اولیه را update می‌کند.

## 5) Admin

بعد از seed از Django Admin می‌توانی این موارد را مدیریت کنی:
- دسته‌های راهنما
- مقالات راهنما
- زمینه‌های صفحات و Regex مسیر
- اسناد حقوقی
- گفتگوهای دستیار
- بازخوردها

از این مرحله به بعد متن آموزش از Admin قابل تغییر است؛ JavaScript فقط UI را کنترل می‌کند.

## 6) اسناد حقوقی

Seed سه رکورد legacy ایجاد می‌کند:
- privacy
- terms
- messaging-privacy

تا وقتی content خالی باشد، صفحه جدید به URL قدیمی redirect می‌شود.
برای انتقال واقعی، نسخه جدید با status=published و is_current=true بساز.

## 7) Handoff

کاربر لاگین‌شده می‌تواند گفتگوی redact‌شده را مستقیم به SupportTicket فعلی پروژه منتقل کند.
مهمان یا کاربری که email ندارد به فرم پشتیبانی هدایت می‌شود.

## 8) Retention

```powershell
python manage.py purge_help_conversations
```

یا:

```powershell
python manage.py purge_help_conversations --days 14
```
