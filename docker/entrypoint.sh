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
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -