from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.5

    def items(self):
        return ["salons:home", "salons:show_salons", "articles:magazine_home", "services:all_services"]

    def location(self, item):
        return reverse(item)
