# Loomera Email & Domain System

این پوشه reference رسمی email/domain/notification visual header برای Loomera است.

## Canonical docs
- `loomera-domain-email-system.md`
- `loomera-notification-email-visual-header-system.md`
- `snippets/loomera-email-base-rtl.html`
- `snippets/loomera-minimal-transactional-email.html`

## Runtime templates اضافه‌شده
- `templates/email/loomera_email_base_rtl.html`
- `templates/email/loomera_minimal_transactional.html`

این templateها source-ready هستند و از contextهای زیر استفاده می‌کنند:
- `subject`
- `category_label`
- `headline`
- `support_line`
- `body_html`
- `cta_url`
- `cta_label`
- `sender_name`

## Env/settings مورد نیاز
- `DEFAULT_FROM_EMAIL`
- `SERVER_EMAIL`
- `LOOMERA_SUPPORT_EMAIL`
- `LOOMERA_PARTNER_EMAIL`
- `LOOMERA_MARKETING_EMAIL`
- `LOOMERA_CRM_SENDER_NAME`
- `LOOMERA_CRM_REPLY_TO_EMAIL`

## RTL و فارسی
تمام email shellها با `lang="fa"` و `dir="rtl"` تعریف شده‌اند. لحن باید calm، clear، trusted و product-ready بماند.
