from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.dashboards.beta_readiness import (
    serialize_beta_salon_readiness,
)
from tests_stage1_helpers import Stage1DomainFactoryMixin


class PlatformSalonBetaReadinessPanelTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(
            manager=self.manager,
        )

        self.admin_user = self.make_user(
            is_admin=True,
        )
        self.client.force_login(self.admin_user)

    def _incomplete_result(self):
        return {
            "salon_id": self.salon.pk,
            "salon_name": self.salon.salon_name,
            "slug": self.salon.slug or "",
            "is_active": self.salon.is_active,
            "verification_status": (self.salon.verification_status),
            "readiness_percent": 68,
            "readiness_percent_label": "۶۸٪",
            "completed_count": 7,
            "total_count": 12,
            "missing_count": 2,
            "has_bookable_path": False,
            "checklist_ready": False,
            "beta_ready": False,
            "status_label": "نیازمند تکمیل",
            "status_tone": "warning",
            "critical_missing_keys": [
                "bookable_path",
            ],
            "critical_missing_count": 1,
            "primary_blocker": {
                "key": "bookable_path",
                "title": "مسیر رزرو واقعی وجود ندارد",
                "description": ("یک متخصص دارای خدمت و شیفت لازم است."),
                "action_label": "بررسی تیم",
                "action_url": "/dashboard/private-action/",
                "weight": 3,
                "is_critical": True,
            },
            "missing_items": [
                {
                    "key": "bookable_path",
                    "title": ("مسیر رزرو واقعی وجود ندارد"),
                    "description": ("یک متخصص دارای خدمت و شیفت لازم است."),
                    "action_label": "بررسی تیم",
                    "action_url": ("/dashboard/private-action/"),
                    "weight": 3,
                    "is_critical": True,
                },
                {
                    "key": "gallery",
                    "title": "گالری سالن ناقص است",
                    "description": ("حداقل یک تصویر واقعی لازم است."),
                    "action_label": "مدیریت گالری",
                    "action_url": ("/dashboard/private-gallery/"),
                    "weight": 1,
                    "is_critical": False,
                },
            ],
            "summary": "چند مورد باقی مانده است.",
        }

    def _ready_result(self):
        result = self._incomplete_result()

        result.update(
            {
                "readiness_percent": 100,
                "readiness_percent_label": "۱۰۰٪",
                "completed_count": 12,
                "missing_count": 0,
                "has_bookable_path": True,
                "checklist_ready": True,
                "beta_ready": True,
                "status_label": "آماده بتا",
                "status_tone": "success",
                "critical_missing_keys": [],
                "critical_missing_count": 0,
                "primary_blocker": None,
                "missing_items": [],
                "summary": "سالن آماده شروع است.",
            }
        )

        return result

    def test_salon_list_displays_beta_readiness_status(self):
        with patch(
            "apps.platform_admin.views." "serialize_beta_salon_readiness",
            return_value=self._incomplete_result(),
        ):
            response = self.client.get(reverse("platform_admin:salons"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "نیازمند تکمیل",
        )
        self.assertContains(response, "۶۸٪")
        self.assertContains(
            response,
            "بدون مسیر رزرو",
        )
        self.assertContains(
            response,
            "data-platform-salon-beta-status",
        )

    def test_salon_detail_displays_blockers(self):
        with patch(
            "apps.platform_admin.views." "serialize_beta_salon_readiness",
            return_value=self._incomplete_result(),
        ):
            response = self.client.get(
                reverse(
                    "platform_admin:salon_detail",
                    kwargs={"pk": self.salon.pk},
                )
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "مسیر رزرو واقعی وجود ندارد",
        )
        self.assertContains(
            response,
            'data-platform-beta-missing-item="bookable_path"',
        )
        self.assertContains(
            response,
            "blocker بتا",
        )

    def test_manager_dashboard_action_urls_are_not_exposed(self):
        with patch(
            "apps.platform_admin.views." "serialize_beta_salon_readiness",
            return_value=self._incomplete_result(),
        ):
            response = self.client.get(
                reverse(
                    "platform_admin:salon_detail",
                    kwargs={"pk": self.salon.pk},
                )
            )

        self.assertNotContains(
            response,
            "/dashboard/private-action/",
        )
        self.assertNotContains(
            response,
            "/dashboard/private-gallery/",
        )

    def test_ready_salon_displays_ready_state(self):
        with patch(
            "apps.platform_admin.views." "serialize_beta_salon_readiness",
            return_value=self._ready_result(),
        ):
            response = self.client.get(
                reverse(
                    "platform_admin:salon_detail",
                    kwargs={"pk": self.salon.pk},
                )
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "آماده بتا")
        self.assertContains(
            response,
            "data-platform-beta-ready",
        )
        self.assertNotContains(
            response,
            "data-platform-beta-missing-item",
        )

    def test_shared_serializer_marks_bookable_path_as_critical(self):
        readiness = {
            "enabled": True,
            "is_ready": False,
            "percent": 75,
            "percent_label": "۷۵٪",
            "completed_count": 8,
            "total_count": 12,
            "has_bookable_path": False,
            "items": [
                {
                    "key": "bookable_path",
                    "is_done": False,
                }
            ],
            "missing_items": [
                {
                    "key": "bookable_path",
                    "title": "مسیر رزرو ناقص است",
                    "description": "نیازمند شیفت منطبق است.",
                    "action_label": "بررسی",
                    "action_url": "/dashboard/shifts/",
                    "weight": 3,
                }
            ],
            "summary": "سالن ناقص است.",
        }

        with patch(
            "apps.dashboards.beta_readiness." "build_salon_readiness_checklist",
            return_value=readiness,
        ):
            result = serialize_beta_salon_readiness(self.salon)

        self.assertFalse(result["beta_ready"])
        self.assertFalse(result["has_bookable_path"])
        self.assertEqual(
            result["critical_missing_keys"],
            ["bookable_path"],
        )
        self.assertTrue(result["primary_blocker"]["is_critical"])

    def test_readiness_panel_does_not_modify_salon(self):
        before = {
            "name": self.salon.salon_name,
            "active": self.salon.is_active,
            "verification": (self.salon.verification_status),
        }

        with patch(
            "apps.platform_admin.views." "serialize_beta_salon_readiness",
            return_value=self._incomplete_result(),
        ):
            self.client.get(
                reverse(
                    "platform_admin:salon_detail",
                    kwargs={"pk": self.salon.pk},
                )
            )

        self.salon.refresh_from_db()

        self.assertEqual(
            self.salon.salon_name,
            before["name"],
        )
        self.assertEqual(
            self.salon.is_active,
            before["active"],
        )
        self.assertEqual(
            self.salon.verification_status,
            before["verification"],
        )
