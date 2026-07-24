# Loomera Brand QA Pass — Summary Ready

## نتیجه سریع
Loomera از نظر **brand foundation** قوی و منسجم است، اما از نظر **implementation readiness** هنوز کامل آماده launch نیست. فایل‌های brand داخل `files.zip` و docs داخل `loomera.zip` یک هویت روشن می‌سازند: آرام، دقیق، قابل‌اعتماد، refined و quietly premium؛ اما runtime محصول هنوز در چند نقطه مهم با آن sync نشده است.

## Source of truth استفاده‌شده
- `files.zip`: مرجع اصلی brand/design/content assetها، چون جدیدتر و کامل‌تر است.
- `loomera.zip`: مرجع implementation واقعی، templates، settings، routes، storage، docs داخل repo.
- Canonical docs مهم: `loomera-mini-brand-guideline.md`, `loomera_design_tokens.json`, `loomera-tailwind-theme.ts`, `loomera-typography-handoff.md`, `loomera-core-copy-pack.md`, `loomera-microcopy-system.md`, `loomera-cta-state-message-library-fa.md`, `loomera-domain-email-system.md`, `loomera_crm_template_set_final`.

## قضاوت launch readiness
**Status: Partial / Not ready for full public brand launch**

Brand system آماده است؛ محصول باید قبل از launch عمومی حداقل این blockerها را ببندد:
1. جایگزینی favicon legacy با glyph Loomera.
2. واردکردن tokenهای Loomera به Tailwind runtime و حذف/alias کردن `legacy-design-namespace-*`.
3. Load کردن typography system در base و dashboard templates.
4. ساخت/بازیابی OG + social + launch hero assets و افزودن meta tags.
5. تکمیل landing/home؛ `templates/pages/home.html` خالی است.
6. sync کردن checkout/email/CRM runtime با docs و template set.
7. کاهش salon-first wording در UIهای عمومی و استفاده از center/provider/specialist.

## Score
**72/100 برای brand foundation**  
**56/100 برای product implementation alignment**  
**Overall brand launch readiness: 62/100**

## Top 10 fixes
1. `static/images/icons/favicon.png` را با `static/branding/favicon/*` جایگزین کن.
2. `templates/base.html` و `dashboard_template.html` را با favicon snippet و typography CSS به‌روزرسانی کن.
3. `tailwind.config.js` را از `legacy-design-namespace` به `loomera` migrate کن.
4. `static/css/output.css` را rebuild کن.
5. `templates/pages/home.html` را بر اساس Core Copy + Launch Hero بساز.
6. `templates/orders/checkout.html` و `templates/payments/*` را با Checkout Branding Kit sync کن.
7. lifecycle emails را به CRM template renderer وصل کن.
8. OG/default meta system را در base template اضافه کن.
9. user-facing copy را از salon-only به provider/center/specialist اصلاح کن.
10. manifest واحد برای asset packages و docs بساز.
