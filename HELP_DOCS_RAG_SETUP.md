# Loomera Help Center — Docs-first RAG refactor

این بسته prototype فازهای 1 تا 3 را از «راهنمای صفحه» به معماری مستندات‌محور تبدیل می‌کند.

## نتیجه معماری

- `/help/` هاب مستندات و منبع حقیقت است.
- دکمه شناور فقط «دستیار لومرا» است.
- صفحه فعلی فقط برای سؤال‌های صریح مثل «این صفحه چیه؟» اثر دارد.
- سؤال عادی در کل مستندات مجاز جستجو می‌شود.
- مدل AI فقط chunkهای بازیابی‌شده را دریافت می‌کند.
- پاسخ AI باید از `[1]`, `[2]`... استفاده کند و UI منابع را به مقاله اصلی لینک می‌کند.
- اگر سند مرتبط پیدا نشود، مدل اصلاً فراخوانی نمی‌شود.
- اگر provider قطع باشد، پاسخ محلی صریحاً می‌گوید اتصال AI در دسترس نیست.

## فایل‌های قدیمی که بعد از کپی بسته باید حذف شوند

```powershell
git rm static/js/components/contextual_help_hub.js
git rm apps/help_center/knowledge.py
git rm apps/help_center/page_catalog.py
```

مهاجرت‌های قبلی را حذف نکن.

## تنظیم settings

فایل `HELP_DOCS_RAG_SETTINGS.patch` را در ریشه repo قرار بده و اجرا کن:

```powershell
git apply HELP_DOCS_RAG_SETTINGS.patch
```

یا همان تغییرات را دستی در `loomera/settings/base.py` اعمال کن.

### نمونه OpenRouter برای تست

```env
HELP_AI_ENABLED=true
HELP_AI_PROVIDER=openrouter
OPENROUTER_API_KEY=YOUR_KEY
HELP_AI_MODEL=openrouter/free
HELP_AI_TIMEOUT_SECONDS=15
HELP_AI_MAX_COMPLETION_TOKENS=750
```

`openrouter/free` برای تست رایگان مناسب است، ولی مدل پشت router می‌تواند بین درخواست‌ها عوض شود؛ برای production بعداً یک مدل ثابت انتخاب کن.

### نمونه Groq

```env
HELP_AI_ENABLED=true
HELP_AI_PROVIDER=groq
GROQ_API_KEY=YOUR_KEY
HELP_AI_MODEL=YOUR_CURRENT_ALLOWED_MODEL
HELP_AI_TIMEOUT_SECONDS=15
HELP_AI_MAX_COMPLETION_TOKENS=750
```

نام مدل عمداً در کد hard-code نشده است.

## ارتقا از prototype فعلی روی staging

ابتدا migration را کنترل کن:

```powershell
python manage.py makemigrations --check --dry-run help_center
```

انتظار: `No changes detected`.

سپس:

```powershell
python manage.py migrate help_center
python manage.py reset_help_center_prototype --confirm
python manage.py seed_help_center
python manage.py rebuild_help_chunks
python manage.py check
python manage.py audit_help_coverage
```

`reset_help_center_prototype` فقط برای گذار از prototype فعلی ساخته شده است. این command:

- contextهای قدیمی را حذف می‌کند؛
- chunkهای قدیمی را حذف می‌کند؛
- مقاله‌ها و دسته‌های prototype را unpublished می‌کند؛
- conversation/message/feedback/legal docs را نگه می‌دارد.

بعد از اینکه تیم شروع به ویرایش محتوای واقعی در Admin کرد، این reset را دوباره اجرا نکن مگر عمداً بخواهی محتوای مستندات را reset کنی.

## تست provider

بعد از تنظیم env:

```powershell
python manage.py test_help_ai
```

این command provider، مدل و خطای HTTP واقعی را نشان می‌دهد.

## محتوای اولیه دقیق

`apps/help_center/data/production_docs.json` در این نسخه 29 مقاله بازبینی‌شده دارد. این‌ها از روی behavior فعلی staging نوشته شده‌اند، از جمله:

- افزودن و مدیریت متخصص
- علت قابل رزرو نبودن متخصص
- خدمات و علت نمایش‌ندادن در رزرو
- شیفت منظم و عدم حضور
- رزرو دستی مدیر
- برنامه کاری و مرخصی متخصص
- جریان رزرو و تغییر زمان مشتری
- از دست رفتن slot هنگام checkout
- کیف پول و محدودیت beta
- شارژ و تراکنش کیف پول
- آدرس‌های مشتری
- کد تخفیف، پیشنهاد خدمات و کمپین
- پشتیبانی و نحوه استفاده دستیار از مستندات

هر مقاله `source_refs` دارد تا تیم بداند مطلب از روی کدام view/form/route بازبینی شده است.

## تست UX مهم

در صفحه «مدیریت تیم» این سؤال‌ها را بپرس:

```text
چطور کد تخفیف بسازم؟
چرا متخصصی که اضافه کردم قابل رزرو نیست؟
مشتری چطور زمان نوبتش را عوض کند؟
این صفحه چیه؟
```

انتظار:

- سؤال اول → مقاله کدهای تخفیف، نه مدیریت تیم.
- سؤال دوم → troubleshooting قابل رزرو نبودن متخصص.
- سؤال سوم → مقاله تغییر زمان مشتری؛ مدیر اجازه خواندن customer journey را دارد.
- فقط سؤال چهارم → context همان صفحه می‌تواند اولویت بگیرد.

## اجرای تست‌ها

```powershell
python manage.py test apps.help_center.tests
```

## توسعه محتوای بعدی

مستندات حالا در DB/CMS هستند و JSON فقط bootstrap اولیه است. برای هر workflow یا مشکل جدید:

1. رفتار واقعی staging را از view/form/service بررسی کن.
2. مقاله را در Admin بساز یا fixture را توسعه بده.
3. `source_refs`, aliases و keywords را دقیق ثبت کن.
4. مقاله را publish کن؛ chunkها با signal بازسازی می‌شوند.
5. یک benchmark سؤال واقعی به `audit_help_coverage.py` اضافه کن.


## Recovery from duplicate-slug seed error

If an earlier v1 seed failed with a unique constraint such as
`HC_Articles_slug_key`, replace `seed_help_center.py` with the v1.1 file and run:

```powershell
python manage.py seed_help_center
python manage.py rebuild_help_chunks
python manage.py audit_help_coverage
```

Do **not** run `reset_help_center_prototype --confirm` a second time. The failed
seed was atomic and rolled back; the reset has already done its job.
