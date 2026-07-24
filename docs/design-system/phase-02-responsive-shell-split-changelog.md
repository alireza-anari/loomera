# Phase 02 — Responsive Shell Split Changelog

Scope: shell, layout, navigation, header, container and responsive wrapper changes only. No routes, view logic, models, migrations, booking logic, payment logic, dashboard data logic, assets, or font files were changed.

## Source baseline
- Project source: `loomera (2).zip` with Phase 01 foundation patch applied.
- Foundation primitives used: `lm-app-*`, `lm-desktop-*`, `lm-dashboard-*`, `lm-btn-*`, `lm-card-*`, `lm-bottom-sheet-surface`, `lm-side-drawer-surface`, `lm-backdrop`.

## Shell roles introduced

| Role | Primary templates | Purpose |
|---|---|---|
| Customer Mobile App Shell | `templates/base.html`, `templates/partials/shell/mobile_app_header.html`, `templates/partials/shell/customer_mobile_nav.html` | App-like mobile shell for discovery, search, booking, checkout, account and favorites. |
| Partner Mobile App Shell | `templates/dashboard_template.html`, `templates/partials/dashboard/mobile_nav.html`, `templates/partials/dashboard/navbar.html` | Touch-friendly light partner mobile shell with existing dashboard data/content preserved. |
| Desktop Public Website Shell | `templates/base.html`, `templates/partials/shell/desktop_site_header.html` | Website-like desktop shell with wide container, desktop header and no bottom nav. |
| Desktop Partner Web-App Shell | `templates/dashboard_template.html`, `templates/partials/dashboard/sidebar.html`, `templates/partials/dashboard/navbar.html` | Operational dashboard shell with sidebar, topbar, content container and drawer-ready surfaces. |

## Compatibility notes
- `templates/partials/navbar.html` remains as a compatibility wrapper and includes `partials/shell/customer_mobile_nav.html`.
- Existing URL names are reused; no route was added, removed or renamed.
- Existing dashboard inclusion tags remain unchanged.
- Existing `fresha-*` and `salonify` compatibility aliases remain unchanged.

## Build note
`static/css/output.css` is not edited manually. Run the project CSS build after Node dependencies are installed.
