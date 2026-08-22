#!/usr/bin/env bash
set -e

echo "Running Loomera pre-start checks..."

python manage.py check --deploy
python manage.py infrastructure_preflight_check
python manage.py pre_beta_check

echo "========================================"
echo "Migration plan..."
echo "========================================"

PYTHONUNBUFFERED=1 python manage.py migrate --plan --verbosity 2

echo "========================================"
echo "Running migrations..."
echo "========================================"

PYTHONUNBUFFERED=1 python manage.py migrate --noinput --verbosity 3

echo "========================================"
echo "Loomera pre-start finished."
echo "========================================"
