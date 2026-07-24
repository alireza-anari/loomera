from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.dashboards.management.commands.beta_salon_readiness_check import (
    Command,
)
from tests_stage1_helpers import Stage1DomainFactoryMixin


class BetaSalonReadinessCommandTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(manager=self.manager)

    @staticmethod
    def _ready_payload():
        return {
            "enabled": True,
            "is_ready": True,
            "percent": 100,
            "percent_label": "۱۰۰٪",
            "completed_count": 12,
            "total_count": 12,
            "missing_count": 0,
            "has_bookable_path": True,
            "items": [
                {
                    "key": "bookable_path",
                    "is_done": True,
                }
            ],
            "missing_items": [],
            "summary": "سالن آماده است.",
        }

    @staticmethod
    def _incomplete_payload():
        return {
            "enabled": True,
            "is_ready": False,
            "percent": 68,
            "percent_label": "۶۸٪",
            "completed_count": 7,
            "total_count": 12,
            "missing_count": 2,
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
                    "title": "مسیر رزرو واقعی وجود ندارد",
                    "action_label": "بررسی تیم و شیفت‌ها",
                    "action_url": "/dashboard/shifts/",
                    "weight": 3,
                },
                {
                    "key": "gallery",
                    "title": "گالری ناقص است",
                    "action_label": "مدیریت گالری",
                    "action_url": "/dashboard/profile/",
                    "weight": 1,
                },
            ],
            "summary": "چند مورد باقی مانده است.",
        }

    def test_json_output_is_scoped_and_contains_no_manager_pii(self):
        stdout = StringIO()

        with patch(
            "apps.dashboards.beta_readiness."
            "build_salon_readiness_checklist",
            return_value=self._incomplete_payload(),
        ):
            call_command(
                "beta_salon_readiness_check",
                salon_ids=[self.salon.pk],
                as_json=True,
                stdout=stdout,
            )

        payload = json.loads(stdout.getvalue())

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["summary"]["total"], 1)

        salon_payload = payload["salons"][0]
        self.assertEqual(
            salon_payload["salon_id"],
            self.salon.pk,
        )
        self.assertEqual(
            salon_payload["salon_name"],
            self.salon.salon_name,
        )
        self.assertFalse(salon_payload["has_bookable_path"])
        self.assertIn(
            "bookable_path",
            salon_payload["critical_missing_keys"],
        )

        body = stdout.getvalue()
        self.assertNotIn(
            self.manager.user.mobile_number,
            body,
        )
        self.assertNotIn(
            self.manager.user.email,
            body,
        )
        self.assertNotIn("SECRET_KEY", body)
        self.assertNotIn("DATABASES", body)

    def test_strict_mode_passes_for_ready_selected_salon(self):
        with patch(
            "apps.dashboards.beta_readiness."
            "build_salon_readiness_checklist",
            return_value=self._ready_payload(),
        ):
            call_command(
                "beta_salon_readiness_check",
                salon_ids=[self.salon.pk],
                strict=True,
                stdout=StringIO(),
            )

    def test_strict_mode_fails_for_incomplete_selected_salon(self):
        with patch(
            "apps.dashboards.beta_readiness."
            "build_salon_readiness_checklist",
            return_value=self._incomplete_payload(),
        ):
            with self.assertRaises(CommandError):
                call_command(
                    "beta_salon_readiness_check",
                    salon_ids=[self.salon.pk],
                    strict=True,
                    stdout=StringIO(),
                )

    def test_unknown_selected_salon_id_is_rejected(self):
        unknown_id = self.salon.pk + 99999

        with self.assertRaises(CommandError):
            call_command(
                "beta_salon_readiness_check",
                salon_ids=[unknown_id],
                stdout=StringIO(),
            )

    def test_active_only_excludes_inactive_salon(self):
        self.salon.is_active = False
        self.salon.save(update_fields=["is_active"])

        stdout = StringIO()
        call_command(
            "beta_salon_readiness_check",
            active_only=True,
            as_json=True,
            stdout=stdout,
        )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["summary"]["total"], 0)
        self.assertEqual(payload["salons"], [])

    def test_only_incomplete_hides_ready_salon(self):
        stdout = StringIO()

        with patch(
            "apps.dashboards.beta_readiness."
            "build_salon_readiness_checklist",
            return_value=self._ready_payload(),
        ):
            call_command(
                "beta_salon_readiness_check",
                salon_ids=[self.salon.pk],
                only_incomplete=True,
                as_json=True,
                stdout=stdout,
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["summary"]["total"], 0)
        self.assertEqual(payload["salons"], [])

    def test_command_does_not_modify_salon(self):
        before = {
            "name": self.salon.salon_name,
            "active": self.salon.is_active,
            "verification": self.salon.verification_status,
        }

        with patch(
            "apps.dashboards.beta_readiness."
            "build_salon_readiness_checklist",
            return_value=self._incomplete_payload(),
        ):
            call_command(
                "beta_salon_readiness_check",
                salon_ids=[self.salon.pk],
                stdout=StringIO(),
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

    def test_serializer_falls_back_to_bookable_path_item(self):
        payload = self._ready_payload()
        payload.pop("has_bookable_path")

        with patch(
            "apps.dashboards.beta_readiness."
            "build_salon_readiness_checklist",
            return_value=payload,
        ):
            serialized = Command._serialize_salon(self.salon)

        self.assertTrue(serialized["has_bookable_path"])
        self.assertTrue(serialized["beta_ready"])
