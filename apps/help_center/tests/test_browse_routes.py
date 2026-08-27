from django.test import SimpleTestCase
from django.urls import reverse

class HelpBrowseRouteTests(SimpleTestCase):
    def test_category_route(self):
        self.assertEqual(reverse("help_center:category", kwargs={"slug":"booking"}), "/help/category/booking/")
    def test_search_route(self):
        self.assertEqual(reverse("help_center:search"), "/help/search/")
