# Phase 10 — Date & Time Booking Flow Changelog

## Scope
Phase 10 refines only the presentation layer for the date/time booking step. It does not change URLconf, routes, Django views, booking backend behavior, availability calculation contracts, checkout/payment, models, migrations, dashboard data, assets, logos, fonts, or generated `static/css/output.css`.

## Real route / template / view

| Item | Value |
|---|---|
| Route name | `orders:select_dateTime` |
| URL pattern | `apps/orders/urls.py` → `select_dateTime/` |
| View | `apps.orders.views.BookingDateTimeSelectPersian` |
| Template | `templates/orders/select_datetime.html` |
| Primary JS | `static/js/select_datetime.js` |

## Preserved hooks and contracts

| Hook / contract | Status |
|---|---|
| `#hiddenData` | Preserved |
| `data-salon-id` | Preserved |
| `data-selections` | Preserved |
| `#dateTimeSelectionForm` | Preserved |
| `#bookingDataInput` | Preserved |
| POST field `booking_data` | Preserved |
| `state.selections` | Preserved |
| `state.picked` / `datetime_selections` | Preserved |
| `stylist_selections` payload | Preserved |
| API `/orders/api/availability/` | Preserved |
| API `/orders/api/stylists-for-service/` | Preserved |
| `window.SelectDateTime` | Preserved |
| `window.openSalonCalendarPicker` | Preserved |

## What changed

- Added a booking progress header for the third step: service → staff → time → confirmation.
- Added a visible selected service/staff summary using the existing `stylist_selections_json` data.
- Improved the date selector as an RTL/Jalali date rail with clearer selected/disabled states.
- Grouped real available time slots into morning, noon, evening, and night based on actual slot times.
- Added mobile sticky CTA and desktop booking side summary using existing form submission behavior.
- Added no-slot empty state without creating fake slots.
- Added `aria-current`, `aria-pressed`, `aria-disabled`, `aria-live`, and status semantics where safe.

## Data safety

No fake dates, fake time slots, fake availability, fake price, fake duration, or fake staff data were added. Prices and durations are shown only when already present in the existing selection payload.

## Jalali / Persian date notes

The existing `JalaliDate` and `jalaliDatepicker` helpers are still used. No backend Jalali logic was changed. If deeper calendar localization is needed, it should be handled in a later dedicated localization pass.

## Backlog for Phase 11

- Carry the selected service/staff/date/time summary into reservation preview and checkout.
- Preserve the resolved stylist for “فرقی ندارد” in the confirmation summary.
- Improve cancellation/payment policy display in checkout without changing payment logic.
- Add final no-surprise summary before payment/confirmation.
