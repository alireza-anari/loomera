# Phase 09 — Staff / Specialist Selection Flow Changelog

## Scope
Phase 09 improves the presentation and interaction layer of the customer staff/specialist selection step after service selection. It does not change routing, backend booking logic, staff-selection logic, availability logic, date/time logic, checkout/payment logic, models, migrations, or dashboard data.

## Real route / template / view
- Route: `orders:select_stylists`
- URL pattern: `apps/orders/urls.py` → `select_stylists/`
- View audited: `apps.orders.views.BookingStylistSelectPerService`
- Template changed: `templates/orders/select_stylists.html`
- JS changed: `static/js/select_stylist.js` only for visual selected state and summary updates

## Context and data used
The template uses only data already provided by the current view:
- `salon`
- `salon_id`
- `service_cards`
- `card.service`
- `card.stylists`
- `card.any_option`
- `item.stylist`
- `item.price`
- `item.availability_label`

No fake specialist, rating, availability, price, duration, photo, or service data was added.

## Preserved form / backend hooks
The following backend and JS hooks were preserved:
- Form id: `stylistSelectionForm`
- Hidden input: `name="salon_id"`
- Hidden input: `name="stylist_selections"`, id `stylistSelectionsInput`
- CTA id: `continueBtn`
- Option class: `.stylist-option`
- Required data attributes:
  - `data-service-id`
  - `data-service-name`
  - `data-service-duration`
  - `data-stylist-id`
  - `data-stylist-name`
  - `data-stylist-profile-image`
  - `data-stylist-price`
- Existing storage keys and legacy keys in `static/js/select_stylist.js`
- Existing POST behavior to `orders:select_dateTime` via the current view

## Any-specialist behavior
The existing `card.any_option` behavior was preserved. The UI label was changed to Persian product copy:
- `فرقی ندارد`
- `اولین متخصص آزاد برای این خدمت انتخاب می‌شود.`

The option is disabled if `card.any_option.enabled` is false. No new backend support was added.

## Presentation changes
- Added compact booking progress: service → staff → time → confirmation.
- Added selected services summary at the top of the page.
- Reworked specialist option cards with stronger selected state and ARIA state.
- Added mobile sticky CTA summary using existing form submission.
- Added desktop booking summary card with selected staff count, remaining count, and total price.
- Added empty states for no selected services and no available specialists.

## JS changes
`static/js/select_stylist.js` was updated only to:
- support the new `[data-staff-service-card]` wrapper,
- set `aria-pressed` and `aria-selected`,
- add/remove `is-selected`,
- update mobile and desktop summaries,
- keep the same selection object structure and sessionStorage schema.

## Backend limitations respected
- No staff availability logic was added.
- No date/time behavior was changed.
- No fake first available time was added.
- No rating or specialty text is displayed unless already present in the real object.
- No route or URLconf was changed.

## Backlog for Phase 10
- Carry selected service/staff summary into `templates/orders/select_datetime.html`.
- Use selected stylist/service durations in the date/time UI if already available from existing context.
- Improve unavailable/fully-booked messaging in the date/time step without changing availability logic.
- Keep `stylist_selections` session schema compatible with Phase 09.
