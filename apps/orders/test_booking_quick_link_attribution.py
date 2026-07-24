from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.accounts.models import Customer, SalonManager, Stylist
from apps.analytics.models import AnalyticsEvent
from apps.orders.models import BookingQuickLink, Order, OrderDetail
from apps.orders.quick_links import (
    BOOKING_QUICK_LINK_CONVERTED_EVENT,
    consume_booking_quick_link_from_session,
    mark_booking_quick_link_converted,
)
from apps.salons.models import Salon
from apps.services.models import Services


User = get_user_model()


class BookingQuickLinkAttributionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = User.objects.create_user(
            mobile_number="09129992001",
            password="test-pass-123",
            name="مدیر",
            family="انتساب",
        )
        cls.manager_user.is_active = True
        cls.manager_user.save(update_fields=["is_active"])

        cls.manager = SalonManager.objects.create(
            user=cls.manager_user,
            is_active=True,
        )

        cls.salon = Salon.objects.create(
            salon_name="سالن انتساب لینک",
            salon_manager=cls.manager,
            is_active=True,
        )

        cls.other_salon = Salon.objects.create(
            salon_name="سالن دیگر انتساب",
            salon_manager=cls.manager,
            is_active=True,
        )

        cls.service = Services.objects.create(
            service_name="خدمت انتساب لینک",
            is_active=True,
            duration_minutes=30,
            base_price=100000,
        )
        cls.other_service = Services.objects.create(
            service_name="خدمت دیگر انتساب",
            is_active=True,
            duration_minutes=30,
            base_price=120000,
        )

        cls.salon.services.add(cls.service, cls.other_service)
        cls.other_salon.services.add(cls.service)

        cls.stylist_user = User.objects.create_user(
            mobile_number="09129992002",
            password="test-pass-123",
            name="متخصص",
            family="انتساب",
        )
        cls.stylist = Stylist.objects.create(
            user=cls.stylist_user,
            is_active=True,
        )
        cls.salon.stylists.add(cls.stylist)
        cls.other_salon.stylists.add(cls.stylist)
        cls.service.stylists.add(cls.stylist)
        cls.other_service.stylists.add(cls.stylist)

        cls.customer_user = User.objects.create_user(
            mobile_number="09129992003",
            password="test-pass-123",
            name="مشتری",
            family="انتساب",
        )
        cls.customer = Customer.objects.create(user=cls.customer_user)

    def build_request(self):
        request = RequestFactory().get("/")
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        return request

    def create_quick_link(self, **overrides):
        values = {
            "creator": self.manager_user,
            "salon": self.salon,
            "service": self.service,
            "stylist": self.stylist,
            "mode": BookingQuickLink.Mode.SERVICE_STYLIST,
            "placement": BookingQuickLink.Placement.MIRROR_LABEL,
            "campaign_name": "کمپین آینه",
            "is_permanent": True,
            "payload": {
                "mode": BookingQuickLink.Mode.SERVICE_STYLIST,
                "salon_id": self.salon.pk,
                "service_ids": [self.service.pk],
                "stylist_user_id": self.stylist.pk,
                "date": "",
                "time": "",
                "summary": {},
            },
        }
        values.update(overrides)
        return BookingQuickLink.objects.create(**values)

    def create_order(
        self,
        *,
        salon=None,
        service=None,
        is_finally=True,
        status="pending",
        quick_link=None,
    ):
        salon = salon or self.salon
        service = service or self.service

        order = Order.objects.create(
            customer=self.customer,
            salon=salon,
            status=status,
            is_finally=is_finally,
            is_paid=False,
            selected_payment_method="pay_in_salon",
            booking_quick_link=quick_link,
        )

        OrderDetail.objects.create(
            order=order,
            service=service,
            stylist=self.stylist,
            salon=salon,
            price=100000,
            date=date.today() + timedelta(days=1),
            time=time(10, 0),
            end_time=time(10, 30),
        )

        return order

    def test_session_link_is_attached_without_early_conversion(self):
        quick_link = self.create_quick_link()
        order = self.create_order(is_finally=False)
        request = self.build_request()
        request.session["booking_quick_link_id"] = quick_link.pk

        result = consume_booking_quick_link_from_session(
            request,
            order,
        )

        order.refresh_from_db()
        quick_link.refresh_from_db()

        self.assertEqual(result.pk, quick_link.pk)
        self.assertEqual(order.booking_quick_link_id, quick_link.pk)
        self.assertEqual(quick_link.bookings_count, 0)
        self.assertIsNone(quick_link.last_converted_at)
        self.assertNotIn(
            "booking_quick_link_id",
            request.session,
        )
        self.assertFalse(
            AnalyticsEvent.objects.filter(
                event_type=BOOKING_QUICK_LINK_CONVERTED_EVENT,
                order=order,
            ).exists()
        )

    def test_cross_salon_session_link_is_not_attributed(self):
        quick_link = self.create_quick_link()
        order = self.create_order(salon=self.other_salon)
        request = self.build_request()
        request.session["booking_quick_link_id"] = quick_link.pk

        result = consume_booking_quick_link_from_session(
            request,
            order,
        )

        order.refresh_from_db()
        quick_link.refresh_from_db()

        self.assertIsNone(result)
        self.assertIsNone(order.booking_quick_link_id)
        self.assertEqual(quick_link.bookings_count, 0)
        self.assertNotIn(
            "booking_quick_link_id",
            request.session,
        )

    def test_service_mismatch_is_not_attributed(self):
        quick_link = self.create_quick_link()
        order = self.create_order(service=self.other_service)
        request = self.build_request()
        request.session["booking_quick_link_id"] = quick_link.pk

        result = consume_booking_quick_link_from_session(
            request,
            order,
        )

        order.refresh_from_db()

        self.assertIsNone(result)
        self.assertIsNone(order.booking_quick_link_id)

    def test_conversion_is_atomic_and_idempotent_per_order(self):
        quick_link = self.create_quick_link(
            opens_count=4,
            bookings_count=0,
        )
        order = self.create_order(quick_link=quick_link)

        first_result = mark_booking_quick_link_converted(order)
        second_result = mark_booking_quick_link_converted(order)

        quick_link.refresh_from_db()

        content_type = ContentType.objects.get_for_model(
            BookingQuickLink,
            for_concrete_model=False,
        )

        events = AnalyticsEvent.objects.filter(
            event_type=BOOKING_QUICK_LINK_CONVERTED_EVENT,
            order=order,
            target_content_type=content_type,
            target_object_id=quick_link.pk,
        )

        self.assertEqual(first_result.pk, quick_link.pk)
        self.assertEqual(second_result.pk, quick_link.pk)
        self.assertEqual(quick_link.opens_count, 4)
        self.assertEqual(quick_link.bookings_count, 1)
        self.assertEqual(quick_link.used_order_id, order.pk)
        self.assertIsNotNone(quick_link.last_converted_at)
        self.assertEqual(events.count(), 1)

        event = events.get()
        self.assertEqual(event.category, "appointment")
        self.assertEqual(event.salon_id, self.salon.pk)
        self.assertEqual(event.actor_id, self.customer_user.pk)
        self.assertEqual(
            event.source,
            BookingQuickLink.Placement.MIRROR_LABEL,
        )
        self.assertEqual(
            event.metadata["campaign_name"],
            "کمپین آینه",
        )

    def test_pending_online_order_is_not_converted(self):
        quick_link = self.create_quick_link()
        order = self.create_order(
            quick_link=quick_link,
            is_finally=False,
            status="pending",
        )

        result = mark_booking_quick_link_converted(order)

        quick_link.refresh_from_db()

        self.assertIsNone(result)
        self.assertEqual(quick_link.bookings_count, 0)
        self.assertIsNone(quick_link.last_converted_at)
        self.assertFalse(
            AnalyticsEvent.objects.filter(
                event_type=BOOKING_QUICK_LINK_CONVERTED_EVENT,
                order=order,
            ).exists()
        )

    def test_non_permanent_link_is_disabled_after_conversion(self):
        quick_link = self.create_quick_link(
            is_permanent=False,
        )
        order = self.create_order(quick_link=quick_link)

        mark_booking_quick_link_converted(order)

        quick_link.refresh_from_db()

        self.assertEqual(quick_link.bookings_count, 1)
        self.assertFalse(quick_link.is_active)
        self.assertIsNotNone(quick_link.used_at)
        self.assertEqual(
            quick_link.disabled_at,
            quick_link.used_at,
        )
        self.assertEqual(quick_link.used_order_id, order.pk)

    def test_legacy_mark_used_wrapper_is_idempotent(self):
        quick_link = self.create_quick_link()
        order = self.create_order()

        quick_link.mark_used(order)
        quick_link.mark_used(order)

        order.refresh_from_db()
        quick_link.refresh_from_db()

        self.assertEqual(order.booking_quick_link_id, quick_link.pk)
        self.assertEqual(quick_link.bookings_count, 1)
        self.assertEqual(
            AnalyticsEvent.objects.filter(
                event_type=BOOKING_QUICK_LINK_CONVERTED_EVENT,
                order=order,
            ).count(),
            1,
        )
