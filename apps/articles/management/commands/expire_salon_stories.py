from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.articles.models import SalonStory
from apps.articles.services import create_moderation_event


class Command(BaseCommand):
    help = "Expire published salon stories whose expires_at has passed."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only show how many stories would expire.")
        parser.add_argument("--limit", type=int, default=500, help="Maximum stories to process.")

    def handle(self, *args, **options):
        now = timezone.now()
        queryset = SalonStory.objects.filter(
            status=SalonStory.Status.PUBLISHED,
            expires_at__isnull=False,
            expires_at__lt=now,
        ).order_by("expires_at")[: options["limit"]]
        stories = list(queryset)
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(f"{len(stories)} stories would expire."))
            return
        for story in stories:
            old_status = story.status
            story.status = SalonStory.Status.EXPIRED
            story.save(update_fields=["status", "updated_at"])
            create_moderation_event(
                story,
                "story_expired",
                old_status=old_status,
                new_status=story.status,
                note="استوری به‌صورت خودکار منقضی شد.",
            )
        self.stdout.write(self.style.SUCCESS(f"Expired {len(stories)} stories."))
