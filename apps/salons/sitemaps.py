from django.contrib.sitemaps import Sitemap

from .models import Salon


class SalonSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.85

    def items(self):
        return Salon.objects.filter(is_active=True, allow_indexing=True).exclude(slug="")

    def lastmod(self, obj):
        return obj.registere_date
