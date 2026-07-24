# Phase 17 — Partner Marketing, Reviews & Marketplace Profile Changelog

## Scope
- Presentation-only pass for partner marketing, online booking readiness, marketplace profile, reviews summary, coupons and basket discounts.
- No route, URLconf, view, context/query builder, campaign/review/payment backend, model or migration changes.

## Templates changed
- `templates/dashboards/online_booking.html`
- `templates/dashboards/salon_profile_view.html`
- `templates/dashboards/finance_coupons.html`
- `templates/dashboards/finance_baskets.html`

## Real data used
- `online_booking_workspace` readiness, focus items, counts and action URLs.
- `salon_profile_workspace` readiness, preview/edit URLs, average score label and profile counts.
- `coupon_stats`, `coupons`, `basket_stats`, `baskets` and their existing POST actions.

## Not faked
- Campaign performance, revenue impact, reviews, ratings, profile score, customer segments, coupons, basket discounts, marketplace publishing state and online booking state.

## Compatibility
- Existing form actions, CSRF tokens, POST toggle/delete/update actions and Jalali datepicker initialization are preserved.
- Existing `fresha-*` and `salonify` compatibility aliases are untouched.

## Backlog
- Dedicated review management/reply page if backend route exists.
- Marketplace profile detail drawer only if a real route/context is added.
- Campaign performance cards using real conversion/revenue data in Phase 18.
- Deeper Persian/localization pass in Phase 21.
