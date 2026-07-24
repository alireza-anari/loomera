# Phase 20 — Component Polish: Cards, Buttons, Chips, Sheets, Icons

## Scope
This phase standardizes cross-product presentation primitives after Phases 01–19. It is intentionally presentation-only.

## Files touched
- `static/css/loomera-brand.css`
- shared component primitives in `templates/components/*`
- dashboard component primitives in `templates/dashboards/components/*`

## Stabilized contracts
- Cards: `lm-card`, `lm-component-card`, `lm-card--interactive`, `lm-card--selected`, `lm-card--disabled`
- Buttons: `lm-btn`, `lm-btn-primary`, `lm-btn-secondary`, `lm-btn-ghost`, `lm-btn-icon`, `lm-btn-sticky-cta`
- Chips/badges: `lm-chip`, `lm-badge`, status-toned aliases
- Forms: `lm-form-card`, `lm-field`, `lm-control`, `lm-form-error`
- Empty states: `lm-empty-state-card`, `role="status"`
- Sheets/modals: `lm-modal-overlay`, `lm-modal-header`, `lm-modal-body`
- Tables/data surfaces: `lm-table-surface`, `lm-report-surface`, `lm-table-responsive`
- Icons: decorative icons use `aria-hidden="true"`; action/icon buttons get accessible labels where touched.

## Data and hook safety
No route, URLconf, view, form validation, query/context builder, model, migration, payment, booking, auth, dashboard, CRM, report, marketing, or search backend behavior was changed.
No input names, form actions, data attributes, or JS selectors were intentionally renamed or removed.
No new assets or font files were added.
`static/css/output.css` was not edited.

## Remaining backlog for Phase 21/22
- Full Persian copy and localization pass across page-specific text.
- Final screenshot diff and regression pass across mobile customer, mobile partner, desktop public, and desktop dashboard surfaces.
- Optional future migration away from legacy `fresha-*` compatibility classes only after usage inventory and testing.
