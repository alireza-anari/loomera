from __future__ import annotations

from datetime import date, datetime, time

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Customer, CustomUser, SalonManager, Stylist
from apps.help_center.actions.work_queries import (
    is_manager_read_query_candidate,
    is_stylist_read_query_candidate,
    run_manager_read_query,
    run_stylist_read_query,
)
from apps.orders.models import Order, OrderDetail
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus
from apps.services.models import Services
from apps.stylists.models import StylistSchedule


class LumiWorkQueryTests(TestCase):
    def setUp(self):
        self.today = date(2026, 8, 29)

        manager_user = CustomUser.objects.create_user(
            mobile_number="09120000001", name="مدیر", family="اول"
        )
        manager = SalonManager.objects.create(user=manager_user, is_active=True)
        self.salon = Salon.objects.create(
            salon_name="سالن اول", salon_manager=manager, is_active=True
        )

        manager2_user = CustomUser.objects.create_user(
            mobile_number="09120000002", name="مدیر", family="دوم"
        )
        manager2 = SalonManager.objects.create(user=manager2_user, is_active=True)
        self.other_salon = Salon.objects.create(
            salon_name="سالن دوم", salon_manager=manager2, is_active=True
        )

        self.service = Services.objects.create(
            service_name="کوتاهی مو", base_price=400000, duration_minutes=30
        )
        self.salon.services.add(self.service)
        self.other_salon.services.add(self.service)

        stylist_user = CustomUser.objects.create_user(
            mobile_number="09120000003", name="علی", family="رضایی"
        )
        self.stylist = Stylist.objects.create(user=stylist_user, is_active=True)
        SalonMembership.objects.create(
            salon=self.salon,
            stylist=self.stylist,
            status=SalonMembershipStatus.ACTIVE,
        )

        customer_user = CustomUser.objects.create_user(
            mobile_number="09120000004", name="مریم", family="احمدی"
        )
        self.customer = Customer.objects.create(user=customer_user)

    def _appointment(self, *, salon, stylist, day, at, status="confirmed"):
        order = Order.objects.create(
            customer=self.customer,
            salon=salon,
            status=status,
            is_finally=True,
        )
        return OrderDetail.objects.create(
            order=order,
            service=self.service,
            stylist=stylist,
            salon=salon,
            price=400000,
            date=day,
            time=at,
        )

    def test_candidates_cover_beta_read_queries(self):
        self.assertTrue(is_manager_read_query_candidate("امروز چند تا نوبت داریم؟"))
        self.assertTrue(is_manager_read_query_candidate("علی فردا چه ساعتی کار میکنه؟"))
        self.assertTrue(is_stylist_read_query_candidate("نوبت‌های فردام رو نشون بده"))
        self.assertTrue(is_stylist_read_query_candidate("امروز تا چه ساعتی کار دارم؟"))
        self.assertFalse(is_stylist_read_query_candidate("برای فردا مرخصی ثبت کن"))

    def test_manager_count_is_cross_salon_isolated(self):
        self._appointment(
            salon=self.salon, stylist=self.stylist, day=self.today, at=time(10, 0)
        )
        self._appointment(
            salon=self.other_salon, stylist=self.stylist, day=self.today, at=time(11, 0)
        )
        result = run_manager_read_query(
            salon=self.salon,
            message="امروز چند تا نوبت داریم؟",
            today=self.today,
        )
        self.assertEqual(result["result"]["count"], 1)

    def test_manager_duplicate_name_returns_ambiguity(self):
        for mobile, family in (("09120000005", "احمدی"), ("09120000006", "کریمی")):
            user = CustomUser.objects.create_user(
                mobile_number=mobile, name="سارا", family=family
            )
            stylist = Stylist.objects.create(user=user, is_active=True)
            SalonMembership.objects.create(
                salon=self.salon,
                stylist=stylist,
                status=SalonMembershipStatus.ACTIVE,
            )

        result = run_manager_read_query(
            salon=self.salon,
            message="نوبت بعدی سارا کیه؟",
            today=self.today,
            now=timezone.make_aware(datetime(2026, 8, 29, 9, 0)),
        )
        self.assertEqual(result["result"]["type"], "ambiguity")
        self.assertEqual(len(result["result"]["items"]), 2)
        self.assertIn("نام کامل", result["answer"])

    def test_stylist_count_never_includes_another_stylist(self):
        other_user = CustomUser.objects.create_user(
            mobile_number="09120000007", name="رضا", family="محمدی"
        )
        other_stylist = Stylist.objects.create(user=other_user, is_active=True)
        SalonMembership.objects.create(
            salon=self.salon,
            stylist=other_stylist,
            status=SalonMembershipStatus.ACTIVE,
        )
        self._appointment(
            salon=self.salon, stylist=self.stylist, day=self.today, at=time(10, 0)
        )
        self._appointment(
            salon=self.salon, stylist=other_stylist, day=self.today, at=time(11, 0)
        )

        result = run_stylist_read_query(
            salon=self.salon,
            stylist=self.stylist,
            message="امروز چند تا نوبت دارم؟",
            today=self.today,
        )
        self.assertEqual(result["result"]["count"], 1)

    def test_stylist_schedule_is_salon_scoped(self):
        StylistSchedule.objects.create(
            salon=self.salon,
            stylist=self.stylist,
            date=self.today,
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
        StylistSchedule.objects.create(
            salon=self.other_salon,
            stylist=self.stylist,
            date=self.today,
            start_time=time(18, 0),
            end_time=time(22, 0),
        )

        result = run_stylist_read_query(
            salon=self.salon,
            stylist=self.stylist,
            message="امروز تا چه ساعتی کار دارم؟",
            today=self.today,
        )
        self.assertEqual(result["result"]["end_time"], "17:00")
        self.assertNotIn("22:00", result["answer"])
