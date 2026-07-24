from __future__ import annotations

import logging
import os

from celery import Celery

logger = logging.getLogger(__name__)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "loomera.settings.base")

app = Celery("loomera")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    logger.debug(
        "Celery debug task received | task_id=%s",
        getattr(self.request, "id", None),
    )
