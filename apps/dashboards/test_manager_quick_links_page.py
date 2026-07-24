from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import (
    Customer,
    SalonManager,
)
from apps.analytics.models import AnalyticsEvent
from apps.orders.models import (
    BookingQuickLink,
    Order,
)
from apps.orders.quick_links import (
    BOOKING_QUICK_LINK_CONVERTED_EVENT,
    BOOKING_QUICK_LINK_OPENED_EVENT,
    BOOKING_QUICK_LINK_STARTED_EVENT,
)
from apps.salons.models import Salon
from apps.services.models import Services


User = get_user_model()


class ManagerQuickLinksPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = User.objects.create_user(
            mobile_number="09129998001",
            password="test-pass-123",
            name="مدیر",
            family="لینک‌ها",
        )
        cls.manager_user.is_active = True
        cls.manager_user.save(
            update_fields=["is_active"]
        )

        cls.other_manager_user = User.objects.create_user(
            mobile_number="09129998002",
            password="test-pass-123",
            name="مدیر",
            family="دیگر",
        )
        cls.other_manager_user.is_active = True
        cls.other_manager_user.save(
            update_fields=["is_active"]
        )

        cls.stylist_creator = User.objects.create_user(
            mobile_number="09129998003",
            password="test-pass-123",
            name="متخصص",
            family="سازنده",
        )
        cls.stylist_creator.is_active = True
        cls.stylist_creator.save(
            update_fields=["is_active"]
        )

        cls.manager = SalonManager.objects.create(
            user=cls.manager_user,
            is_active=True,
        )

        cls.other_manager = SalonManager.objects.create(
            user=cls.other_manager_user,
            is_active=True,
        )

        cls.salon = Salon.objects.create(
            salon_name="سالن لینک‌های مدیر",
            salon_manager=cls.manager,
            is_active=True,
        )

        cls.other_salon = Salon.objects.create(
            salon_name="سالن خارج از Scope",
            salon_manager=cls.other_manager,
            is_active=True,
        )

        cls.service = Services.objects.create(
            service_name="خدمت لینک مدیر",
            is_active=True,
            duration_minutes=30,
            base_price=100000,
        )

        cls.other_service = Services.objects.create(
            service_name="خدمت سالن دیگر",
            is_active=True,
            duration_minutes=30,
            base_price=120000,
        )

        cls.salon.services.add(cls.service)
        cls.other_salon.services.add(cls.other_service)

        cls.customer_user = User.objects.create_user(
            mobile_number="09129998004",
            password="test-pass-123",
            name="مشتری",
            family="لینک",
        )

        cls.customer = Customer.objects.create(
            user=cls.customer_user
        )

    def create_link(
        self,
        *,
        creator=None,
        salon=None,
        service=None,
        title="",
        **overrides,
    ):
        creator = creator or self.manager_user
        salon = salon or self.salon
        service = service or self.service

        values = {
            "creator": creator,
            "salon": salon,
            "service": service,
            "title": title,
            "mode": BookingQuickLink.Mode.SERVICE,
            "placement": (
                BookingQuickLink.Placement.DIRECT
            ),
            "campaign_name": "کمپین صفحه مدیر",
            "payload": {
                "mode": BookingQuickLink.Mode.SERVICE,
                "salon_id": salon.pk,
                "service_ids": [service.pk],
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
        session_key,
        order=None,
    ):
        content_type = ContentType.objects.get_for_model(
            BookingQuickLink,
            for_concrete_model=False,
        )

        return AnalyticsEvent.objects.create(
            category="appointment",
            event_type=event_type,
            occurred_at=timezone.now(),
            salon=quick_link.salon,
            order=order,
            target_content_type=content_type,
            target_object_id=quick_link.pk,
            session_key=session_key,
            source=quick_link.placement,
            metadata={"quick_link_id": quick_link.pk},
        )

    def page_url(self):
        return reverse("dashboards:quick_links")

    def test_anonymous_user_is_redirected(self):
        response = Client().get(self.page_url())

        self.assertEqual(response.status_code, 302)

    def test_manager_page_renders_title_and_zero_safe_summary(self):
        client = Client()
        client.force_login(self.manager_user)

        response = client.get(self.page_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "لینک‌های رزرو")

        summary = response.context[
            "quick_link_page"
        ]["summary"]

        self.assertEqual(summary["total_links"], 0)
        self.assertEqual(summary["unique_visitors"], 0)
        self.assertEqual(summary["conversion_rate"], 0.0)

    def test_manager_sees_all_same_salon_creators(self):
        manager_link = self.create_link(
            title="لینک مدیر"
        )

        stylist_link = self.create_link(
            creator=self.stylist_creator,
            title="لینک متخصص همان سالن",
        )

        other_link = self.create_link(
            creator=self.other_manager_user,
            salon=self.other_salon,
            service=self.other_service,
            title="لینک سالن دیگر",
        )

        client = Client()
        client.force_login(self.manager_user)

        response = client.get(self.page_url())

        returned_ids = {
            row["id"]
            for row
            in response.context[
                "quick_link_page"
            ]["links"]
        }

        self.assertIn(manager_link.pk, returned_ids)
        self.assertIn(stylist_link.pk, returned_ids)
        self.assertNotIn(other_link.pk, returned_ids)

        self.assertContains(
            response,
            "لینک متخصص همان سالن",
        )

        self.assertNotContains(
            response,
            "لینک سالن دیگر",
        )

    def test_period_sort_and_stats_are_rendered(self):
        quick_link = self.create_link(
            title="لینک آماری"
        )

        self.create_event(
            quick_link=quick_link,
            event_type=BOOKING_QUICK_LINK_OPENED_EVENT,
            session_key="manager-page-session",
        )

        self.create_event(
            quick_link=quick_link,
            event_type=BOOKING_QUICK_LINK_STARTED_EVENT,
            session_key="manager-page-session",
        )

        order = Order.objects.create(
            customer=self.customer,
            salon=self.salon,
            status="completed",
            is_finally=True,
            selected_payment_method="pay_in_salon",
            booking_quick_link=quick_link,
            service_completed_at=timezone.now(),
        )

        self.create_event(
            quick_link=quick_link,
            event_type=(
                BOOKING_QUICK_LINK_CONVERTED_EVENT
            ),
            session_key="manager-page-session",
            order=order,
        )

        client = Client()
        client.force_login(self.manager_user)

        response = client.get(
            self.page_url(),
            {
                "period": "7",
                "sort": "conversions",
            },
        )

        page = response.context["quick_link_page"]
        summary = page["summary"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(page["period"]["key"], "7")
        self.assertEqual(page["sort"], "conversions")
        self.assertEqual(summary["total_opens"], 1)
        self.assertEqual(summary["unique_visitors"], 1)
        self.assertEqual(summary["started_count"], 1)
        self.assertEqual(summary["converted_count"], 1)
        self.assertEqual(summary["conversion_rate"], 100.0)
        self.assertEqual(summary["completed_count"], 1)

        row = page["links"][0]

        self.assertEqual(row["id"], quick_link.pk)
        self.assertEqual(row["converted_count"], 1)
        self.assertEqual(row["conversion_rate"], 100.0)

        self.assertEqual(
            row["qr_preview_url"],
            reverse(
                "dashboards:quick_link_qr_preview",
                kwargs={"link_id": quick_link.pk},
            ),
        )

    def test_invalid_query_values_fall_back_without_500(self):
        self.create_link(title="لینک fallback")

        client = Client()
        client.force_login(self.manager_user)

        response = client.get(
            self.page_url(),
            {
                "period": "not-a-period",
                "sort": "not-a-sort",
            },
        )

        self.assertEqual(response.status_code, 200)

        page = response.context["quick_link_page"]

        self.assertEqual(page["period"]["key"], "30")
        self.assertEqual(page["sort"], "newest")

    def test_online_booking_template_links_to_new_page(self):
        template_path = (
            Path(settings.BASE_DIR)
            / "templates"
            / "dashboards"
            / "online_booking.html"
        )

        source = template_path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "{% url 'dashboards:quick_links' "
            "as quick_links_url %}",
            source,
        )

        self.assertIn(
            'href="{{ quick_links_url }}"',
            source,
        )
