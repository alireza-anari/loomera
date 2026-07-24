# Phase 14 — Partner Calendar & Appointment Management

## Scope
Presentation-only update for partner calendar and appointment management.
No route, URLconf, view logic, context/query builder, appointment create/edit/cancel logic, payment logic, availability logic, model, migration, asset, font file, or `static/css/output.css` was changed.

## Real templates/routes audited
- `templates/dashboards/appointment_calendar.html`
- `templates/dashboards/partials/appointment_schedule_board.html`
- `apps.dashboards.views.calendar_view`
- `apps.dashboards.appointment_management.build_appointment_management_context`

## Data used
- `appointment_management.stats`
- `appointment_management.active_filter_chips`
- `appointment_management.focus_navigation`
- `appointment_management.schedule_board.date_label`
- `appointment_management.schedule_board.opening_label`
- `appointment_management.schedule_board.time_slots`
- `appointment_management.schedule_board.summary`
- `appointment_management.schedule_board.columns`
- `appointment_management.schedule_board.columns[].appointments`
- `appointment_management.table`
- `appointment_management.workspace.focus_items`
- `appointment_management.workspace.quick_actions`

## Mobile IA decisions
- Add mobile-only agenda experience through the existing `appointment_management` context.
- Keep appointment cards grouped by real stylist/resource columns.
- Show summary and quick actions only from existing context data.
- Use existing appointment detail URLs; no new action routes were created.

## Desktop IA decisions
- Preserve dashboard shell and sidebar/topbar behavior.
- Replace the generic web-dashboard rhythm with a scheduler-like layout using existing staff/resource columns.
- Keep the existing table include for bulk operations and operational continuity.

## Not faked
No fake appointments, staff columns, time slots, payment states, revenue, availability, filters, or appointment actions were added.

## Backlog
- Phase 15: connect customer/client data from appointments into CRM surfaces.
- Phase 16: enrich real sales/payment preview when finance context is available.
- Phase 18: add real analytics/trend cards when reporting data is available.
