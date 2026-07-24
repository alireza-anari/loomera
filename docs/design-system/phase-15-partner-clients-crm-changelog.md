# Phase 15 — Partner Clients / CRM

## Scope

این فاز فقط presentation و UX صفحات مشتریان/CRM پنل پارتنر را تغییر داد. هیچ route، URLconf، view logic، query/context builder، model، migration، client backend، appointment backend، payment backend یا dashboard data logic تغییر نکرد.

## Real templates / routes audited

| بخش | مسیر |
| --- | --- |
| لیست مشتریان | `templates/dashboards/salonsCustomersPage.html` |
| کارت‌های مشتریان | `templates/dashboards/partials/salons_customers.html` |
| پروفایل مشتری | `templates/dashboards/customer_detail.html` |
| viewهای مرجع | `apps/dashboards/views.py` |

## Data used

Phase 15 فقط از داده‌های واقعی موجود استفاده می‌کند:

- `customer_workspace`
- `customer_cards`
- `customer_workspace.active_filter_chips`
- `customer_workspace.quick_actions`
- `customer_workspace.focus_items`
- `customer_workspace.appointments`
- `customer_workspace.favorite_services`
- `customer_workspace.notes`
- `customer.user.mobile_number`
- `customer.user.email`
- `customer_primary_address`
- `customer.detail_url`
- `customer.call_url`
- `customer.appointments_url`

هیچ مشتری، نوبت، مبلغ، note، tag، segment، spend یا contact action ساختگی اضافه نشد.

## UX decisions

### Mobile clients

- branch موبایل جدا با `lg:hidden` ساخته شد.
- top context شامل عنوان «مشتریان»، search/sort موجود و CTA افزودن مشتری است.
- metric cards فقط از داده‌های واقعی `customer_workspace` استفاده می‌کنند.
- client cards از همان partial مشترک استفاده می‌کنند تا desktop و mobile data logic یکسان بماند.

### Desktop clients

- desktop branch حفظ شد و CRM-like‌تر شد.
- search/sort فعلی با همان query params موجود باقی ماند.
- list/grid فعلی با card rhythm جدید و accessibleتر نمایش داده می‌شود.

### Client profile

- mobile profile branch جدا ساخته شد.
- profile summary، quick actions، focus items، appointment history و notes card-based شدند.
- desktop profile structure حفظ شد و readableتر شد.
- form ثبت یادداشت با همان `POST`، همان CSRF و همان `name="note"` حفظ شد.

## Compatibility

- `fresha-*` aliasها حذف نشدند.
- `salonify` compatibility حذف نشد.
- action routeها فقط از URLهای موجود استفاده می‌کنند.
- `tel:` فقط زمانی نمایش داده می‌شود که شماره واقعی وجود داشته باشد.
- هیچ mail/SMS/WhatsApp action جدید ساخته نشد.

## Backlog

| مورد | فاز پیشنهادی |
| --- | --- |
| اتصال CRM به POS/Payments و نمایش خریدهای مالی دقیق‌تر | Phase 16 |
| review/marketing prompts برای مشتریان | Phase 17 |
| segment/tag/note advanced workflows | بعد از backend/design phase اختصاصی |
| client import / bulk actions | در صورت وجود backend، فاز CRM تکمیلی |
