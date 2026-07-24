from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import SalonManager
from apps.analytics.models import AnalyticsEvent
from apps.orders.models import BookingQuickLink
from apps.orders.quick_links import (
    BOOKING_QUICK_LINK_OPENED_EVENT,
    count_booking_quick_link_unique_visitors,
    sign_booking_payload,
)
from apps.salons.models import Salon
from apps.services.models import Services


User = get_user_model()


class BookingQuickLinkOpenAnalyticsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = User.objects.create_user(
            mobile_number="09129993001",
            password="test-pass-123",
            name="مدیر",
            family="بازدید",
        )
        cls.manager_user.is_active = True
        cls.manager_user.save(update_fields=["is_active"])

        cls.manager = SalonManager.objects.create(
            user=cls.manager_user,
            is_active=True,
        )

        cls.salon = Salon.objects.create(
            salon_name="سالن بازدید لینک",
            salon_manager=cls.manager,
            is_active=True,
        )

        cls.service = Services.objects.create(
            service_name="خدمت بازدید لینک",
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
            "placement": BookingQuickLink.Placement.TABLE_STAND,
            "campaign_name": "کمپین استند",
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

    def open_url(self, quick_link):
        return reverse(
            "orders:quick_booking_entry",
            kwargs={"token": str(quick_link.token)},
        )

    def opened_events(self, quick_link):
        content_type = ContentType.objects.get_for_model(
            BookingQuickLink,
            for_concrete_model=False,
        )

        return AnalyticsEvent.objects.filter(
            event_type=BOOKING_QUICK_LINK_OPENED_EVENT,
            target_content_type=content_type,
            target_object_id=quick_link.pk,
        ).order_by("id")

    def test_anonymous_open_creates_session_event_and_counter(self):
        quick_link = self.create_quick_link()
        client = Client(
            HTTP_USER_AGENT="Loomera quick-link test",
            REMOTE_ADDR="127.0.0.1",
        )

        response = client.get(self.open_url(quick_link))

        self.assertEqual(response.status_code, 302)

        quick_link.refresh_from_db()
        events = self.opened_events(quick_link)

        self.assertEqual(quick_link.opens_count, 1)
        self.assertIsNotNone(quick_link.last_opened_at)
        self.assertEqual(events.count(), 1)

        event = events.get()
        session_key = client.session.session_key

        self.assertTrue(session_key)
        self.assertEqual(event.session_key, session_key)
        self.assertIsNone(event.actor_id)
        self.assertEqual(event.salon_id, self.salon.pk)
        self.assertEqual(
            event.source,
            BookingQuickLink.Placement.TABLE_STAND,
        )
        self.assertEqual(
            event.metadata["campaign_name"],
            "کمپین استند",
        )
        self.assertEqual(
            event.user_agent,
            "Loomera quick-link test",
        )
        self.assertEqual(
            client.session["booking_quick_link_id"],
            quick_link.pk,
        )

    def test_repeated_open_in_same_session_counts_total_not_unique(self):
        quick_link = self.create_quick_link()
        client = Client()

        first_response = client.get(self.open_url(quick_link))
        second_response = client.get(self.open_url(quick_link))

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 302)

        quick_link.refresh_from_db()

        self.assertEqual(quick_link.opens_count, 2)
        self.assertEqual(
            self.opened_events(quick_link).count(),
            2,
        )
        self.assertEqual(
            count_booking_quick_link_unique_visitors(quick_link),
            1,
        )

    def test_different_sessions_are_counted_as_unique_visitors(self):
        quick_link = self.create_quick_link()
        first_client = Client()
        second_client = Client()

        first_client.get(self.open_url(quick_link))
        first_client.get(self.open_url(quick_link))
        second_client.get(self.open_url(quick_link))

        quick_link.refresh_from_db()

        self.assertEqual(quick_link.opens_count, 3)
        self.assertEqual(
            self.opened_events(quick_link).count(),
            3,
        )
        self.assertEqual(
            count_booking_quick_link_unique_visitors(quick_link),
            2,
        )

    def test_authenticated_open_records_actor(self):
        quick_link = self.create_quick_link()
        client = Client()
        client.force_login(self.manager_user)

        response = client.get(self.open_url(quick_link))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.opened_events(quick_link).get().actor_id,
            self.manager_user.pk,
        )

    def test_inactive_link_does_not_create_open_event(self):
        quick_link = self.create_quick_link(is_active=False)
        client = Client()

        response = client.get(self.open_url(quick_link))

        self.assertEqual(response.status_code, 410)

        quick_link.refresh_from_db()

        self.assertEqual(quick_link.opens_count, 0)
        self.assertIsNone(quick_link.last_opened_at)
        self.assertFalse(self.opened_events(quick_link).exists())

    def test_archived_link_does_not_create_open_event(self):
        quick_link = self.create_quick_link(
            is_active=False,
            archived_at=quick_link_archived_at(),
        )
        client = Client()

        response = client.get(self.open_url(quick_link))

        self.assertEqual(response.status_code, 410)

        quick_link.refresh_from_db()

        self.assertEqual(quick_link.opens_count, 0)
        self.assertFalse(self.opened_events(quick_link).exists())

    def test_legacy_signed_link_remains_supported_without_model_event(self):
        payload = {
            "mode": BookingQuickLink.Mode.SERVICE,
            "salon_id": self.salon.pk,
            "service_ids": [self.service.pk],
            "stylist_user_id": None,
            "date": "",
            "time": "",
            "summary": {},
        }
        token = sign_booking_payload(payload)
        client = Client()

        response = client.get(
            reverse(
                "orders:quick_booking_entry",
                kwargs={"token": token},
            )
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            AnalyticsEvent.objects.filter(
                event_type=BOOKING_QUICK_LINK_OPENED_EVENT,
            ).exists()
        )


def quick_link_archived_at():
    from django.utils import timezone

    return timezone.now()
