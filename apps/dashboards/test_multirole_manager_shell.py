"""Regression coverage for the scoped multi-salon manager shared shell."""

from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import SalonManager, Stylist
from apps.dashboards.layout import build_dashboard_context
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ScopedMultiroleManagerShellTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.user = self.make_user()
        self.manager = SalonManager.objects.create(user=self.user)
        # Include another professional capability so the navbar workspace menu
        # exercises the same multi-role shape that exposed QA-BUG-001.
        Stylist.objects.create(user=self.user)
        self.salon_a = self.make_salon(manager=self.manager)
        self.salon_b = self.make_salon(manager=self.manager)

    def _overview_url(self, salon):
        return reverse(
            "dashboards:multirole_manager_salon_overview",
            kwargs={"salon_id": salon.pk},
        )

    def test_scoped_shell_uses_explicit_url_salon_not_first_owned_salon(self):
        path = self._overview_url(self.salon_b)
        context = build_dashboard_context(self.user, request_path=path)

        self.assertTrue(context["dashboard_is_scoped_manager_shell"])
        self.assertEqual(context["salon"].pk, self.salon_b.pk)
        self.assertEqual(context["dashboard_workspace_active"]["salon_id"], self.salon_b.pk)

        sidebar = {
            item["key"]: item for item in context["dashboard_sidebar_items"]
        }
        self.assertEqual(
            sidebar["services"]["url"],
            reverse(
                "dashboards:multirole_manager_salon_services",
                kwargs={"salon_id": self.salon_b.pk},
            ),
        )
        self.assertEqual(
            sidebar["clients"]["url"],
            reverse(
                "dashboards:multirole_manager_salon_customers",
                kwargs={"salon_id": self.salon_b.pk},
            ),
        )
        # Legacy single-salon settings/report/profile destinations stay fail-closed.
        self.assertFalse(sidebar["settings"]["is_available"])
        self.assertEqual(sidebar["settings"]["url"], "#")
        self.assertFalse(sidebar["reports"]["is_available"])
        self.assertEqual(sidebar["reports"]["url"], "#")

    def test_scoped_service_path_marks_services_active_and_scopes_actions(self):
        path = reverse(
            "dashboards:multirole_manager_service_add",
            kwargs={"salon_id": self.salon_b.pk},
        )
        context = build_dashboard_context(self.user, request_path=path)

        self.assertEqual(context["salon"].pk, self.salon_b.pk)
        self.assertEqual(context["dashboard_active_key"], "services")
        self.assertEqual(
            context["dashboard_create_actions"][0]["url"],
            path,
        )
        self.assertTrue(all(
            action["url"] != reverse("dashboards:salon_manager_dashboard")
            for action in context["dashboard_create_actions"]
        ))

    def test_overview_renders_shared_dashboard_and_inline_workspace_switcher(self):
        self.client.force_login(self.user)
        response = self.client.get(self._overview_url(self.salon_b))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-dashboard-root")
        self.assertContains(response, "data-dashboard-workspace-switch")
        self.assertContains(response, "data-multirole-salon-overview")
        self.assertContains(response, self.salon_b.salon_name)
        # The other owned salon is an explicit POST option in the inline switcher.
        self.assertContains(
            response,
            f'name="salon_id" value="{self.salon_a.pk}"',
        )
        self.assertNotContains(response, ">تغییر محیط فعالیت</a>")

    def test_all_scoped_manager_templates_extend_shared_dashboard_shell(self):
        template_dir = Path(settings.BASE_DIR) / "templates" / "dashboards"
        names = [
            "multirole_manager_salon_overview.html",
            "multirole_manager_services.html",
            "multirole_manager_service_form.html",
            "multirole_manager_team.html",
            "multirole_manager_team_member_form.html",
            "multirole_manager_bookings.html",
            "multirole_manager_manual_booking.html",
            "multirole_manager_manual_booking_cancel.html",
            "multirole_manager_customers.html",
            "multirole_manager_finance_preview.html",
            "multirole_manager_settlement_ledger.html",
        ]
        for name in names:
            source = (template_dir / name).read_text(encoding="utf-8-sig")
            first_tag = next(line.strip() for line in source.splitlines() if line.strip())
            self.assertEqual(first_tag, '{% extends "dashboard_template.html" %}', name)
            self.assertNotIn("accounts:workspace_choose", source, name)
            self.assertNotIn("<!doctype html>", source.lower(), name)

        dashboard_base = (
            Path(settings.BASE_DIR) / "templates" / "dashboard_template.html"
        ).read_text(encoding="utf-8-sig")
        self.assertIn('dashboards/partials/dashboard_help_fab.html', dashboard_base)
        self.assertIn("dashboard_navbar", dashboard_base)
        self.assertIn("dashboard_sidebar", dashboard_base)
