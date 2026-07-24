# Loomera CRM Template Integration

این پوشه نسخه‌ی source-ready از CRM Template Set برند Loomera را داخل repo نگه می‌دارد.

## Canonical source
- source package: `files.zip / loomera_crm_template_set_final`
- repo path: `docs/crm/source/`
- runtime sender config:
  - `BRAND_NAME`
  - `BRAND_DOMAIN`
  - `LOOMERA_EMAIL_SENDER_NAME`
  - `DEFAULT_FROM_EMAIL`
  - `LOOMERA_SUPPORT_EMAIL`
  - `LOOMERA_CRM_SENDER_NAME`
  - `LOOMERA_CRM_REPLY_TO_EMAIL`
  - `LOOMERA_CRM_TEMPLATE_DOCS_DIR`

## ساختار
- `source/templates/`: lifecycle templates برای welcome، booking reminder، previsit، postvisit، rebook، winback، payment recovery، support follow-up و موارد مشابه.
- `source/snippets/json/`: library و channel variants.
- `source/config/`: cadence rules و personalization tokens.
- `source/docs/`: notes، summary و handoff.
- `source/manifest/`: manifest و source-review.

## نحوه استفاده در runtime
فعلاً پروژه email/CRM renderer اختصاصی ندارد. بنابراین این فایل‌ها source of truth محتوایی هستند و نباید مستقیم به‌عنوان binary asset استفاده شوند. وقتی renderer اضافه شد:
1. داده‌های کاربر را با personalization tokens map کنید.
2. sender/reply-to را از settings بخوانید.
3. HTML shell را از `templates/email/loomera_email_base_rtl.html` یا `templates/email/loomera_minimal_transactional.html` render کنید.
4. متن in-app را از فایل‌های `inapp-notification.fa.md` بگیرید.
5. cadence را با `source/config/loomera-crm-cadence-rules.json` کنترل کنید.

## نکته مهم
هیچ تصویر، لوگو یا header binary در این فاز کپی نشده است. اگر ایمیل نیاز به header image داشته باشد، مسیر انتقال دستی باید از Phase 4 asset transfer list انجام شود.
