# Phase 18 — Reports, Insights & Business Analytics

## Scope

Phase 18 improves the presentation of partner reports, insights and analytics without changing routes, views, queries, backend calculations, models, migrations, payment logic, CRM logic, marketing logic, or dashboard data builders.

## Real templates and context reviewed

| Area | Source |
|---|---|
| Main reports page | `templates/dashboards/reports.html` |
| Reports context | `apps/dashboards/reports_components.py` |
| Finance report reference | `templates/dashboards/finance_reports.html` from Phase 16 |
| Marketing/reference data | Phase 17 online booking, coupon and basket presentation |

## Real data used

Only existing `reports_dashboard` data is used:

- `reports_dashboard.stats`
- `reports_dashboard.workspace.result_count_label`
- `reports_dashboard.workspace.revenue_total_label`
- `reports_dashboard.workspace.completion_rate_label`
- `reports_dashboard.workspace.customers_label`
- `reports_dashboard.workspace.focus_items`
- `reports_dashboard.workspace.quick_actions`
- `reports_dashboard.chart.summary`
- `reports_dashboard.status_breakdown.items`
- `reports_dashboard.top_services.items`
- `reports_dashboard.top_team.items`
- `reports_dashboard.tabs`
- `reports_dashboard.active_filter_chips`
- `reports_dashboard.filter_summary`
- `reports_dashboard.table`

## Presentation changes

- Added a mobile-only reports overview branch in `templates/dashboards/reports.html`.
- Preserved the existing desktop reports dashboard in a desktop-only branch.
- Added app-like mobile cards for KPI summary, report categories, focus insights, chart summary, status breakdown, service/team rankings, and related action routes.
- Kept the existing filter bar and reports table available on mobile through existing accordion wrappers.
- Added reports-scoped CSS helpers prefixed with `lm-reports-mobile-*` and `lm-reports-desktop`.

## Backend safety

No backend or analytics logic changed. The phase does not add:

- fake KPIs
- fake trends
- fake forecasts
- fake benchmarks
- fake customer insights
- fake marketing performance
- fake revenue data
- fake chart data

## Export/filter behavior

Existing filter forms, query parameters, tabs, preset links and clear-filter URLs are preserved. No export or download route was created.

## Desktop preservation

The existing desktop reports layout, chart widget, status widget, ranking widgets and reports table remain intact. The desktop branch is wrapped in `lm-reports-desktop hidden lg:block` only for responsive separation.

## Backlog

- Deeper cross-domain insights from finance, CRM and marketing should only be added when a real context builder provides those calculations.
- If CSV/export routes are added later, expose them through the existing reports action area.
- Chart accessibility could be expanded with server-provided long descriptions if the backend later provides chart summary text.
- Deeper Jalali/date localization should be reviewed in Phase 21.
