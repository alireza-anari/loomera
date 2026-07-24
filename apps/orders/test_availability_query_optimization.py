from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.orders.booking_utils import get_available_slots_for_service
from tests_stage1_helpers import Stage1DomainFactoryMixin


class AvailabilityQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.target_date = timezone.localdate() + timedelta(days=2)

        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(manager=self.manager)

        self.service = self.make_service(
            name="خدمت بهینه‌سازی زمان آزاد",
            duration_minutes=30,
            buffer_minutes=10,
            is_active=True,
        )
        self.stylist = self.make_stylist()

        self.connect_service(
            salon=self.salon,
            stylist=self.stylist,
            service=self.service,
        )

        self.schedule = self.add_schedule(
            stylist=self.stylist,
            salon=self.salon,
            service=self.service,
            date_value=self.target_date,
            start=time(9, 0),
            end=time(13, 0),
        )

    def _slots(self):
        return get_available_slots_for_service(
            salon=self.salon,
            stylist=self.stylist,
            service=self.service,
            date_value=self.target_date,
        )

    def test_available_slots_use_three_queries(self):
        with self.assertNumQueries(3):
            slots = self._slots()

        self.assertGreater(len(slots), 1)
        self.assertIn(
            (time(9, 0), time(9, 30)),
            slots,
        )

    def test_query_count_does_not_grow_with_more_candidate_slots(self):
        self.schedule.start_time = time(8, 0)
        self.schedule.end_time = time(18, 0)
        self.schedule.save(
            update_fields=[
                "start_time",
                "end_time",
            ]
        )

        with self.assertNumQueries(3):
            slots = self._slots()

        self.assertGreater(len(slots), 20)

    def test_leave_and_booking_windows_preserve_slot_results(self):
        self.add_time_off(
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.target_date,
            start=time(9, 30),
            end=time(10, 15),
        )

        customer = self.make_customer()
        order = self.make_order(
            customer=customer,
            salon=self.salon,
            is_paid=False,
            is_finally=True,
        )
        self.make_order_detail(
            order=order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.target_date,
            start=time(11, 0),
            end=time(11, 30),
            occupied_until=time(11, 40),
        )

        with self.assertNumQueries(3):
            slots = self._slots()

        # The displayed service interval ends at 09:30, but its 10-minute buffer
        # keeps the stylist occupied until 09:40, overlapping the 09:30 time-off.
        self.assertNotIn(
            (time(9, 0), time(9, 30)),
            slots,
        )

        self.assertNotIn(
            (time(9, 30), time(10, 0)),
            slots,
        )
        self.assertNotIn(
            (time(10, 0), time(10, 30)),
            slots,
        )

        self.assertNotIn(
            (time(11, 0), time(11, 30)),
            slots,
        )
        self.assertNotIn(
            (time(11, 15), time(11, 45)),
            slots,
        )

        self.assertIn(
            (time(11, 45), time(12, 15)),
            slots,
        )
