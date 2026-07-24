# Loomera CRM Template Set — Final Package

این پکیج شامل CRM strategy، segment mapping، channel strategy، journey mapping، ruleها، template library، JSON registry، cadence rules، personalization tokens و snippetهای HTML email-safe است.

## فایل‌های اصلی
- `docs/loomera-crm-template-set-fa.md` نسخه کامل source-ready
- `docs/loomera-crm-summary-ready-fa.md` نسخه خلاصه برای docs/marketing یا docs/crm
- `docs/loomera-crm-implementation-notes-fa.md` یادداشت implementation
- `manifest/loomera-crm-template-set.manifest.json` registry پکیج
- `manifest/source-review.json` خلاصه بررسی sourceها
- `config/loomera-crm-personalization-tokens.json` tokenها و fallback logic
- `config/loomera-crm-cadence-rules.json` cadence و frequency caps
- `snippets/email/loomera-email-base-rtl.html` قالب پایه HTML email
- `snippets/email/loomera-minimal-transactional-email.html` قالب transactional minimal
- `templates/` familyهای CRM با variantهای email، short-form و in-app

## Source decision
`files.zip` برای هویت برند و copy system کامل‌تر و منسجم‌تر بود؛ `loomera.zip` برای triggerهای واقعی محصول و implementation surfaces استفاده شد.
