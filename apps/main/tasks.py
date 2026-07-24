from __future__ import annotations

try:
    from celery import shared_task
except Exception:  # pragma: no cover - celery is optional in local/dev
    def shared_task(*dargs, **dkwargs):
        def decorator(func):
            return func
        return decorator


@shared_task(ignore_result=True)
def run_scheduled_tasks_task(daily_metrics=True, dry_run=False, limit=100):
    from .infrastructure import run_scheduled_tasks
    run_scheduled_tasks(daily_metrics=daily_metrics, dry_run=dry_run, limit=limit)


@shared_task(ignore_result=True)
def process_media_jobs_task(limit=25):
    from .media_processing import process_pending_media_jobs
    process_pending_media_jobs(limit=limit)


@shared_task(ignore_result=True)
def cleanup_operational_data_task(dry_run=True):
    from django.core.management import call_command
    call_command("cleanup_operational_data", dry_run=dry_run)
