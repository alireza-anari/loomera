"""Navigation and UI contracts for the multirole workspace switcher."""

from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import SalonManager, Stylist
from tests_stage1_helpers import Stage1DomainFactoryMixin


class MultiroleNavigationTests(Stage1DomainFactoryMixin, TestCase):
    def test_customer_can_find_role_attachment_without_duplicate_workspace_card(self):
        user = self.make_user()
        self.client.force_login(user)
        stylist_url = reverse("accounts:add_role", kwargs={"kind": "stylist"})
        manager_url = reverse("accounts:add_role", kwargs={"kind": "manager"})

        panel = self.client.get(reverse("accounts:customer_panel"))
        self.assertEqual(panel.status_code, 200)
        self.assertContains(panel, "data-multirole-account-actions")
        self.assertContains(panel, f'href="{stylist_url}"')
        self.assertContains(panel, f'href="{manager_url}"')
        self.assertNotContains(panel, "محیط‌های فعالیت من")
        self.assertNotContains(panel, "تغییر محیط فعالیت")

    def test_existing_provider_roles_use_inline_shell_switcher(self):
        user = self.make_user()
        SalonManager.objects.create(user=user)
        Stylist.objects.create(user=user)
        self.client.force_login(user)

        panel = self.client.get(reverse("accounts:customer_panel"))
        self.assertEqual(panel.status_code, 200)
        self.assertNotContains(panel, 'href="%s"' % reverse(
            "accounts:add_role", kwargs={"kind": "stylist"}
        ))
        self.assertNotContains(panel, 'href="%s"' % reverse(
            "accounts:add_role", kwargs={"kind": "manager"}
        ))
        self.assertContains(panel, "data-shell-workspace-switch", count=2)
        self.assertContains(panel, "data-multirole-workspace-entry", count=2)
        # The current customer workspace is rendered as an active, non-submit option
        # in both desktop and mobile switchers. Only alternate workspaces are POST forms.
        self.assertContains(panel, "data-workspace-active", count=2)
        self.assertNotContains(panel, 'name="kind" value="customer"')
        self.assertContains(panel, 'name="kind" value="stylist"', count=2)
        self.assertContains(panel, reverse("accounts:workspace_choose"))

    def test_two_salon_manager_shell_switcher_scopes_each_manager_option(self):
        user = self.make_user()
        manager = SalonManager.objects.create(user=user)
        salon_a = self.make_salon(manager=manager)
        salon_b = self.make_salon(manager=manager)
        self.client.force_login(user)

        panel = self.client.get(reverse("accounts:customer_panel"))
        self.assertEqual(panel.status_code, 200)
        self.assertContains(panel, "data-multirole-workspace-entry", count=2)
        # Desktop and mobile switchers each render an explicit scoped salon id.
        self.assertContains(panel, f'name="salon_id" value="{salon_a.pk}"', count=2)
        self.assertContains(panel, f'name="salon_id" value="{salon_b.pk}"', count=2)
        self.assertContains(panel, salon_a.salon_name, count=2)
        self.assertContains(panel, salon_b.salon_name, count=2)
        # Never send a multi-salon manager to the ambiguous guarded legacy route.
        self.assertNotContains(
            panel, f'href="{reverse("dashboards:salon_manager_dashboard")}"'
        )

    def test_chooser_remains_login_protected_fallback_and_does_not_create_role_on_get(self):
        chooser_url = reverse("accounts:workspace_choose")
        self.assertEqual(self.client.get(chooser_url).status_code, 302)
        user = self.make_user()
        self.client.force_login(user)
        response = self.client.get(chooser_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-multirole-workspace-chooser")
        self.assertContains(response, "data-workspace-card")
        self.assertContains(response, 'data-workspace-kind="customer"')
        self.assertContains(response, "css/pages/workspace_choose.css")
        self.assertFalse(SalonManager.objects.filter(user=user).exists())
        self.assertFalse(Stylist.objects.filter(user=user).exists())

    def test_dashboard_has_one_compact_inline_workspace_switcher(self):
        navbar = (
            Path(settings.BASE_DIR)
            / "templates" / "partials" / "dashboard" / "navbar.html"
        ).read_text(encoding="utf-8")
        sidebar = (
            Path(settings.BASE_DIR)
            / "templates" / "partials" / "dashboard" / "sidebar.html"
        ).read_text(encoding="utf-8")
        css = (
            Path(settings.BASE_DIR)
            / "static" / "css" / "components" / "workspace_switcher.css"
        ).read_text(encoding="utf-8")

        self.assertIn("data-dashboard-workspace-switch", navbar)
        self.assertIn("data-workspace-option-form", navbar)
        self.assertIn("lm-workspace-switch__menu", navbar)
        self.assertIn("accounts:workspace_choose", navbar)
        self.assertIn("width: 20.5rem", css)
        self.assertIn("background: transparent !important", css)
        self.assertNotIn("data-multirole-workspace-entry", sidebar)
        self.assertNotIn("تغییر محیط فعالیت", sidebar)

    def test_workspace_switcher_styles_are_loaded_in_both_shells(self):
        base = (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(
            encoding="utf-8"
        )
        dashboard = (
            Path(settings.BASE_DIR) / "templates" / "dashboard_template.html"
        ).read_text(encoding="utf-8")
        asset = "css/components/workspace_switcher.css"
        self.assertIn(asset, base)
        self.assertIn(asset, dashboard)
