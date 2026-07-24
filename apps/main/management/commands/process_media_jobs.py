from django.core.management.base import BaseCommand
from apps.main.media_processing import process_pending_media_jobs


class Command(BaseCommand):
    help = "Process pending image/media optimization jobs."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)

    def handle(self, *args, **options):
        jobs = process_pending_media_jobs(limit=options["limit"])
        completed = sum(1 for job in jobs if job.status == "completed")
        failed = sum(1 for job in jobs if job.status == "failed")
        skipped = sum(1 for job in jobs if job.status == "skipped")
        self.stdout.write(self.style.SUCCESS(f"Processed {len(jobs)} media jobs. completed={completed} failed={failed} skipped={skipped}"))
