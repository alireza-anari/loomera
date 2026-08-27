from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.help_center.models import HelpArticle, HelpArticleChunk, HelpCategory, HelpPageContext


class Command(BaseCommand):
    help = (
        "Disable Phase 1-3 prototype Help Center content before seeding the docs-first set. "
        "Conversations, messages, feedback and legal documents are preserved."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required safety flag.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["confirm"]:
            raise CommandError(
                "Nothing changed. Re-run with --confirm only when you intentionally want "
                "to disable the old prototype docs."
            )

        contexts, _ = HelpPageContext.objects.all().delete()
        chunks, _ = HelpArticleChunk.objects.all().delete()
        articles = HelpArticle.objects.filter(is_published=True).update(
            is_published=False,
            is_featured=False,
        )
        categories = HelpCategory.objects.filter(is_published=True).update(is_published=False)

        self.stdout.write(
            self.style.SUCCESS(
                "Prototype reset complete: "
                f"{contexts} context rows removed, {chunks} chunk rows removed, "
                f"{articles} articles unpublished, {categories} categories unpublished. "
                "Conversations/messages/feedback/legal docs were preserved."
            )
        )
