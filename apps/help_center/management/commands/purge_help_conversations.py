from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.help_center.models import HelpConversation


class Command(BaseCommand):
    help = "Delete old Help Assistant conversations according to the configured retention period."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=None)

    def handle(self, *args, **options):
        days = options["days"]
        if days is None:
            days = int(getattr(settings, "HELP_CONVERSATION_RETENTION_DAYS", 30) or 30)
        days = max(days, 1)
        cutoff = timezone.now() - timedelta(days=days)

        qs = HelpConversation.objects.filter(created_at__lt=cutoff)
        count = qs.count()
        qs.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {count} help conversations older than {days} days."
            )
        )
