#!/usr/bin/env bash
set -e

echo "Running Loomera pre-start checks..."

python manage.py check --deploy
python manage.py infrastructure_preflight_check
python manage.py pre_beta_check

echo "Running migrations..."
python manage.py migrate --noinput

echo "Loomera pre-start finished."
