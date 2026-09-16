from django.db.models.signals import post_save
from django.dispatch import receiver

from .chunking import rebuild_article_chunks
from .models import HelpArticle


@receiver(post_save, sender=HelpArticle)
def rebuild_help_article_chunks(sender, instance, **kwargs):
    rebuild_article_chunks(instance)
