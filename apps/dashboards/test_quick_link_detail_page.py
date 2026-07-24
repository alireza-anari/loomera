from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import (
    Customer,
    SalonManager,
    Stylist,
)
from apps.analytics.models import AnalyticsEvent
from apps.orders.models import BookingQuickLink, Order
from apps.orders.quick_link_detail_stats import (
    build_booking_quick_link_detail_stats,
)
from apps.orders.quick_links import (
    BOOKING_QUICK_LINK_CONVERTED_EVENT,
    BOOKING_QUICK_LINK_OPENED_EVENT,
    BOOKING_QUICK_LINK_STARTED_EVENT,
)
from apps.salons.models import (
    Salon,
    SalonMembership,
    SalonMembershipStatus,
)
from apps.services.models import Services


User = get_user_model()


class QuickLinkDetailPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = User.objects.create_user(
            mobile_number="09126661001",
            password="test-pass-123",
            name="مدیر",
            family="جزئیات لینک",
        )
        cls.manager_user.is_active = True
        cls.manager_user.save(
            update_fields=["is_active"]
        )

        cls.other_manager_user = User.objects.create_user(
            mobile_number="09126661002",
            password="test-pass-123",
            name="مدیر",
            family="سالن دیگر",
        )
        cls.other_manager_user.is_active = True
        cls.other_manager_user.save(
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
            salon_name="سالن جزئیات لینک",
            salon_manager=cls.manager,
            is_active=True,
        )
        cls.other_salon = Salon.objects.create(
            salon_name="سالن خارج از Scope",
            salon_manager=cls.other_manager,
            is_active=True,
        )

        cls.stylist_user = User.objects.create_user(
            mobile_number="09126661003",
            password="test-pass-123",
            name="متخصص",
            family="جزئیات",
        )
        cls.stylist_user.is_active = True
        cls.stylist_user.save(
            update_fields=["is_active"]
        )

        cls.other_stylist_user = User.objects.create_user(
            mobile_number="09126661004",
            password="test-pass-123",
            name="متخصص",
            family="دیگر",
        )
        cls.other_stylist_user.is_active = True
        cls.other_stylist_user.save(
            update_fields=["is_active"]
        )

        cls.stylist = Stylist.objects.create(
            user=cls.stylist_user,
            expert="مو",
            is_active=True,
        )
        cls.other_stylist = Stylist.objects.create(
            user=cls.other_stylist_user,
            expert="پوست",
            is_active=True,
        )

        cls.salon.stylists.add(
            cls.stylist,
            cls.other_stylist,
        )

        cls.service = Services.objects.create(
            service_name="خدمت جزئیات لینک",
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
        cls.other_salon.services.add(
            cls.other_service
        )
        cls.service.stylists.add(
            cls.stylist,
            cls.other_stylist,
        )

        SalonMembership.objects.create(
            salon=cls.salon,
            stylist=cls.stylist,
            status=SalonMembershipStatus.ACTIVE,
        )

        cls.customer_user = User.objects.create_user(
            mobile_number="09126661005",
            password="test-pass-123",
            name="مشتری",
            family="جزئیات",
        )
        cls.customer = Customer.objects.create(
            user=cls.customer_user
        )

    def setUp(self):
        self.now = timezone.now()

    def create_link(
        self,
        *,
        creator=None,
        salon=None,
        service=None,
        stylist=None,
        title="لینک جزئیات",
    ):
        creator = creator or self.manager_user
        salon = salon or self.salon
        service = service or self.service

        mode = (
            BookingQuickLink.Mode.SERVICE_STYLIST
            if stylist
            else BookingQuickLink.Mode.SERVICE
        )

        return BookingQuickLink.objects.create(
            creator=creator,
            salon=salon,
            service=service,
            stylist=stylist,
            title=title,
            mode=mode,
            placement=(
                BookingQuickLink.Placement
                .MIRROR_LABEL
            ),
            campaign_name="کمپین جزئیات",
            internal_note="یادداشت جزئیات",
            payload={
                "mode": mode,
                "salon_id": salon.pk,
                "service_ids": [service.pk],
                "stylist_user_id": (
                    stylist.pk if stylist else None
                ),
                "date": "",
                "time": "",
                "summary": {},
            },
            is_permanent=True,
        )

    def create_event(
        self,
        *,
        quick_link,
        event_type,
        session_key,
        occurred_at,
        order=None,
    ):
        content_type = ContentType.objects.get_for_model(
            BookingQuickLink,
            for_concrete_model=False,
        )

        return AnalyticsEvent.objects.create(
            category="appointment",
            event_type=event_type,
            occurred_at=occurred_at,
            salon=quick_link.salon,
            stylist=quick_link.stylist,
            order=order,
            target_content_type=content_type,
            target_object_id=quick_link.pk,
            session_key=session_key,
            source=quick_link.placement,
            metadata={
                "quick_link_id": quick_link.pk,
            },
        )

    def add_funnel_activity(self, quick_link):
        yesterday = self.now - timedelta(days=1)

        for session_key in (
            "detail-session-1",
            "detail-session-1",
            "detail-session-2",
        ):
            self.create_event(
                quick_link=quick_link,
                event_type=(
                    BOOKING_QUICK_LINK_OPENED_EVENT
                ),
                session_key=session_key,
                occurred_at=yesterday,
            )

        self.create_event(
            quick_link=quick_link,
            event_type=(
                BOOKING_QUICK_LINK_STARTED_EVENT
            ),
            session_key="detail-session-1",
            occurred_at=yesterday,
        )

        order = Order.objects.create(
            customer=self.customer,
            salon=quick_link.salon,
            status="completed",
            is_finally=True,
            selected_payment_method="pay_in_salon",
            booking_quick_link=quick_link,
            service_completed_at=self.now,
        )

        self.create_event(
            quick_link=quick_link,
            event_type=(
                BOOKING_QUICK_LINK_CONVERTED_EVENT
            ),
            session_key="detail-session-1",
            occurred_at=self.now,
            order=order,
        )

    def stylist_client(self):
        client = Client()
        client.force_login(self.stylist_user)

        session = client.session
        session["active_stylist_salon_id"] = str(
            self.salon.pk
        )
        session.save()

        return client

    def test_manager_detail_renders_funnel_and_daily_metrics(self):
        quick_link = self.create_link(
            creator=self.stylist_user,
            stylist=self.stylist,
        )
        self.add_funnel_activity(quick_link)

        client = Client()
        client.force_login(self.manager_user)

        response = client.get(
            reverse(
                "dashboards:quick_link_detail",
                kwargs={"link_id": quick_link.pk},
            ),
            {"period": "7"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funnel رزرو")
        self.assertContains(response, "روند روزانه")

        detail = response.context[
            "quick_link_detail"
        ]
        metrics = detail["metrics"]

        self.assertEqual(detail["period"]["key"], "7")
        self.assertEqual(metrics["total_opens"], 3)
        self.assertEqual(metrics["unique_visitors"], 2)
        self.assertEqual(metrics["started_count"], 1)
        self.assertEqual(metrics["converted_count"], 1)
        self.assertEqual(metrics["conversion_rate"], 50.0)
        self.assertEqual(metrics["start_rate"], 50.0)
        self.assertEqual(
            metrics["converted_from_start_rate"],
            100.0,
        )
        self.assertEqual(metrics["completed_count"], 1)
        self.assertTrue(detail["has_activity"])
        self.assertTrue(detail["daily"])

    def test_invalid_period_falls_back_to_30(self):
        quick_link = self.create_link()
        client = Client()
        client.force_login(self.manager_user)

        response = client.get(
            reverse(
                "dashboards:quick_link_detail",
                kwargs={"link_id": quick_link.pk},
            ),
            {"period": "invalid"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context[
                "quick_link_detail"
            ]["period"]["key"],
            "30",
        )

    def test_manager_scope_blocks_other_salon(self):
        quick_link = self.create_link(
            creator=self.other_manager_user,
            salon=self.other_salon,
            service=self.other_service,
        )

        client = Client()
        client.force_login(self.manager_user)

        response = client.get(
            reverse(
                "dashboards:quick_link_detail",
                kwargs={"link_id": quick_link.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_stylist_scope_only_allows_own_link(self):
        own_link = self.create_link(
            creator=self.stylist_user,
            stylist=self.stylist,
        )
        manager_link = self.create_link(
            creator=self.manager_user,
            stylist=self.stylist,
            title="لینک مدیر",
        )
        other_stylist_link = self.create_link(
            creator=self.other_stylist_user,
            stylist=self.other_stylist,
            title="لینک متخصص دیگر",
        )

        client = self.stylist_client()

        own_response = client.get(
            reverse(
                "dashboards:stylist_quick_link_detail",
                kwargs={"link_id": own_link.pk},
            )
        )
        manager_response = client.get(
            reverse(
                "dashboards:stylist_quick_link_detail",
                kwargs={"link_id": manager_link.pk},
            )
        )
        other_response = client.get(
            reverse(
                "dashboards:stylist_quick_link_detail",
                kwargs={
                    "link_id": other_stylist_link.pk
                },
            )
        )

        self.assertEqual(own_response.status_code, 200)
        self.assertEqual(manager_response.status_code, 404)
        self.assertEqual(other_response.status_code, 404)

    def test_list_pages_render_detail_actions(self):
        manager_link = self.create_link()
        stylist_link = self.create_link(
            creator=self.stylist_user,
            stylist=self.stylist,
            title="لینک متخصص",
        )

        manager_client = Client()
        manager_client.force_login(self.manager_user)
        manager_response = manager_client.get(
            reverse("dashboards:quick_links")
        )

        self.assertEqual(manager_response.status_code, 200)
        self.assertContains(
            manager_response,
            reverse(
                "dashboards:quick_link_detail",
                kwargs={"link_id": manager_link.pk},
            ),
        )

        stylist_response = self.stylist_client().get(
            reverse("dashboards:stylist_quick_links")
        )

        self.assertEqual(stylist_response.status_code, 200)
        self.assertContains(
            stylist_response,
            reverse(
                "dashboards:stylist_quick_link_detail",
                kwargs={"link_id": stylist_link.pk},
            ),
        )

    def test_detail_stats_query_budget_is_fixed(self):
        quick_link = self.create_link()
        self.add_funnel_activity(quick_link)

        ContentType.objects.clear_cache()

        with CaptureQueriesContext(connection) as captured:
            result = (
                build_booking_quick_link_detail_stats(
                    quick_link=quick_link,
                    period="30",
                    now=self.now,
                )
            )

        self.assertEqual(
            result["metrics"]["converted_count"],
            1,
        )
        self.assertLessEqual(
            len(captured),
            4,
            msg=(
                "Quick-link detail stats must use a fixed "
                "grouped-query budget."
            ),
        )
