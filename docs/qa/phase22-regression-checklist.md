# Phase 22 — Regression Checklist

## Global

- [ ] No route, URLconf, view, model, migration, form validation, auth/session/permission, payment, booking, dashboard query, CRM, reports, or marketing backend changes in final release diff.
- [ ] `static/css/output.css` was not manually edited.
- [ ] No new asset/font/logo files were added.
- [ ] All changed files are templates/CSS/docs/scripts only unless explicitly approved.
- [ ] `npm run build` passes.
- [ ] `python manage.py check` passes.
- [ ] Browser console has no critical JS errors on representative pages.

## RTL / Persian

- [ ] Visible UI has no unintended English labels.
- [ ] `Salonify` and `Fresha` are not visible in product UI.
- [ ] Back/forward arrows make sense in RTL.
- [ ] Long Persian labels do not break nav, cards, chips, tables, or bottom nav.
- [ ] Phone, amount, date, time and reference codes remain bidi-safe.
- [ ] تومان appears only with real amounts.
- [ ] No fake Jalali conversion is introduced.

## Mobile customer

- [ ] Bottom nav is visible and not overlapped by content.
- [ ] Sticky CTA does not cover important content.
- [ ] Home/search/profile/booking feel app-like, not desktop-shrunk.
- [ ] Service/staff/date/checkout summaries stay readable.
- [ ] Empty/no-result/no-slot states are helpful and have real CTA only.

## Mobile partner

- [ ] Partner bottom nav is visible and operational.
- [ ] Dashboard/calendar/CRM/finance/marketing/reports use app-like cards.
- [ ] Quick actions only point to real routes.
- [ ] Appointment/payment/status badges are readable.
- [ ] Empty states do not invent metrics/actions.

## Desktop public

- [ ] Homepage has website-like spacing, hierarchy and CTA.
- [ ] Search/profile/booking keep desktop layout; no mobile-only density.
- [ ] Auth/signup pages are clear and role-aware.
- [ ] Footer/header/nav remain accessible and not dashboard-like.

## Desktop partner

- [ ] Sidebar/topbar/header remain stable.
- [ ] No mobile bottom nav appears on desktop.
- [ ] Tables have readable headers, rows, actions and empty states.
- [ ] Reports/finance/CRM/marketing panels do not overflow.
- [ ] Filters/forms preserve query/input names and submission behavior.

## Functional smoke

- [ ] Login with valid account.
- [ ] Register customer account.
- [ ] Register partner/salon account.
- [ ] Verify OTP flow where SMS/test backend allows.
- [ ] Search query + location.
- [ ] Open venue profile.
- [ ] Select service.
- [ ] Select stylist / any stylist if supported.
- [ ] Select date/time.
- [ ] Submit reservation preview/checkout.
- [ ] View customer bookings.
- [ ] Open partner dashboard.
- [ ] Open calendar and appointment detail.
- [ ] Open clients/CRM.
- [ ] Open finance/payments.
- [ ] Open marketing/reviews/profile.
- [ ] Open reports.
