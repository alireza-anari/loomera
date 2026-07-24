# Phase 21 — RTL Persian Copy & Iran Localization Pass

## Scope

This phase performs a presentation-only Persian localization and RTL pass. It updates visible UI copy in templates where safe, adds RTL/bidi helper CSS, and documents remaining localization backlog.

## Safety

No route, URLconf, view, query/context builder, form validation, backend logic, model, migration, payment, booking, auth, permission, dashboard, CRM, marketing, or reports logic is changed.

No fake date, Jalali conversion, price, metric, status, action, insight, profile readiness, or verification state is created.

## Main copy decisions

- `ثبت نام` → `ثبت‌نام`
- `تایید` → `تأیید`
- English operational leftovers such as `dead-end`, `workspace`, `planner`, `time off`, `Reconciliation`, `Payment Mix`, and `Wallet Flow` are localized where they appear as visible UI copy.
- Customer-facing copy should stay calm, short, and booking-oriented.
- Partner-facing copy should stay operational, direct, and dashboard-oriented.
- Auth/onboarding copy should remain trustworthy and low-anxiety.

## Date / number / currency decisions

- No fake Jalali conversion is introduced.
- Existing Jalali/date labels remain the source of truth.
- `lm-amount`, `lm-price`, `lm-currency`, `lm-percent`, `lm-numeric`, `lm-date`, and `lm-time` are reinforced for bidi-safe presentation.
- `تومان` should only be used where real amount data exists.

## Backlog for Phase 22

- Screenshot diff and manual visual QA across customer mobile, partner mobile, public desktop, and partner desktop.
- Full audit of dynamically generated labels from Python forms/views if any remain English.
- Optional deeper standardization of status labels only if backend exposes a safe presentation mapping.
