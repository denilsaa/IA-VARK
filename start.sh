#!/usr/bin/env bash
set -o errexit

python manage.py migrate --noinput
python manage.py cargar_dataset_anatomia
python manage.py collectstatic --noinput

gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers ${WEB_CONCURRENCY:-2} --timeout ${GUNICORN_TIMEOUT:-180}
