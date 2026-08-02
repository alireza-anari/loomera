from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.services.models import Services


class ServicesCatalogAdminTests(TestCase):
    def test_stylists_field_is_optional_in_services_admin(self):
        request = RequestFactory().get("/admin/services/services/add/")
        request.user = AnonymousUser()

        model_admin = admin.site._registry[Services]
        form_class = model_admin.get_form(request)

        self.assertIn("stylists", form_class.base_fields)
        self.assertFalse(form_class.base_fields["stylists"].required)
