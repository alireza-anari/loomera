from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.dashboards.home_components import (
    _build_dashboard_setup_priority,
)
from tests_stage1_helpers import Stage1DomainFactoryMixin


class DashboardHomeSetupPriorityTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(manager=self.manager)
        self.client.force_login(self.manager.user)

    def _readiness(self, *, missing_items, percent=50, is_ready=False):
        return {
            "enabled": True,
            "is_ready": is_ready,
            "percent": percent,
            "percent_label": f"{percent}٪",
            "completed_count": 2,
            "total_count": 5,
            "missing_count": len(missing_items),
            "missing_items": missing_items,
            "items": missing_items,
            "summary": "چند مورد باقی مانده است.",
        }

    def _get_dashboard(self, readiness):
        with (
            patch(
                "apps.dashboards.views._redirect_to_required_onboarding",
                return_value=None,
            ),
            patch(
                "apps.dashboards.home_components.build_salon_readiness_checklist",
                return_value=readiness,
            ),
        ):
            return self.client.get(reverse("dashboards:salon_manager_dashboard"))

    def test_service_setup_is_prioritized_before_gallery(self):
        readiness = self._readiness(
            missing_items=[
                {
                    "key": "gallery",
                    "title": "گالری را کامل کن",
                    "description": "تصویر سالن لازم است.",
                    "action_label": "مدیریت گالری",
                    "action_url": "/gallery/",
                    "weight": 1,
                },
                {
                    "key": "services",
                    "title": "خدمات را کامل کن",
                    "description": "خدمت قابل رزرو لازم است.",
                    "action_label": "مدیریت خدمات",
                    "action_url": "/services/",
                    "weight": 2,
                },
            ]
        )

        priority = _build_dashboard_setup_priority(readiness)

        self.assertEqual(priority["key"], "services")
        self.assertEqual(priority["action_url"], "/services/")
        self.assertEqual(priority["remaining_after"], 1)

    def test_schedule_is_prioritized_before_public_activation(self):
        readiness = self._readiness(
            missing_items=[
                {
                    "key": "public_active",
                    "title": "فعال‌سازی عمومی",
                    "description": "سالن باید فعال شود.",
                    "action_label": "تنظیم رزرو",
                    "action_url": "/booking-settings/",
                    "weight": 2,
                },
                {
                    "key": "schedule",
                    "title": "برنامه کاری را ثبت کن",
                    "description": "شیفت آینده لازم است.",
                    "action_label": "تنظیم شیفت",
                    "action_url": "/shifts/",
                    "weight": 2,
                },
            ]
        )

        priority = _build_dashboard_setup_priority(readiness)

        self.assertEqual(priority["key"], "schedule")

    def test_ready_salon_has_no_priority_action(self):
        readiness = self._readiness(
            missing_items=[],
            percent=100,
            is_ready=True,
        )

        self.assertIsNone(_build_dashboard_setup_priority(readiness))

    def test_manager_dashboard_exposes_readiness_and_priority_card(self):
        readiness = self._readiness(
            missing_items=[
                {
                    "key": "bookable_path",
                    "title": "مسیر رزرو واقعی را کامل کن",
                    "description": ("یک متخصص دارای خدمت و برنامه کاری لازم است."),
                    "action_label": "بررسی تیم و شیفت‌ها",
                    "action_url": reverse("dashboards:scheduled_shifts"),
                    "weight": 3,
                }
            ],
            percent=82,
        )

        response = self._get_dashboard(readiness)

        self.assertEqual(response.status_code, 200)

        dashboard_home = response.context["dashboard_home"]
        self.assertEqual(
            dashboard_home["readiness"],
            readiness,
        )
        self.assertEqual(
            dashboard_home["setup_priority"]["key"],
            "bookable_path",
        )

        self.assertContains(
            response,
            "مسیر رزرو واقعی را کامل کن",
        )
        self.assertContains(
            response,
            "data-dashboard-setup-priority",
        )
        self.assertContains(
            response,
            "data-dashboard-setup-primary-action",
        )

    def test_ready_manager_dashboard_does_not_show_priority_card(self):
        readiness = self._readiness(
            missing_items=[],
            percent=100,
            is_ready=True,
        )

        response = self._get_dashboard(readiness)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["dashboard_home"]["setup_priority"])
        self.assertNotContains(
            response,
            "data-dashboard-setup-priority",
        )

    def test_non_actionable_missing_item_is_not_selected(self):
        readiness = self._readiness(
            missing_items=[
                {
                    "key": "verification",
                    "title": "احراز سالن",
                    "description": "در انتظار بررسی است.",
                    "action_label": "",
                    "action_url": "#",
                    "weight": 1,
                }
            ]
        )

        self.assertIsNone(_build_dashboard_setup_priority(readiness))
