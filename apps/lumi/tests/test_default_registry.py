from __future__ import annotations

import unittest
from types import SimpleNamespace

from apps.lumi.context import build_lumi_context
from apps.lumi.tools import build_default_registry


class FakeDomain:
    pass


class Guest:
    is_authenticated = False


class Customer:
    is_authenticated = True
    pk = 11
    is_admin = False
    is_superuser = False
    customer_profile = SimpleNamespace(pk=1)


class DefaultRegistryTests(unittest.TestCase):
    def test_guest_gets_only_public_beta_tools(self):
        registry = build_default_registry(domain=FakeDomain())
        names = {item["name"] for item in registry.list_for_context(build_lumi_context(user=Guest()))}
        self.assertEqual(
            names,
            {
                "get_services",
                "get_service_price",
                "get_contact",
                "get_availability",
                "search_booking_options",
            },
        )

    def test_customer_can_prepare_but_no_execute_tool_exists(self):
        registry = build_default_registry(domain=FakeDomain())
        names = {item["name"] for item in registry.list_for_context(build_lumi_context(user=Customer()))}
        self.assertIn("get_my_profile", names)
        self.assertIn("prepare_booking", names)
        self.assertNotIn("confirm_booking", names)
        self.assertNotIn("cancel_booking", names)
        self.assertNotIn("request_refund", names)


if __name__ == "__main__":
    unittest.main()
