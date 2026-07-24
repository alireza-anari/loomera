from django.core.management.base import BaseCommand

from apps.articles.models import Article, SalonStory, SalonStoryItem
from apps.articles.services import strip_internal_content_notes


class Command(BaseCommand):
    help = "Remove internal dashboard review notes from published article/story public fields."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only show what would be changed.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        changed_articles = 0
        changed_stories = 0
        changed_items = 0

        for article in Article.objects.all().only("id", "summary", "content"):
            clean_summary = strip_internal_content_notes(article.summary)
            clean_content = strip_internal_content_notes(article.content)
            if clean_summary != (article.summary or "") or clean_content != (article.content or ""):
                changed_articles += 1
                self.stdout.write(f"ARTICLE #{article.id}: would clean internal notes")
                if not dry_run:
                    article.summary = clean_summary
                    article.content = clean_content
                    article.save(update_fields=["summary", "content", "updated_at"])

        for story in SalonStory.objects.all().only("id", "summary"):
            clean_summary = strip_internal_content_notes(story.summary)
            if clean_summary != (story.summary or ""):
                changed_stories += 1
                self.stdout.write(f"STORY #{story.id}: would clean internal notes")
                if not dry_run:
                    story.summary = clean_summary
                    story.save(update_fields=["summary", "updated_at"])

        for item in SalonStoryItem.objects.all().only("id", "caption"):
            clean_caption = strip_internal_content_notes(item.caption)
            if clean_caption != (item.caption or ""):
                changed_items += 1
                self.stdout.write(f"STORY ITEM #{item.id}: would clean internal notes")
                if not dry_run:
                    item.caption = clean_caption
                    item.save(update_fields=["caption", "updated_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"clean_public_content_notes completed: articles={changed_articles}, stories={changed_stories}, items={changed_items}, dry_run={dry_run}"
            )
        )
