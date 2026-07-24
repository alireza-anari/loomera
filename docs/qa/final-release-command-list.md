# Final Release Command List

## Install

```bash
pip install -r requirements.txt
npm install
npm run build
```

## Database

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py check
```

## Data sync commands

```bash
python manage.py sync_salon_memberships
python manage.py sync_financial_ledger --dry-run
python manage.py sync_legacy_notifications --dry-run
python manage.py sync_support_threads --dry-run
python manage.py sync_discount_records --dry-run
```

## Operational checks

```bash
python manage.py infrastructure_preflight_check
python manage.py pre_beta_check
python manage.py release_readiness_check --run-tests --skip-operational-dry-runs
```

## Scheduled jobs dry-run

```bash
python manage.py run_scheduled_tasks --dry-run
python manage.py confirm_no_show_after_window --dry-run
python manage.py expire_salon_stories --dry-run
python manage.py process_report_exports --limit 10
python manage.py process_media_jobs --limit 10
```
