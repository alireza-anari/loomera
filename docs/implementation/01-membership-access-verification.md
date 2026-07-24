# Phase 1 — Roles, Salon Membership, Staff Access and Salon Verification

## Scope

This phase introduces the new membership/access layer without rewriting the existing UI.
The legacy relations are kept for compatibility:

- `Salon.stylists`
- `JobDetails`
- existing dashboard templates and Tailwind classes

The new layer is added beside them and synced gradually.

## Added models

- `Salon.verification_status`
- `SalonMembership`
- `StaffDashboardPermission`
- `MembershipEvent`
- `SalonVerification`
- `SalonVerificationDocument`
- `BankAccount`

## Added service layer

File: `apps/salons/membership.py`

Important helpers:

- `sync_legacy_membership`
- `invite_or_attach_stylist`
- `change_membership_status`
- `ensure_membership_permissions`
- `ensure_salon_verification`
- `get_active_salon_for_stylist`

## Compatibility decisions

1. `Salon.stylists` remains in place so existing dashboards do not break.
2. `JobDetails` remains in place for existing scheduling and historical display.
3. `SalonMembership` is now the source of truth for per-salon collaboration status.
4. `Stylist.is_active` is not toggled by a salon manager anymore, because one stylist can work in multiple salons.
5. Pausing a team member changes `SalonMembership.status`, not the global stylist account.
6. Existing team UI is preserved; it now derives member status from `SalonMembership` where available.

## Data migration

Migration `apps/salons/migrations/0011_membership_verification_access.py` creates memberships from:

- existing `Salon.stylists`
- existing `JobDetails`

It also creates a `SalonVerification` row for each salon.

A manual re-sync command is available:

```bash
python manage.py sync_salon_memberships
```

## Dashboard changes

- `AddStylistView` can now attach an existing user by mobile number instead of rejecting duplicate mobile numbers.
- `toggle_stylist_status` now changes membership status for that salon only.
- A backend endpoint is available to set active stylist salon context:

```text
POST /dashboards/stylist/set-active-salon/
```

No Tailwind, template, global CSS or brand layout was changed in this phase.

## Commands to run locally

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py sync_salon_memberships
python manage.py check
```

## Manual QA

1. Existing salon team members still appear in the team page.
2. Adding a new stylist creates user + stylist + membership + permissions.
3. Adding an existing mobile attaches that account instead of creating a duplicate.
4. Toggling a stylist changes status only in that salon.
5. Stylist dashboard still opens for existing stylists.
6. Salon verification records exist for existing salons.
