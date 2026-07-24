from django.contrib.sitemaps import Sitemap

from .models import Article, ArticleCategory, ArticleTag


class ArticleSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Article.objects.published().filter(
            allow_indexing=True,
            visibility=Article.Visibility.PUBLIC,
        )

    def lastmod(self, obj):
        return obj.updated_at


class ArticleCategorySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return ArticleCategory.objects.filter(is_active=True)

    def lastmod(self, obj):
        return obj.updated_at


class ArticleTagSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.4

    def items(self):
        return ArticleTag.objects.filter(
            is_active=True,
            articles__status=Article.Status.PUBLISHED,
        ).distinct()

    def lastmod(self, obj):
        return obj.updated_at
