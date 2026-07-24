# Phase 01 — Loomera × Fresha Design Foundation Changelog

این فایل فقط تغییرات foundation بصری Phase 01 را ثبت می‌کند. در این فاز هیچ route، view logic، model، migration، booking/payment behavior، dashboard data logic، asset جدید یا فایل فونت اضافه نشده است.

## Source of truth

- سورس اصلی: `loomera (2).zip`
- برند و assetها: `files.zip` و فایل‌های موجود در `static/branding/*`
- Fresha فقط benchmark ریتم بصری و UX است؛ رنگ، لوگو، asset یا layout دقیق از Fresha وارد نشده است.

## فایل‌های foundation به‌روزرسانی‌شده

| فایل | تغییر |
|---|---|
| `tailwind.config.js` | اضافه شدن semantic tokenهای Loomera-first برای brand، surface، text، border، status، state، payment، focus، spacing، radius، elevation و compatibility alias. |
| `static/css/loomera-brand.css` | تعریف runtime CSS variables، mobile app surfaces، desktop website/web-app surfaces، cards، buttons، chips، forms، modal/sheet/drawer، tables/data surfaces، loader و brand asset hooks. |
| `static/css/loomera-typography.css` | آماده‌سازی hook فونت Yekan Bakh، fallback stack، type scale فارسی، numeric rules و RTL-first typography. |
| `templates/components/*` و `templates/dashboards/components/*` منتخب | اضافه شدن classهای primitive مثل `lm-card`, `lm-form-card`, `lm-table-surface`, `lm-dashboard-metric-card`, بدون redesign صفحه‌ای. |

## مسیر فونت Yekan Bakh

بعد از خرید، فایل‌های فونت را دقیقاً در مسیر زیر قرار بدهید:

```text
static/fonts/yekan-bakh/YekanBakh-Regular.woff2
static/fonts/yekan-bakh/YekanBakh-Medium.woff2
static/fonts/yekan-bakh/YekanBakh-SemiBold.woff2
static/fonts/yekan-bakh/YekanBakh-Bold.woff2
```

نبودن فایل‌ها باعث شکست build نمی‌شود؛ browser به `Vazirmatn`, `IRANSansX` و سپس system font fallback می‌کند.

## Compatibility notes

- aliasهای `fresha-*` در `tailwind.config.js` عمداً باقی مانده‌اند و به tokenهای Loomera map شده‌اند.
- این aliasها هنوز در بعضی فایل‌های Python-generated class استفاده می‌شوند و حذف مستقیم آن‌ها ممکن است UI موجود را بشکند.
- migration کامل `fresha-*` باید در Phase 20 یا یک phase cleanup جدا انجام شود، نه در Phase 01.

## Foundation primitives

### Cards

- `lm-card`
- `lm-card--compact`
- `lm-card--default`
- `lm-card--spacious`
- `lm-card--elevated`
- `lm-card--interactive`
- `lm-card--selected`
- `lm-card--disabled`
- `lm-venue-card`
- `lm-booking-card`
- `lm-dashboard-metric-card`
- `lm-form-card`
- `lm-list-detail-card`
- `lm-empty-state-card`

### Buttons

- `lm-btn`
- `lm-btn-primary`
- `lm-btn-secondary`
- `lm-btn-ghost`
- `lm-btn-destructive`
- `lm-btn-link`
- `lm-btn-icon`
- `lm-btn-sticky-cta`
- `is-loading`
- `is-disabled`

### Chips / badges / statuses

- `lm-chip`
- `lm-chip--interactive`
- `lm-chip--selected`
- `lm-chip--disabled`
- `lm-badge`
- `lm-badge--success`
- `lm-badge--warning`
- `lm-badge--danger`
- `lm-badge--info`
- `lm-badge--neutral`
- `lm-badge--count`
- `lm-status--pending`
- `lm-status--confirmed`
- `lm-status--cancelled`
- `lm-payment--paid`
- `lm-payment--unpaid`
- `lm-payment--failed`
- `lm-payment--processing`

### Forms

- `lm-field`
- `lm-field-label`
- `lm-field-helper`
- `lm-field-error`
- `lm-control`
- `lm-input`
- `lm-select`
- `lm-textarea`
- `lm-checkbox`
- `lm-radio`
- `lm-toggle`

### Surfaces

- `lm-app-surface`
- `lm-app-container`
- `lm-app-card`
- `lm-app-sticky-header`
- `lm-app-bottom-nav-surface`
- `lm-app-sticky-cta-surface`
- `lm-app-bottom-sheet-surface`
- `lm-desktop-canvas`
- `lm-wide-container`
- `lm-hero-surface`
- `lm-section-surface`
- `lm-dashboard-canvas`
- `lm-dashboard-sidebar-surface`
- `lm-dashboard-panel`
- `lm-desktop-drawer-surface`
- `lm-scheduler-surface`

## QA notes

- `static/css/output.css` در این فاز دستی تغییر نکرده است.
- اگر Node/Tailwind dependencies روی محیط نصب باشد، build استاندارد پروژه این است:

```bash
npm run build
```

- اگر dependencies نصب نیستند، قبل از build باید `npm install` یا `npm ci` طبق سیاست پروژه اجرا شود.
