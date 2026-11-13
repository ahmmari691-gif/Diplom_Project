#!/bin/sh
set -eu
python manage.py check --deploy --fail-level WARNING
python manage.py migrate --noinput
if [ "${DELO_STUDY_MODE:-0}" = "1" ]; then
    python manage.py ensure_study_accounts
fi
python manage.py collectstatic --noinput
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-10000}" --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile -
