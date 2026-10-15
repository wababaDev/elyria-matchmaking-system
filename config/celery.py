import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("elyria")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()  # finds tasks.py in every installed app