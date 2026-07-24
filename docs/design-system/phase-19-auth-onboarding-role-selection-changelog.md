# Phase 19 — Auth, Onboarding & Role Selection

## Scope

Phase 19 only changes presentation for authentication, signup, verification, password recovery, and partner onboarding surfaces. It does not change routes, URLconf, views, forms, validation, sessions, redirects, permissions, models, migrations, or dashboard/customer/booking/payment logic.

## Real routes and templates audited

| Area | Route / view | Template |
|---|---|---|
| Login | `accounts:login` / `LoginUserView` | `templates/accounts/login.html` |
| Customer signup | `accounts:customer_signup` / `CustomerSignupView` | `templates/accounts/customer_signup.html` |
| Partner signup | `accounts:register` / `RegisterUserView` | `templates/accounts/register.html` |
| Verification | `accounts:verify` / `VerifyRegisterView` | `templates/accounts/verify.html` |
| Password recovery | `accounts:remember_password` / `RememberPasswordView` | `templates/accounts/remember_password.html` |
| Partner setup | dashboard salon profile creator views | `templates/dashboards/salon_profile_creator_step*.html` via shared `page_hero.html` |

## Preserved hooks

- Login fields: `mobile_number`, `password`
- Signup fields: `name`, `family`, `mobile_number`, `password1`, `password2`, `agree_to_terms`
- Verification field: `active_code`
- CSRF tokens and form methods
- Existing URL names for login, customer signup, partner register, verify, and password recovery
- Existing password visibility JS behavior in signup pages
- Existing partner onboarding save/continue behavior through dashboard forms

## Presentation decisions

- Auth pages use a new `lm-auth-*` shell with mobile-first cards and desktop split layout.
- Login now clearly presents the two paths: customer and salon/partner.
- Customer and partner signup keep separate real routes and form fields, but now explain the next steps.
- Verification and password recovery share the same auth surface language.
- Partner profile creator pages get an onboarding stepper via the shared `page_hero.html` only when the eyebrow is `ساخت پروفایل سالن`.
- No role-selection route was created because no independent route/template currently exists.

## What was not faked

- No fake role, OTP, verification state, redirect, readiness percentage, profile completion score, onboarding step completion, or permission state.
- No asset, logo, or font file was added.
- No backend behavior was changed.

## Backlog

- A dedicated role-selection landing route can be added only if product routing explicitly allows it.
- Customer onboarding preferences should be added only if real forms/context exist.
- Partner readiness percentages should come from real dashboard/profile data, not frontend assumptions.
- Phase 20 should audit auth forms against all customer/partner shell and component primitives.
