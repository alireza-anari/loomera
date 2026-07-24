# Phase 13 — Partner Mobile Home Dashboard

## Scope
این فاز فقط presentation و UX داشبورد موبایل partner / salon manager را تغییر داد. نسخه دسکتاپ داشبورد موجود حفظ شد و در branch دسکتاپ جداگانه باقی ماند.

## Real templates / views
- Route اصلی داشبورد: `dashboards:home` / dashboard home routes موجود
- Template اصلی: `templates/dashboards/home.html`
- Partial اصلی تغییرکرده: `templates/dashboards/partials/overview_intro.html`
- Dashboard shell: `templates/dashboard_template.html`
- Context builder بررسی‌شده: `apps/dashboards/home_components.py`

## Data used
فقط داده‌های واقعی موجود در `dashboard_home` استفاده شد:
- `dashboard_home.workspace`
- `dashboard_home.stats`
- `dashboard_home.actions`
- `dashboard_home.today.items`
- `dashboard_home.upcoming.items`
- `dashboard_home.workspace.focus_items`
- `dashboard_home.primary_calendar_url`
- `dashboard_home.salon_profile_url`

## Data not fabricated
هیچ metric، درآمد، نوبت، مشتری، پرداخت، اعلان، آمار، trend یا appointment ساختگی اضافه نشد.

## Mobile IA decisions
- موبایل داشبورد اکنون branch جدا با `lg:hidden` دارد.
- دسکتاپ branch با `hidden lg:block` حفظ شد.
- موبایل از card-based sections استفاده می‌کند:
  - top context / business context
  - today/business summary
  - quick actions
  - today appointments
  - upcoming appointments
  - focus / business health
- actionها فقط اگر route واقعی و available داشته باشند نمایش داده می‌شوند.

## Desktop preservation
ساختار قبلی دسکتاپ داخل `data-dashboard-home="partner-desktop"` حفظ شد. تغییرات CSS فاز ۱۳ با کلاس‌های `lm-partner-mobile-*` scoped هستند.

## Accessibility
- بخش‌ها heading و `aria-labelledby` دارند.
- appointment lists از `role="list"` و `role="listitem"` استفاده می‌کنند.
- empty states دارای `role="status"` هستند.
- iconهای تزئینی `aria-hidden="true"` دارند.

## Backlog
- Phase 14: اتصال دقیق‌تر appointment cards امروز به calendar / appointment detail rhythm
- Phase 15: preview مشتریان و CRM در dashboard mobile
- Phase 16: sales / payments preview دقیق‌تر اگر داده پرداخت آماده باشد
- Phase 18: insight cards و trend واقعی، بدون ساخت داده fake
