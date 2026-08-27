from django.core.management.base import BaseCommand

from apps.help_center.chunking import rebuild_article_chunks
from apps.help_center.models import HelpArticle


class Command(BaseCommand):
    help = "Rebuild searchable RAG chunks for all published Help Center articles."

    def handle(self, *args, **options):
        articles = HelpArticle.objects.filter(is_published=True).order_by("id")
        article_count = 0
        chunk_count = 0
        for article in articles.iterator():
            chunks = rebuild_article_chunks(article)
            article_count += 1
            chunk_count += int(chunks)
        self.stdout.write(
            self.style.SUCCESS(
                f"Help chunk rebuild complete: {article_count} articles, {chunk_count} chunks."
            )
        )
