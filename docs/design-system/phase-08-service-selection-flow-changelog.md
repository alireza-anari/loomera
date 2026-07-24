# Phase 08 — Service Selection Flow Changelog

## Scope
Phase 08 improves only service selection presentation and booking-entry summary on the venue profile page. It does not change routes, views, models, migrations, booking backend behavior, payment logic, search backend, dashboard logic, assets, fonts, or static/css/output.css.

## Changed targets
- templates/pages/detail_salon.html
- templates/components/service_item.html
- static/js/pages/detail_salon.js
- static/css/loomera-brand.css

## Preserved hooks
.service-item, .add-service-btn, .service-group-btn, #serviceGroups, #servicesList, #showAllServicesBtn, #bookingBar, #bookingSubmitBtn, data-service-id, data-service-name, data-service-price, data-service-duration, data-service-description, data-service-score, data-salon-id, and data-booking-url remain available.

## Selection behavior
Service cards expose stronger selected state with is-selected, aria-selected, and aria-pressed. The flow remains frontend-driven and uses the existing booking draft storage path. Multi-service selection remains supported by the existing frontend Map-based behavior. No backend service selection logic was added.

## Mobile sticky summary
The mobile sticky summary keeps #bookingBar, #bookingCount, #bookingPrice, #bookingDuration, and #bookingSubmitBtn, but presents the information in a clearer app-like summary using Phase 01 primitives.

## Desktop sidebar summary
The desktop booking card includes #desktopBookingEmptyState, #desktopBookingSelectedMeta, #desktopBookingCount, #desktopBookingPrice, and #desktopBookingDuration. The desktop CTA uses data-booking-submit-trigger and the existing booking URL.

## Backend limitations
No availability state was added because current venue service data does not expose confirmed availability per service in this template. No fake price, duration, service, discount, or service description was added.

## Backlog
Phase 09 should connect selected services to staff selection. Phase 10 should show selected-service summary and availability states in date/time selection.
