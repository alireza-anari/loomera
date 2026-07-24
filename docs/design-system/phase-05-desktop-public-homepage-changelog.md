# Phase 05 — Desktop Public Homepage Like Fresha Website

## Scope
Phase 05 updates only the public homepage template currently rendered by the root salon listing route. It does not change routes, views, models, migrations, booking logic, payment logic, dashboard data logic, assets, fonts, or generated CSS output.

## Homepage / root template
- Current root/public homepage template: `templates/pages/show_salons.html`
- Rendering view: `apps.salons.views.ShowSalonsView`
- URL route: `apps/salons/urls.py` with `path("", ShowSalonsView.as_view(), name="show_salons")`
- URLconf was not changed.

## Structure implemented
1. Hero section with RTL Persian headline, subheadline, customer CTA and business CTA.
2. Search entry module using existing `search:search_page` route and GET fields `q` and `location`.
3. Service discovery chips for Iran-market beauty categories.
4. City/location discovery chips for Iranian cities.
5. Featured/popular preview using only real context data: `best_discount_salons`, `top_salons`, `recent_salons`.
6. Customer value proposition cards without fake statistics.
7. Partner/business CTA linking to existing register and dashboard entry routes.
8. Trust section without fake numeric claims.

## CSS
Homepage-scoped helpers were added to `static/css/loomera-brand.css`, including `lm-public-home`, `lm-public-hero`, `lm-public-search-card`, `lm-public-search-form`, `lm-public-section`, `lm-public-chip-grid`, `lm-public-city-grid`, `lm-public-business-panel`, and `lm-public-trust`.

## Mobile-safe decision
The homepage remains readable and stacked on mobile, but it is not transformed into the full customer app discovery experience. That remains Phase 04.

## Route and data safety
- No URLconf changes
- No view changes
- No fake numeric statistics
- No new route
- No new assets
- No font file changes
- No manual edit to `static/css/output.css`

## Backlog
- Phase 04: convert customer mobile home/discovery into a richer app-like experience using the existing mobile shell.
- Phase 06: refine search results, filters, map/list, and query-driven landing chips.
- Future route hygiene: decide whether `/` should keep rendering `ShowSalonsView` or move to a dedicated public landing view. This was not changed in Phase 05 to avoid route behavior changes.
