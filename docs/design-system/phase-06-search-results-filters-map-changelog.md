# Phase 06 — Search Results, Filters & Map Experience

## Scope

Phase 06 refined the presentation layer for the customer search experience without changing routes, URLconf, models, migrations, search backend logic, booking/payment behavior, dashboard data logic, assets, fonts, or generated `static/css/output.css`.

## Search route and template

- Route name: `search:search_page`
- View: `apps.search.views.SearchPageView`
- Main template: `templates/pages/search.html`
- Main shell partial: `templates/partials/search/search_page_shell.html`
- AJAX results partial: `templates/search/search_results.html`

## Supported query parameters preserved

The current search page continues to work with the existing parameters surfaced by `SearchPageView` and `filters_from_querydict`:

- `q`
- `location`
- `date`
- `period`
- `time`
- `group`
- `services`
- `sort`
- `lat`
- `lng`

No new backend filters were added.

## Functional filters

Functional filters remain limited to the existing backend-supported fields:

- service/salon text query via `q`
- location via `location`
- date via `date`
- day period via `period`
- exact time via `time`
- service group via `group`
- selected services via `services`
- sort via `sort`
- current location via `lat` / `lng`

## Future / non-functional filters

The mobile filter dialog now reserves disabled future chips for:

- price
- rating
- discounted
- available slot
- venue type

These are intentionally disabled because Phase 06 does not add search backend logic.

## Mobile behavior

The mobile search experience keeps the existing map-backed layout but improves the app-like shell:

- compact search topbar
- filter button with dialog ARIA
- touch-friendly sort/filter chips
- bottom sheet results panel
- horizontal active chips
- improved no-results state
- bottom-nav-safe spacing through existing shell helpers

## Desktop behavior

The desktop search page now uses a web-app-like split:

- right-side results/filter column for RTL
- left-side map panel
- desktop search summary form
- active query chips
- static result panel instead of mobile bottom sheet
- scrollable results list
- sticky-like map surface inside a dedicated panel

## Map availability

The real map container remains `#search-map` and continues to be managed by `static/js/search/map.js`.

- If `MAP_PROVIDER_ENABLED` is true and vendor assets load, the map initializes normally.
- If provider configuration or SDK loading fails, the existing fallback message is shown.
- No fake map, fake map asset, or fake coordinates were added.

## Accessibility

Phase 06 added or preserved:

- `role="search"` for desktop search form
- `aria-label` for mobile/desktop search controls
- `aria-haspopup="dialog"` and `aria-controls="filterScreen"` for filter triggers
- `role="dialog"`, `aria-modal`, and `aria-labelledby` for the filter screen
- `role="list"` / `role="listitem"` for result lists/cards
- `aria-live` on status/loading/fallback areas

## Compatibility

- Existing IDs used by `static/js/search/filters.js` were preserved: `filtersSheet`, `searchBarButton`, `searchBarText`, `openFilterBtn`, `filterScreen`, `filterApplyBtn`, `salonList`, and related filter inputs.
- `fresha-*` aliases and `salonify` compatibility routes were not removed.
- Homepage Phase 04/05 templates were not changed.

## Backlog

Recommended next work:

1. Phase 07 should align result cards with the salon profile entry experience.
2. A later search/backend phase can make price/rating/discount/venue-type filters functional.
3. Search map can be improved with richer marker cards and a mobile map/list toggle if the map provider is fully configured.
4. Phase 21 should run a copy/localization pass on all filter labels and search states.
