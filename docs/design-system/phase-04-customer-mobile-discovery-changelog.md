# Phase 04 — Customer Mobile Home / Discovery App

## Scope

Phase 04 turns the mobile rendering of `templates/pages/show_salons.html` into a customer discovery app surface while preserving the desktop public homepage created in Phase 05.

No route, view, model, migration, search backend, booking/payment behavior, dashboard data logic, asset, logo, font file, or generated CSS output was changed.

## Homepage/root template

- Current root/homepage template: `templates/pages/show_salons.html`
- Current rendering view: `apps/salons/views.py` → `ShowSalonsView`
- URL behavior: unchanged
- Desktop public homepage: preserved as the `hidden lg:block` branch
- Mobile customer discovery: added as the `lg:hidden` branch

## Mobile sections added

| Section | Purpose | Data source | Notes |
| --- | --- | --- | --- |
| Mobile greeting/context | App-like customer entry point | `user` from existing context | Uses first name/username only if authenticated |
| Mobile search card | Search-first booking entry | Existing `search:search_page` route | Uses `GET` with `q` and `location`, same as Phase 05 |
| Quick service categories | Fast discovery for common beauty services | Static labels only | Links to existing search route; no new route |
| Book again | Personalized rebooking | `book_again_orders` | Rendered only if existing real data is present |
| Discounted salons | Deal discovery | `best_discount_salons` | Rendered only if existing real data is present |
| Top salons | Popular venue discovery | `top_salons` | Rendered only if existing real data is present |
| Favorites | Saved venues | `favorits_salons` | Rendered only if existing real data is present |
| Recent salons | New venue discovery | `recent_salons` | Rendered only if existing real data is present |
| City chips | Iran city discovery | Static city labels | Links to existing search route using `location` query |
| Customer value | Compact mobile trust/value | Static copy, no numeric claims | Three compact cards only |
| Partner CTA | Small business-side entry | Existing register route | Kept compact and placed at the end |

## Desktop preservation decisions

- The Phase 05 desktop homepage branch remains intact.
- Desktop sections remain under `.lm-public-home.hidden.lg:block`.
- Mobile discovery sections are under `.lm-mobile-discovery.lg:hidden`.
- Desktop search, service/city sections, featured preview, partner CTA, and trust section are not redesigned in this phase.

## Data decisions

- No fake salon data was added.
- No fake statistics or claims were added.
- Personalized sections are conditional and only render when existing context data is present.
- City and service labels are static discovery shortcuts and use existing search URLs.

## Mobile visual rules

- Uses Phase 01/02 primitives: `lm-app-card`, `lm-card`, `lm-chip`, `lm-btn-primary`, `lm-btn-secondary`, `lm-venue-card`.
- Adds only mobile-home scoped helpers in `static/css/loomera-brand.css`.
- Horizontal rails are scroll-safe and touch-friendly.
- Bottom navigation spacing is respected through `--lm-bottom-nav-space` and `env(safe-area-inset-bottom)`.

## Accessibility

- Mobile branch has one H1 for mobile viewport.
- Desktop branch keeps its desktop H1 but is hidden in mobile viewport.
- Mobile search has `role="search"` and descriptive `aria-label`.
- Horizontal rails use `role="list"` and `role="listitem"`.
- Decorative icons remain `aria-hidden="true"`.

## Backlog

- Phase 06 should connect search/results filters more deeply to the mobile search entry.
- Phase 07 should align venue cards/profile entry after this mobile discovery surface.
- Phase 12 can strengthen authenticated customer personalization if more account data is exposed safely.
