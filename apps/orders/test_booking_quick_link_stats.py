from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
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
from apps.orders.quick_link_stats import (
    build_booking_quick_link_stats,
    calculate_booking_quick_link_conversion_rate,
)
from apps.orders.quick_links import (
    BOOKING_QUICK_LINK_CONVERTED_EVENT,
    BOOKING_QUICK_LINK_OPENED_EVENT,
    BOOKING_QUICK_LINK_STARTED_EVENT,
)
from apps.salons.models import Salon
from apps.services.models import Services


User = get_user_model()


class BookingQuickLinkStatsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = User.objects.create_user(
            mobile_number="09129997001",
            password="test-pass-123",
            name="مدیر",
            family="آمار",
        )
        cls.manager_user.is_active = True
        cls.manager_user.save(
            update_fields=["is_active"]
        )

        cls.other_manager_user = (
            User.objects.create_user(
                mobile_number="09129997002",
                password="test-pass-123",
                name="مدیر",
                family="سالن دیگر",
            )
        )
        cls.other_manager_user.is_active = True
        cls.other_manager_user.save(
            update_fields=["is_active"]
        )

        cls.manager = SalonManager.objects.create(
            user=cls.manager_user,
            is_active=True,
        )

        cls.other_manager = (
            SalonManager.objects.create(
                user=cls.other_manager_user,
                is_active=True,
            )
        )

        cls.salon = Salon.objects.create(
            salon_name="سالن آمار لینک",
            salon_manager=cls.manager,
            is_active=True,
        )

        cls.other_salon = Salon.objects.create(
            salon_name="سالن خارج از Scope",
            salon_manager=cls.other_manager,
            is_active=True,
        )

        cls.service = Services.objects.create(
            service_name="خدمت آمار لینک",
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

        cls.customer_user = User.objects.create_user(
            mobile_number="09129997003",
            password="test-pass-123",
            name="مشتری",
            family="آمار",
        )

        cls.customer = Customer.objects.create(
            user=cls.customer_user
        )

    def setUp(self):
        self.now = timezone.now()

        self.primary_link = self.create_link(
            title="لینک اصلی",
            placement=(
                BookingQuickLink.Placement
                .MIRROR_LABEL
            ),
        )

        self.secondary_link = self.create_link(
            title="لینک دوم",
            placement=(
                BookingQuickLink.Placement
                .TABLE_STAND
            ),
        )

        self.other_salon_link = self.create_link(
            creator=self.other_manager_user,
            salon=self.other_salon,
            service=self.other_service,
            title="لینک سالن دیگر",
        )

    def create_link(
        self,
        *,
        creator=None,
        salon=None,
        service=None,
        **overrides,
    ):
        creator = creator or self.manager_user
        salon = salon or self.salon
        service = service or self.service

        values = {
            "creator": creator,
            "salon": salon,
            "service": service,
            "mode": BookingQuickLink.Mode.SERVICE,
            "placement": (
                BookingQuickLink.Placement.DIRECT
            ),
            "payload": {
                "mode": (
                    BookingQuickLink.Mode.SERVICE
                ),
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

    def create_order(
        self,
        *,
        quick_link,
        status,
        completed_at=None,
    ):
        return Order.objects.create(
            customer=self.customer,
            salon=quick_link.salon,
            status=status,
            is_finally=True,
            selected_payment_method="pay_in_salon",
            booking_quick_link=quick_link,
            service_completed_at=completed_at,
        )

    def create_event(
        self,
        *,
        quick_link,
        event_type,
        occurred_at,
        session_key="",
        order=None,
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
            occurred_at=occurred_at,
            salon=quick_link.salon,
            order=order,
            target_content_type=content_type,
            target_object_id=quick_link.pk,
            session_key=session_key,
            source=quick_link.placement,
            metadata={
                "quick_link_id": quick_link.pk,
            },
        )

    def salon_queryset(self):
        return BookingQuickLink.objects.filter(
            salon=self.salon
        )

    def add_primary_link_activity(self):
        for session_key, age_days in (
            ("session-1", 1),
            ("session-1", 1),
            ("session-2", 2),
            ("session-3", 3),
        ):
            self.create_event(
                quick_link=self.primary_link,
                event_type=(
                    BOOKING_QUICK_LINK_OPENED_EVENT
                ),
                occurred_at=(
                    self.now
                    - timedelta(days=age_days)
                ),
                session_key=session_key,
            )

        for session_key in (
            "session-1",
            "session-2",
        ):
            self.create_event(
                quick_link=self.primary_link,
                event_type=(
                    BOOKING_QUICK_LINK_STARTED_EVENT
                ),
                occurred_at=(
                    self.now
                    - timedelta(hours=12)
                ),
                session_key=session_key,
            )

        completed_order = self.create_order(
            quick_link=self.primary_link,
            status="completed",
            completed_at=(
                self.now
                - timedelta(hours=2)
            ),
        )

        cancelled_order = self.create_order(
            quick_link=self.primary_link,
            status="cancelled",
        )

        no_show_order = self.create_order(
            quick_link=self.primary_link,
            status="no_show",
        )

        for order, session_key in (
            (completed_order, "session-1"),
            (cancelled_order, "session-2"),
            (no_show_order, "session-3"),
        ):
            self.create_event(
                quick_link=self.primary_link,
                event_type=(
                    BOOKING_QUICK_LINK_CONVERTED_EVENT
                ),
                occurred_at=(
                    self.now
                    - timedelta(hours=1)
                ),
                session_key=session_key,
                order=order,
            )

    def test_period_metrics_and_order_outcomes_are_correct(self):
        self.add_primary_link_activity()

        result = build_booking_quick_link_stats(
            links_queryset=self.salon_queryset(),
            period="30",
            now=self.now,
        )

        rows = {
            row["id"]: row
            for row in result["links"]
        }

        primary = rows[self.primary_link.pk]
        secondary = rows[self.secondary_link.pk]

        self.assertEqual(primary["total_opens"], 4)
        self.assertEqual(
            primary["unique_visitors"],
            3,
        )
        self.assertEqual(primary["started_count"], 2)
        self.assertEqual(
            primary["converted_count"],
            3,
        )
        self.assertEqual(
            primary["conversion_rate"],
            100.0,
        )
        self.assertEqual(
            primary["completed_count"],
            1,
        )
        self.assertEqual(
            primary["cancelled_count"],
            1,
        )
        self.assertEqual(
            primary["no_show_count"],
            1,
        )

        self.assertEqual(secondary["total_opens"], 0)
        self.assertEqual(
            secondary["conversion_rate"],
            0.0,
        )

        summary = result["summary"]

        self.assertEqual(summary["total_links"], 2)
        self.assertEqual(summary["active_links"], 2)
        self.assertEqual(summary["total_opens"], 4)
        self.assertEqual(
            summary["unique_visitors"],
            3,
        )
        self.assertEqual(
            summary["converted_count"],
            3,
        )
        self.assertEqual(
            summary["conversion_rate"],
            100.0,
        )
        self.assertEqual(
            summary["completed_count"],
            1,
        )
        self.assertEqual(
            summary["cancelled_count"],
            1,
        )
        self.assertEqual(
            summary["no_show_count"],
            1,
        )
        self.assertEqual(
            summary["best_link"]["id"],
            self.primary_link.pk,
        )

    def test_all_period_includes_old_events_but_30_days_excludes_them(self):
        old_event_at = (
            self.now - timedelta(days=45)
        )

        self.create_event(
            quick_link=self.secondary_link,
            event_type=(
                BOOKING_QUICK_LINK_OPENED_EVENT
            ),
            occurred_at=old_event_at,
            session_key="old-session",
        )

        recent_result = (
            build_booking_quick_link_stats(
                links_queryset=(
                    self.salon_queryset()
                ),
                period="30",
                now=self.now,
            )
        )

        all_result = build_booking_quick_link_stats(
            links_queryset=self.salon_queryset(),
            period="all",
            now=self.now,
        )

        recent_row = next(
            row
            for row in recent_result["links"]
            if row["id"] == self.secondary_link.pk
        )

        all_row = next(
            row
            for row in all_result["links"]
            if row["id"] == self.secondary_link.pk
        )

        self.assertEqual(
            recent_row["total_opens"],
            0,
        )
        self.assertEqual(
            all_row["total_opens"],
            1,
        )
        self.assertEqual(
            all_row["unique_visitors"],
            1,
        )

    def test_invalid_period_and_sort_fall_back_without_error(self):
        result = build_booking_quick_link_stats(
            links_queryset=self.salon_queryset(),
            period="invalid-range",
            sort="invalid-sort",
            now=self.now,
        )

        self.assertEqual(
            result["period"]["key"],
            "30",
        )
        self.assertEqual(
            result["sort"],
            "newest",
        )

        self.assertEqual(
            calculate_booking_quick_link_conversion_rate(
                converted_count=4,
                unique_visitors=0,
            ),
            0.0,
        )

    def test_queryset_scope_prevents_cross_salon_leak(self):
        self.create_event(
            quick_link=self.other_salon_link,
            event_type=(
                BOOKING_QUICK_LINK_OPENED_EVENT
            ),
            occurred_at=self.now,
            session_key="other-salon-session",
        )

        result = build_booking_quick_link_stats(
            links_queryset=self.salon_queryset(),
            period="all",
            now=self.now,
        )

        returned_ids = {
            row["id"]
            for row in result["links"]
        }

        self.assertNotIn(
            self.other_salon_link.pk,
            returned_ids,
        )

        self.assertEqual(
            result["summary"]["total_opens"],
            0,
        )

    def test_sorting_and_best_link_use_grouped_metrics(self):
        for index in range(3):
            self.create_event(
                quick_link=self.secondary_link,
                event_type=(
                    BOOKING_QUICK_LINK_OPENED_EVENT
                ),
                occurred_at=(
                    self.now
                    - timedelta(minutes=index)
                ),
                session_key=f"secondary-{index}",
            )

        secondary_order = self.create_order(
            quick_link=self.secondary_link,
            status="confirmed",
        )

        self.create_event(
            quick_link=self.secondary_link,
            event_type=(
                BOOKING_QUICK_LINK_CONVERTED_EVENT
            ),
            occurred_at=self.now,
            session_key="secondary-0",
            order=secondary_order,
        )

        for session_key in (
            "primary-a",
            "primary-b",
        ):
            self.create_event(
                quick_link=self.primary_link,
                event_type=(
                    BOOKING_QUICK_LINK_OPENED_EVENT
                ),
                occurred_at=self.now,
                session_key=session_key,
            )

        primary_order_one = self.create_order(
            quick_link=self.primary_link,
            status="confirmed",
        )

        primary_order_two = self.create_order(
            quick_link=self.primary_link,
            status="confirmed",
        )

        for order, session_key in (
            (primary_order_one, "primary-a"),
            (primary_order_two, "primary-b"),
        ):
            self.create_event(
                quick_link=self.primary_link,
                event_type=(
                    BOOKING_QUICK_LINK_CONVERTED_EVENT
                ),
                occurred_at=self.now,
                session_key=session_key,
                order=order,
            )

        result = build_booking_quick_link_stats(
            links_queryset=self.salon_queryset(),
            period="7",
            sort="conversions",
            now=self.now,
        )

        self.assertEqual(
            result["links"][0]["id"],
            self.primary_link.pk,
        )

        self.assertEqual(
            result["summary"]["best_link"]["id"],
            self.primary_link.pk,
        )

    def test_query_count_does_not_grow_with_number_of_links(self):
        additional_links = [
            self.create_link(
                title=f"لینک اضافه {index}"
            )
            for index in range(12)
        ]

        small_ids = [
            self.primary_link.pk,
            self.secondary_link.pk,
        ]

        ContentType.objects.clear_cache()

        with CaptureQueriesContext(
            connection
        ) as small_context:
            build_booking_quick_link_stats(
                links_queryset=(
                    BookingQuickLink.objects.filter(
                        pk__in=small_ids
                    )
                ),
                period="30",
                now=self.now,
            )

        ContentType.objects.clear_cache()

        with CaptureQueriesContext(
            connection
        ) as large_context:
            build_booking_quick_link_stats(
                links_queryset=(
                    BookingQuickLink.objects.filter(
                        pk__in=[
                            *small_ids,
                            *[
                                link.pk
                                for link
                                in additional_links
                            ],
                        ]
                    )
                ),
                period="30",
                now=self.now,
            )

        self.assertEqual(
            len(small_context),
            len(large_context),
        )

        self.assertLessEqual(
            len(large_context),
            4,
            msg=(
                "Quick-link stats must remain within "
                "a fixed grouped-query budget."
            ),
        )
