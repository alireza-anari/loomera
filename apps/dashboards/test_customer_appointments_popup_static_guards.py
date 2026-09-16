from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]


class CustomerAppointmentsPopupStaticGuards(SimpleTestCase):
    def test_customer_card_supplies_popup_url_and_template_uses_it(self):
        views = (ROOT / "apps/dashboards/views.py").read_text(encoding="utf-8")
        partial = (
            ROOT / "templates/dashboards/partials/salons_customers.html"
        ).read_text(encoding="utf-8")

        self.assertIn('"appointments_popup_url": detail_url', views)
        self.assertIn("data-customer-appointments-trigger", partial)
        self.assertIn(
            'data-customer-appointments-url="{{ customer.appointments_popup_url }}"',
            partial,
        )

    def test_customer_detail_ajax_returns_serialized_appointments(self):
        views = (ROOT / "apps/dashboards/views.py").read_text(encoding="utf-8")

        self.assertIn(
            'request.headers.get("x-requested-with") == "XMLHttpRequest"', views
        )
        self.assertIn('"appointments": [', views)
        self.assertIn("self._serialize_appointment(item, salon)", views)
        self.assertIn('json_dumps_params={"ensure_ascii": False}', views)

    def test_customer_list_keeps_modal_and_click_handler(self):
        template = (
            ROOT / "templates/dashboards/salonsCustomersPage.html"
        ).read_text(encoding="utf-8")

        self.assertIn("data-customer-appointments-modal", template)
        self.assertIn("openAppointmentsModal(button)", template)
        self.assertIn("fetch(url", template)
