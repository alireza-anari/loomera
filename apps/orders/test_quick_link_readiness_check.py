from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import SalonManager
from apps.analytics.models import AnalyticsEvent
from apps.orders.models import BookingQuickLink
from apps.orders.quick_links import (
    BOOKING_QUICK_LINK_CONVERTED_EVENT,
    BOOKING_QUICK_LINK_OPENED_EVENT,
)
from apps.salons.models import Salon
from apps.services.models import Services


User = get_user_model()


class QuickLinkReadinessCheckTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = User.objects.create_user(
            mobile_number="09126661001",
            password="test-pass-123",
            name="مدیر",
            family="آمادگی لینک",
        )
        cls.manager_user.is_active = True
        cls.manager_user.save(
            update_fields=["is_active"]
        )

        cls.manager = SalonManager.objects.create(
            user=cls.manager_user,
            is_active=True,
        )

        cls.salon = Salon.objects.create(
            salon_name="سالن آمادگی لینک",
            salon_manager=cls.manager,
            is_active=True,
        )

        cls.service = Services.objects.create(
            service_name="خدمت آمادگی لینک",
            is_active=True,
            duration_minutes=30,
            base_price=100000,
        )

        cls.salon.services.add(cls.service)

    def create_link(self, **overrides):
        values = {
            "creator": self.manager_user,
            "salon": self.salon,
            "service": self.service,
            "title": "لینک آمادگی",
            "mode": BookingQuickLink.Mode.SERVICE,
            "placement": (
                BookingQuickLink.Placement.DIRECT
            ),
            "payload": {
                "mode": BookingQuickLink.Mode.SERVICE,
                "salon_id": self.salon.pk,
                "service_ids": [self.service.pk],
                "stylist_user_id": None,
                "date": "",
                "time": "",
                "summary": {},
            },
            "is_permanent": True,
        }
        values.update(overrides)

        return BookingQuickLink.objects.create(
            **values
        )

    def create_event(
        self,
        *,
        quick_link,
        event_type,
        session_key="",
    ):
        content_type = (
            ContentType.objects.get_for_model(
                BookingQuickLink,
                for_concrete_model=False,
            )
        )

        return AnalyticsEvent.objects.create(
            category="appointment",
            event_type=event_type,
            occurred_at=timezone.now(),
            salon=self.salon,
            target_content_type=content_type,
            target_object_id=quick_link.pk,
            session_key=session_key,
            source=quick_link.placement,
            metadata={
                "quick_link_id": quick_link.pk,
            },
        )

    def run_command(self, *arguments):
        output = StringIO()

        call_command(
            "quick_link_readiness_check",
            *arguments,
            stdout=output,
        )

        return output.getvalue()

    def test_healthy_project_passes_without_writes(self):
        quick_link = self.create_link()

        link_count = (
            BookingQuickLink.objects.count()
        )
        event_count = (
            AnalyticsEvent.objects.count()
        )

        output = self.run_command()

        self.assertIn(
            "Quick-link readiness passed.",
            output,
        )
        self.assertIn(
            "duplicate-conversions",
            output,
        )
        self.assertIn(
            "qr-glyph",
            output,
        )

        self.assertEqual(
            BookingQuickLink.objects.count(),
            link_count,
        )
        self.assertEqual(
            AnalyticsEvent.objects.count(),
            event_count,
        )

        quick_link.refresh_from_db()
        self.assertTrue(quick_link.is_active)

    def test_archived_active_link_fails(self):
        self.create_link(
            archived_at=timezone.now(),
            is_active=True,
        )

        with self.assertRaises(CommandError):
            self.run_command()

    def test_blank_session_is_warning_by_default(self):
        quick_link = self.create_link()

        self.create_event(
            quick_link=quick_link,
            event_type=(
                BOOKING_QUICK_LINK_OPENED_EVENT
            ),
            session_key="",
        )

        output = self.run_command()

        self.assertIn(
            "WARN blank-analytics-session",
            output,
        )

    def test_fail_on_warnings_returns_non_zero(self):
        quick_link = self.create_link()

        self.create_event(
            quick_link=quick_link,
            event_type=(
                BOOKING_QUICK_LINK_OPENED_EVENT
            ),
            session_key="",
        )

        with self.assertRaises(CommandError):
            self.run_command(
                "--fail-on-warnings"
            )

    def test_orphan_analytics_event_fails(self):
        quick_link = self.create_link()

        event = self.create_event(
            quick_link=quick_link,
            event_type=(
                BOOKING_QUICK_LINK_CONVERTED_EVENT
            ),
            session_key="session-1",
        )

        event.target_object_id = (
            quick_link.pk + 999999
        )
        event.save(
            update_fields=[
                "target_object_id",
            ]
        )

        with self.assertRaises(CommandError):
            self.run_command()
