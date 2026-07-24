from django.contrib.sitemaps import Sitemap

from .models import GroupServices, Services


class ServiceSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Services.objects.filter(is_active=True, allow_indexing=True).exclude(slug="")

    def lastmod(self, obj):
        return obj.updated_date


class ServiceGroupSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.65

    def items(self):
        return GroupServices.objects.filter(is_active=True, allow_indexing=True).exclude(slug="")

    def lastmod(self, obj):
        return obj.updated_date
