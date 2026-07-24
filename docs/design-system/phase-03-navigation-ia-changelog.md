# Phase 03 — Navigation & Information Architecture Changelog

## Scope
Phase 03 تثبیت Navigation و IA بعد از Phase 02 است. در این فاز هیچ route، view، model، migration، asset، font، booking logic، payment logic یا dashboard data/query logic تغییر نکرد.

## Navigation roles

| Role | File | IA decision |
| --- | --- | --- |
| Customer Mobile Nav | `templates/partials/shell/customer_mobile_nav.html` | پنج آیتم app-like: خانه، جستجو، نوبت‌ها، علاقه‌مندی‌ها، حساب من. |
| Customer Mobile Header | `templates/partials/shell/mobile_app_header.html` | header فشرده با slotهای امن برای back/title/subtitle/location/search/filter/account. |
| Desktop Public Nav | `templates/partials/shell/desktop_site_header.html` | navigation وب‌سایتی: سالن‌ها، جستجو، برای کسب‌وکارها، پشتیبانی، ورود/حساب من، شروع کنید. |
| Partner Mobile Nav | `templates/partials/dashboard/mobile_nav.html` | context-driven باقی ماند؛ accessibility، active/disabled state و touch rhythm بهتر شد. |
| Partner Desktop Sidebar | `templates/partials/dashboard/sidebar.html` | context-driven باقی ماند؛ semantics، section labels، active state، disabled state و focus بهتر شد. |
| Partner Topbar/Header | `templates/partials/dashboard/navbar.html`, `templates/partials/dashboard/header.html` | actionهای عملیاتی فعلی حفظ شد؛ ARIA و notification dialog semantics اضافه شد. |

## Active state logic

- Customer/public active state با `request.resolver_match.namespace` و در صورت نیاز `url_name` کنترل می‌شود.
- Partner nav همچنان با `dashboard_mobile_nav_items`, `dashboard_sidebar_sections` و `item.is_active` فعلی کنترل می‌شود.
- هیچ Python context builder در این فاز تغییر نکرد.

## Accessibility changes

- `aria-label` برای navهای اصلی اضافه شد.
- `aria-current="page"` برای لینک فعال اضافه شد.
- `aria-disabled="true"` برای آیتم‌های غیرفعال partner اضافه شد.
- `aria-haspopup`, `aria-expanded`, `aria-controls` برای quick-create و notification trigger اضافه شد.
- iconهای nav با `aria-hidden="true"` مشخص شدند.
- focus-visible navigation در `loomera-brand.css` polish شد.

## URL safety

- هیچ URLconf تغییر نکرد.
- `main:contact` نگه داشته شد چون namespace فعلی resolve می‌شود.
- نکته: include پروژه فعلاً `path("main", include(...))` است و ممکن است URL ظاهراً `maincontact/` بسازد؛ بررسی آن برای route hygiene در فاز جداگانه بماند.
- legacy `salonify` و aliasهای `fresha-*` حذف نشدند.

## CSS additions

- active state navigation
- focus-visible state
- mobile nav touch target
- disabled nav item state
- desktop public nav readability
- sidebar group/active indicator
- safe-area bottom padding

## Backlog

| Phase | Backlog |
| --- | --- |
| Phase 04 | استفاده از customer mobile nav/header primitives در home/discovery. |
| Phase 05 | تبدیل root به landing دسکتاپ و بررسی hygiene مسیر `main:contact` اگر scope اجازه داد. |
| Phase 13 | اگر IA دقیق partner mobile لازم شد، context builderها به خانه/تقویم/مشتریان/فروش/بیشتر align شوند. |
| Phase 14 | استفاده از drawer-ready topbar/sidebar برای calendar و appointment detail. |
| Phase 20 | migration باقی‌مانده utilityهای nav به primitives مشترک. |
