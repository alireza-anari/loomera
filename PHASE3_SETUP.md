# Loomera Help Center — Phase 3

Phase 3 changes page detection from URL-only matching to **exact Django route names first**.
The FAB now sends both the current path and values such as:

```text
route=dashboards:team_member
route=orders:checkout
route=payments:detail
```

This package also seeds page-specific guides for public/customer/manager/stylist flows and adds a route coverage audit.

## Upgrade commands

```powershell
python manage.py migrate help_center
python manage.py seed_help_center
python manage.py check
python manage.py audit_help_coverage
```

The normal seed preserves text changed later in Django Admin.
Only use this when you intentionally want code defaults to overwrite seeded content:

```powershell
python manage.py seed_help_center --refresh-defaults
```

## QA

Open the assistant on at least these pages and check that the title changes specifically:

```text
Manager:
Dashboard → Team → Add stylist → Service menu → Schedule → Calendar → Finance

Stylist:
Dashboard → Appointments → Appointment detail → Schedule → Finance

Customer:
Account → Addresses → Communications → Appointments → Wallet

Public:
Search → Salon detail → Stylist profile → Service detail → Magazine

Help:
/help/ → /help/search/ → /help/legal/
```

## Future route additions

After adding any new UI page run:

```powershell
python manage.py audit_help_coverage
```

The command reports exact declared routes missing from the DB and a heuristic list of probable user-facing routes that still lack a guide.
