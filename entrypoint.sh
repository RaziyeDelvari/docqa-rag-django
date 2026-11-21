#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# create the admin user if credentials are set (the error is ignored if it already exists)
if [ -n "$DJANGO_SUPERUSER_USERNAME" ]; then
  python manage.py createsuperuser --noinput || true
fi

if [ "$LOAD_SAMPLE_DATA" = "1" ]; then
  python manage.py load_sample_data || true
fi

exec gunicorn -c gunicorn.conf.py config.wsgi:application
