import ast
import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import SalonManager
from apps.analytics.models import AnalyticsEvent
from apps.orders.models import BookingQuickLink
from apps.orders.quick_links import (
    BOOKING_QUICK_LINK_OPENED_EVENT,
    BOOKING_QUICK_LINK_STARTED_EVENT,
)
from apps.salons.models import Salon
from apps.services.models import Services


User = get_user_model()


class BookingQuickLinkStartAnalyticsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = User.objects.create_user(
            mobile_number="09129994001",
            password="test-pass-123",
            name="مدیر",
            family="شروع",
        )
        cls.manager_user.is_active = True
        cls.manager_user.save(update_fields=["is_active"])

        cls.manager = SalonManager.objects.create(
            user=cls.manager_user,
            is_active=True,
        )

        cls.salon = Salon.objects.create(
            salon_name="سالن شروع لینک",
            salon_manager=cls.manager,
            is_active=True,
        )

        cls.service = Services.objects.create(
            service_name="خدمت شروع لینک",
            is_active=True,
            duration_minutes=30,
            base_price=100000,
        )
        cls.salon.services.add(cls.service)

    def create_quick_link(self, **overrides):
        values = {
            "creator": self.manager_user,
            "salon": self.salon,
            "service": self.service,
            "mode": BookingQuickLink.Mode.SERVICE,
            "placement": BookingQuickLink.Placement.RECEPTION,
            "campaign_name": "کمپین پذیرش",
            "is_permanent": True,
            "payload": {
                "mode": BookingQuickLink.Mode.SERVICE,
                "salon_id": self.salon.pk,
                "service_ids": [self.service.pk],
                "stylist_user_id": None,
                "date": "",
                "time": "",
                "summary": {},
            },
        }
        values.update(overrides)
        return BookingQuickLink.objects.create(**values)

    def quick_link_url(self, quick_link):
        return reverse(
            "orders:quick_booking_entry",
            kwargs={"token": str(quick_link.token)},
        )

    def start_events(self, quick_link):
        content_type = ContentType.objects.get_for_model(
            BookingQuickLink,
            for_concrete_model=False,
        )

        return AnalyticsEvent.objects.filter(
            event_type=BOOKING_QUICK_LINK_STARTED_EVENT,
            target_content_type=content_type,
            target_object_id=quick_link.pk,
        ).order_by("id")

    def valid_stylist_selection_payload(self):
        return json.dumps(
            [
                {
                    "serviceId": str(self.service.pk),
                    "stylistId": "any",
                    "stylistName": "هر متخصص آزاد",
                }
            ]
        )

    def test_opening_link_does_not_start_booking(self):
        quick_link = self.create_quick_link()
        client = Client()

        response = client.get(self.quick_link_url(quick_link))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            AnalyticsEvent.objects.filter(
                event_type=BOOKING_QUICK_LINK_OPENED_EVENT,
            ).count(),
            1,
        )
        self.assertFalse(self.start_events(quick_link).exists())

    def test_valid_first_action_creates_single_start_event(self):
        quick_link = self.create_quick_link()
        client = Client(
            HTTP_USER_AGENT="Loomera booking start test",
            REMOTE_ADDR="127.0.0.1",
        )

        client.get(self.quick_link_url(quick_link))

        response = client.post(
            reverse("orders:select_stylists"),
            {
                "salon_id": str(self.salon.pk),
                "stylist_selections": (
                    self.valid_stylist_selection_payload()
                ),
            },
        )

        self.assertEqual(response.status_code, 302)

        events = self.start_events(quick_link)

        self.assertEqual(events.count(), 1)

        event = events.get()

        self.assertEqual(
            event.session_key,
            client.session.session_key,
        )
        self.assertEqual(event.salon_id, self.salon.pk)
        self.assertIsNone(event.actor_id)
        self.assertEqual(
            event.source,
            BookingQuickLink.Placement.RECEPTION,
        )
        self.assertEqual(
            event.metadata["campaign_name"],
            "کمپین پذیرش",
        )
        self.assertEqual(
            event.user_agent,
            "Loomera booking start test",
        )

    def test_repeated_actions_in_same_session_do_not_duplicate_start(self):
        quick_link = self.create_quick_link()
        client = Client()

        client.get(self.quick_link_url(quick_link))

        post_data = {
            "salon_id": str(self.salon.pk),
            "stylist_selections": (
                self.valid_stylist_selection_payload()
            ),
        }

        first_response = client.post(
            reverse("orders:select_stylists"),
            post_data,
        )
        second_response = client.post(
            reverse("orders:select_stylists"),
            post_data,
        )

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 302)
        self.assertEqual(self.start_events(quick_link).count(), 1)

    def test_different_sessions_create_distinct_start_events(self):
        quick_link = self.create_quick_link()
        first_client = Client()
        second_client = Client()

        for client in (first_client, second_client):
            client.get(self.quick_link_url(quick_link))
            client.post(
                reverse("orders:select_stylists"),
                {
                    "salon_id": str(self.salon.pk),
                    "stylist_selections": (
                        self.valid_stylist_selection_payload()
                    ),
                },
            )

        events = self.start_events(quick_link)

        self.assertEqual(events.count(), 2)
        self.assertEqual(
            events.values("session_key").distinct().count(),
            2,
        )

    def test_invalid_post_does_not_create_start_event(self):
        quick_link = self.create_quick_link()
        client = Client()

        client.get(self.quick_link_url(quick_link))

        response = client.post(
            reverse("orders:select_stylists"),
            {
                "salon_id": str(self.salon.pk),
                "stylist_selections": "{invalid-json",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.start_events(quick_link).exists())

    def test_post_without_quick_link_session_creates_no_event(self):
        client = Client()

        response = client.post(
            reverse("orders:select_stylists"),
            {
                "salon_id": str(self.salon.pk),
                "stylist_selections": (
                    self.valid_stylist_selection_payload()
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            AnalyticsEvent.objects.filter(
                event_type=BOOKING_QUICK_LINK_STARTED_EVENT,
            ).exists()
        )

    def test_all_real_action_boundaries_have_start_hook(self):
        source_path = Path(__file__).with_name("views.py")
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        expected_classes = {
            "BookingStylistSelectPerService",
            "BookingQuickLinkStylistServicesView",
            "BookingDateTimeSelectPersian",
            "ReservationPreview",
        }

        found = {}

        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue

            if node.name not in expected_classes:
                continue

            post_methods = [
                item
                for item in node.body
                if isinstance(item, ast.FunctionDef)
                and item.name == "post"
            ]

            self.assertEqual(
                len(post_methods),
                1,
                msg=f"post method missing for {node.name}",
            )

            method = post_methods[0]
            calls = [
                item
                for item in ast.walk(method)
                if isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id
                == "record_booking_quick_link_started"
            ]

            found[node.name] = len(calls)

        self.assertEqual(set(found), expected_classes)
        self.assertEqual(
            found,
            {
                "BookingStylistSelectPerService": 1,
                "BookingQuickLinkStylistServicesView": 1,
                "BookingDateTimeSelectPersian": 1,
                "ReservationPreview": 1,
            },
        )
