from __future__ import annotations

import unittest
from types import SimpleNamespace

from apps.lumi.context import build_lumi_context
from apps.lumi.policy import ToolPolicy
from apps.lumi.tools.base import ToolRegistry, ToolSpec


class FakeDomain:
    def ping(self, value):
        return {"value": value}

    def get_my_profile(self, *, context):
        return {"name": "Test", "role": context.primary_role, "phone_verified": True, "preferences": {}}


class FakeUser:
    def __init__(self, *, authenticated=True, pk=7, customer=False, manager=False):
        self.is_authenticated = authenticated
        self.pk = pk
        self.is_admin = False
        self.is_superuser = False
        if customer:
            self.customer_profile = SimpleNamespace(pk=1)
        if manager:
            self.salon_manager_profile = SimpleNamespace(pk=2)


class LumiContextTests(unittest.TestCase):
    def test_guest_context_exposes_no_actor(self):
        ctx = build_lumi_context(user=FakeUser(authenticated=False))
        self.assertEqual(ctx.roles, frozenset({"guest"}))
        self.assertIsNone(ctx.user_id)
        self.assertNotIn("actor", ctx.public_dict())
        self.assertNotIn("request", ctx.public_dict())

    def test_customer_role_is_detected(self):
        ctx = build_lumi_context(user=FakeUser(customer=True))
        self.assertTrue(ctx.authenticated)
        self.assertIn("customer", ctx.roles)
        self.assertEqual(ctx.primary_role, "customer")


class ToolRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry(domain=FakeDomain())
        self.registry.register(
            ToolSpec(
                name="echo",
                description="test",
                handler=lambda ctx, args, domain: domain.ping(args["value"]),
                policy=ToolPolicy.read_public(),
                input_schema={"type": "object", "required": ["value"]},
            )
        )

    def test_public_read_tool_executes(self):
        ctx = build_lumi_context(user=FakeUser(authenticated=False))
        result = self.registry.execute(name="echo", context=ctx, arguments={"value": "ok"})
        self.assertTrue(result.ok)
        self.assertEqual(result.data, {"value": "ok"})

    def test_missing_required_argument_is_normalized(self):
        ctx = build_lumi_context(user=FakeUser(authenticated=False))
        result = self.registry.execute(name="echo", context=ctx, arguments={})
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_arguments")

    def test_policy_denies_guest_before_handler(self):
        called = {"value": False}

        def handler(ctx, args, domain):
            called["value"] = True
            return {"unsafe": True}

        registry = ToolRegistry(domain=FakeDomain())
        registry.register(
            ToolSpec(
                name="customer_only",
                description="test",
                handler=handler,
                policy=ToolPolicy(
                    allowed_roles=frozenset({"customer"}),
                    requires_auth=True,
                ),
            )
        )
        ctx = build_lumi_context(user=FakeUser(authenticated=False))
        result = registry.execute(name="customer_only", context=ctx)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "authentication_required")
        self.assertFalse(called["value"])


    def test_unknown_tool_is_normalized(self):
        ctx = build_lumi_context(user=FakeUser(authenticated=False))
        result = self.registry.execute(name="hallucinated_tool", context=ctx)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "unknown_tool")

    def test_wrong_argument_type_is_rejected(self):
        registry = ToolRegistry(domain=FakeDomain())
        registry.register(
            ToolSpec(
                name="typed",
                description="test",
                handler=lambda ctx, args, domain: {"ok": True},
                policy=ToolPolicy.read_public(),
                input_schema={"type": "object", "properties": {"count": {"type": "integer"}}},
            )
        )
        ctx = build_lumi_context(user=FakeUser(authenticated=False))
        result = registry.execute(name="typed", context=ctx, arguments={"count": "3"})
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_arguments")

    def test_confirmation_is_backend_enforced(self):
        registry = ToolRegistry(domain=FakeDomain())
        registry.register(
            ToolSpec(
                name="dangerous",
                description="test",
                handler=lambda ctx, args, domain: {"done": True},
                policy=ToolPolicy(
                    allowed_roles=frozenset({"customer"}),
                    requires_auth=True,
                    requires_confirmation=True,
                    mutates_state=True,
                    writes_database=True,
                ),
            )
        )
        ctx = build_lumi_context(user=FakeUser(customer=True))
        denied = registry.execute(name="dangerous", context=ctx)
        allowed = registry.execute(name="dangerous", context=ctx, confirmed=True)
        self.assertEqual(denied.error_code, "confirmation_required")
        self.assertTrue(allowed.ok)


if __name__ == "__main__":
    unittest.main()
