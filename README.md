# Loomera

Loomera is a Django application for salon/service discovery, booking, customer and partner operations, notifications, reviews, and Loomi messaging integrations.

## Project entry points

- Django entry point: `manage.py`
- Runtime dependencies: `requirements.txt`
- Development/test dependencies: `requirements-dev.txt`
- QA command list: `docs/qa/final-release-command-list.md`
- Release readiness checklist: `docs/qa/release-readiness-checklist.md`
- Manual E2E checklist: `docs/qa/manual-e2e-checklist.md`

## Local validation

After installing the appropriate dependencies and environment variables, run:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

For the current beta, customer checkout is **Pay at Salon only**. Wallet, online payment, prepayment, recharge, and withdrawal are not active customer booking capabilities.
