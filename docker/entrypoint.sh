#!/bin/sh
set -e

echo "Applying migrations..."
python manage.py migrate --noinput

echo "Preparing cache table..."
python manage.py createcachetable

echo "Refreshing groups and permissions..."
python manage.py setup_groups

echo "Starting Gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --worker-class gthread \
    --workers "${GUNICORN_WORKERS:-2}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -