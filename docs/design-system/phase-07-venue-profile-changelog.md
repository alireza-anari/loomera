# Phase 07 — Venue / Salon Profile Page Changelog

## Scope

Phase 07 updated the public customer venue/salon profile presentation while preserving routes, view logic, booking/payment behavior, models, migrations, dashboard logic, and all existing brand assets.

## Real template and route

- Route: `salons:detail_salon`
- URL pattern: `apps/salons/urls.py` → `detail_salon/<int:salon_id>/`
- View inspected but not changed: `apps/salons/views.py` → `DetailSalonView`
- Template changed: `templates/pages/detail_salon.html`

## Data used

Only existing context/model data was used:

- `salon`
- `services`
- `service_groups`
- `stylists`
- `comments_list`
- `opening_hours_list` / `salon.ordered_opening_hours`
- `supplementary_info`
- `average_score`
- `total_reviews`
- `is_favorite`
- `salon.gallery_images.all`
- `salon.address`
- `salon.location`
- `salon.phone_number`

No fake gallery image, review, rating, map, price, distance, availability, or business statistic was added.

## Presentation decisions

### Mobile profile

- Kept the existing detail page route and JS contract.
- Added a mobile-first venue summary card after the gallery.
- Kept existing gallery component and fallback behavior.
- Added section-anchor navigation for services, samples, specialists, reviews, about, location, and extra information when data exists.
- Kept mobile sticky booking CTA behavior with the original `bookingBar`, `bookingSubmitBtn`, and service selection draft flow.
- Improved quick actions using only safe existing links/actions: services anchor, phone link when present, location anchor when present, favorite toggle, share.

### Desktop profile

- Added a wide profile layout with main content and a desktop booking sidebar.
- Desktop sidebar points to the services section and does not create a new booking flow.
- Services, staff, reviews, information, and location remain in the same template and use existing data.
- Map panel uses the existing `#salonMap` and JavaScript integration.

## Component updates

Updated only primitives directly used by the venue profile:

- `templates/components/service_item.html`
- `templates/components/team_member.html`
- `templates/components/review_item.html`

These updates preserved existing JS hooks:

- `.service-item`
- `.add-service-btn`
- service `data-*` attributes
- review modal data contract
- team card display data

## CSS updates

Added venue-scoped helpers to `static/css/loomera-brand.css`:

- `lm-venue-profile-shell`
- `lm-venue-profile`
- `lm-venue-hero`
- `lm-venue-topbar`
- `lm-venue-layout`
- `lm-venue-summary`
- `lm-venue-section-nav`
- `lm-venue-section`
- `lm-venue-service-list`
- `lm-venue-booking-sidebar`
- `lm-venue-sticky-cta`
- `lm-venue-map`

`static/css/output.css` was not edited manually.

## Alignment with Phase 06

Search result cards and venue profile now share:

- calmer card rhythm
- rating pattern
- address/location rhythm
- service-first CTA language
- `lm-card`, `lm-chip`, `lm-badge`, and `lm-btn-*` primitives
- no fake rating/price/availability data

## Backlog for Phase 08 and Phase 09

### Phase 08 — Service Selection Flow

- Extract a dedicated service selection shell if needed.
- Make selected service state visually richer.
- Improve summary of selected services before staff selection.
- Keep `bookingSelectionDraft` compatibility.

### Phase 09 — Staff / Specialist Selection Flow

- Align specialist cards with the updated profile specialist preview.
- Decide whether the profile specialist section should link into staff selection once a service is selected.
- Keep staff availability logic in the booking phase, not in profile.

## Not changed

- Routes / URLconf
- View logic
- Models / migrations
- Search backend
- Booking backend or selection behavior
- Payment / checkout logic
- Dashboard / partner pages
- Brand assets / logo / fonts
- Legacy aliases such as `fresha-*` or `salonify`
