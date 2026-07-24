from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Stylist
from apps.dashboards.views import AddServicesView
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ServiceSetupHandoffUxTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(manager=self.manager)
        self.client.force_login(self.manager.user)

    def _get_service_menu(self, params=None):
        with patch(
            "apps.dashboards.views._redirect_to_required_onboarding",
            return_value=None,
        ):
            return self.client.get(
                reverse("dashboards:service_menu"),
                params or {},
            )

    def test_new_service_without_team_shows_assign_stylist_handoff(self):
        service = self.make_service(name="رنگ مو")
        self.salon.services.add(service)

        response = self._get_service_menu({"created_service": str(service.pk)})

        self.assertEqual(response.status_code, 200)

        handoff = response.context["service_setup_handoff"]
        self.assertIsNotNone(handoff)
        self.assertEqual(handoff["service_name"], "رنگ مو")
        self.assertEqual(
            handoff["primary_url"],
            reverse(
                "dashboards:edit_service",
                kwargs={"service_id": service.pk},
            ),
        )
        self.assertContains(response, "اتصال متخصص به خدمت")
        self.assertContains(response, "data-service-setup-handoff")

    def test_new_service_with_public_active_stylist_shows_schedule_handoff(self):
        service = self.make_service(name="اصلاح صورت")
        stylist = self.make_stylist(
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )
        self.connect_service(
            salon=self.salon,
            stylist=stylist,
            service=service,
        )

        response = self._get_service_menu({"created_service": str(service.pk)})

        self.assertEqual(response.status_code, 200)

        handoff = response.context["service_setup_handoff"]
        self.assertEqual(
            handoff["primary_url"],
            reverse("dashboards:scheduled_shifts"),
        )
        self.assertEqual(handoff["status_tone"], "success")
        self.assertContains(response, "تنظیم برنامه کاری")

    def test_hidden_stylist_does_not_count_as_public_service_coverage(self):
        service = self.make_service(name="فیشال")
        stylist = self.make_stylist(
            public_visibility=Stylist.PublicVisibility.HIDDEN,
        )
        self.connect_service(
            salon=self.salon,
            stylist=stylist,
            service=service,
        )

        response = self._get_service_menu({"created_service": str(service.pk)})

        handoff = response.context["service_setup_handoff"]
        self.assertEqual(handoff["status_tone"], "warning")
        self.assertContains(response, "بدون پوشش تیم")

    def test_foreign_salon_service_is_not_exposed_in_handoff(self):
        other_manager = self.make_salon_manager()
        other_salon = self.make_salon(manager=other_manager)
        foreign_service = self.make_service(name="خدمت محرمانه سالن دیگر")
        other_salon.services.add(foreign_service)

        response = self._get_service_menu({"created_service": str(foreign_service.pk)})

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["service_setup_handoff"])
        self.assertNotContains(response, "خدمت محرمانه سالن دیگر")

    def test_invalid_created_service_value_is_ignored(self):
        response = self._get_service_menu({"created_service": "not-a-number"})

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["service_setup_handoff"])
        self.assertNotContains(response, "data-service-setup-handoff")

    def test_add_service_success_redirects_to_scoped_handoff(self):
        service = self.make_service(name="مانیکور")
        self.salon.services.add(service)

        class FakeValidServiceForm:
            def __init__(self, *args, **kwargs):
                pass

            def is_valid(self):
                return True

            def save(self, *, commit, salon):
                return service

        with (
            patch(
                "apps.dashboards.views._redirect_to_required_onboarding",
                return_value=None,
            ),
            patch.object(
                AddServicesView,
                "form_class",
                FakeValidServiceForm,
            ),
        ):
            response = self.client.post(
                reverse("dashboards:add_service"),
                data={},
            )

        expected_url = (
            f"{reverse('dashboards:service_menu')}" f"?created_service={service.pk}"
        )
        self.assertRedirects(
            response,
            expected_url,
            fetch_redirect_response=False,
        )
