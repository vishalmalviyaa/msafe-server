import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vishkey_backend.settings")

app = Celery("vishkey_backend")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
