from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.help_center.actions.customer_operations import is_customer_current_appointment_candidate


class LumiCustomerCurrentAppointmentTests(SimpleTestCase):
    @patch("apps.help_center.actions.customer_operations.resolve_current_path")
    def test_cancel_requires_real_current_appointment_route(self, resolver):
        resolver.return_value = SimpleNamespace(view_name="orders:appointment_detail", kwargs={"pk": 22})
        self.assertTrue(
            is_customer_current_appointment_candidate(
                "این نوبت رو لغو کن",
                current_path="/orders/appointment_detail/22/",
                has_customer_role=True,
            )
        )

    @patch("apps.help_center.actions.customer_operations.resolve_current_path")
    def test_never_treats_id_in_text_as_current_entity(self, resolver):
        resolver.return_value = SimpleNamespace(view_name="main:home", kwargs={})
        self.assertFalse(
            is_customer_current_appointment_candidate(
                "نوبت 22 رو لغو کن",
                current_path="/",
                has_customer_role=True,
            )
        )
