from __future__ import annotations

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import (
    Customer,
    SalonManager,
    Stylist,
)
from apps.analytics.models import AnalyticsEvent
from apps.dashboards.views import (
    _generate_stylist_quick_link,
)
from apps.orders.models import (
    BookingQuickLink,
    Order,
    OrderDetail,
)
from apps.orders.quick_links import (
    BOOKING_QUICK_LINK_CONVERTED_EVENT,
    BOOKING_QUICK_LINK_OPENED_EVENT,
    BOOKING_QUICK_LINK_STARTED_EVENT,
    consume_booking_quick_link_from_session,
    mark_booking_quick_link_converted,
    normalize_booking_payload,
    record_booking_quick_link_started,
)
from apps.salons.models import (
    Salon,
    SalonMembership,
    SalonMembershipStatus,
)
from apps.services.models import Services


User = get_user_model()


class SalonHomeQuickLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = User.objects.create_user(
            mobile_number="09125554001",
            password="test-pass-123",
            name="مدیر",
            family="لینک سالن",
        )
        cls.manager_user.is_active = True
        cls.manager_user.save(
            update_fields=["is_active"]
        )

        cls.other_manager_user = User.objects.create_user(
            mobile_number="09125554002",
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
            salon_name="سالن لینک صفحه اصلی",
            salon_manager=cls.manager,
            is_active=True,
        )
        cls.other_salon = Salon.objects.create(
            salon_name="سالن خارج از لینک",
            salon_manager=cls.other_manager,
            is_active=True,
        )

        cls.stylist_user = User.objects.create_user(
            mobile_number="09125554003",
            password="test-pass-123",
            name="متخصص",
            family="لینک سالن",
        )
        cls.stylist_user.is_active = True
        cls.stylist_user.save(
            update_fields=["is_active"]
        )

        cls.stylist = Stylist.objects.create(
            user=cls.stylist_user,
            expert="مو",
            is_active=True,
        )
        cls.salon.stylists.add(cls.stylist)

        cls.service = Services.objects.create(
            service_name="خدمت لینک سالن",
            is_active=True,
            duration_minutes=30,
            base_price=100000,
        )
        cls.salon.services.add(cls.service)
        cls.service.stylists.add(cls.stylist)

        SalonMembership.objects.create(
            salon=cls.salon,
            stylist=cls.stylist,
            status=SalonMembershipStatus.ACTIVE,
        )

        cls.customer_user = User.objects.create_user(
            mobile_number="09125554004",
            password="test-pass-123",
            name="مشتری",
            family="لینک سالن",
        )
        cls.customer = Customer.objects.create(
            user=cls.customer_user
        )

    def create_salon_link(
        self,
        *,
        is_permanent=True,
    ):
        payload = normalize_booking_payload(
            {
                "mode": BookingQuickLink.Mode.SALON,
                "salon_id": self.salon.pk,
                "summary": {
                    "service": "صفحه اصلی سالن",
                    "stylist": "—",
                    "date": "—",
                    "time": "—",
                },
            }
        )

        return BookingQuickLink.objects.create(
            creator=self.manager_user,
            salon=self.salon,
            service=None,
            stylist=None,
            title=(
                f"صفحه اصلی {self.salon.salon_name}"
            ),
            mode=BookingQuickLink.Mode.SALON,
            placement=(
                BookingQuickLink.Placement.DIRECT
            ),
            campaign_name="کمپین صفحه سالن",
            payload=payload,
            is_permanent=is_permanent,
        )

    def request_with_link(self, quick_link):
        request = RequestFactory().post(
            "/booking-start/"
        )
        middleware = SessionMiddleware(
            lambda current_request: None
        )
        middleware.process_request(request)
        request.session[
            "booking_quick_link_id"
        ] = quick_link.pk
        request.session.save()
        request.user = AnonymousUser()
        request.META["REMOTE_ADDR"] = (
            "127.0.0.1"
        )
        return request

    def create_order(self, *, salon=None):
        salon = salon or self.salon

        order = Order.objects.create(
            customer=self.customer,
            salon=salon,
            selected_payment_method=(
                "pay_in_salon"
            ),
        )

        if salon.pk == self.salon.pk:
            OrderDetail.objects.create(
                order=order,
                service=self.service,
                stylist=self.stylist,
                salon=self.salon,
                price=100000,
                date=(
                    timezone.localdate()
                    + timedelta(days=1)
                ),
                time=time(10, 0),
                end_time=time(10, 30),
            )

        return order

    def test_model_and_normalizer_accept_salon_mode(self):
        self.assertEqual(
            BookingQuickLink.Mode.SALON,
            "salon",
        )

        payload = normalize_booking_payload(
            {
                "mode": "salon",
                "salon_id": self.salon.pk,
            }
        )

        self.assertEqual(
            payload["mode"],
            BookingQuickLink.Mode.SALON,
        )
        self.assertEqual(
            payload["salon_id"],
            self.salon.pk,
        )
        self.assertEqual(
            payload["service_ids"],
            [],
        )
        self.assertIsNone(
            payload["stylist_user_id"]
        )

    def test_manager_can_create_salon_home_link(self):
        client = Client()
        client.force_login(self.manager_user)

        response = client.post(
            reverse("dashboards:quick_links"),
            {
                "quick_link_mode": "salon",
                "service_id": "",
                "stylist_id": "",
                "appointment_date": "",
                "appointment_time": "",
                "quick_link_title": "",
                "placement": (
                    BookingQuickLink
                    .Placement
                    .MIRROR_LABEL
                ),
                "campaign_name": (
                    "لیبل صفحه سالن"
                ),
                "internal_note": (
                    "تست لینک عمومی سالن"
                ),
                "is_permanent": "on",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        quick_link = (
            BookingQuickLink.objects.get(
                salon=self.salon,
                mode=(
                    BookingQuickLink.Mode.SALON
                ),
            )
        )

        self.assertIsNone(
            quick_link.service_id
        )
        self.assertIsNone(
            quick_link.stylist_id
        )
        self.assertEqual(
            quick_link.payload["service_ids"],
            [],
        )
        self.assertIsNone(
            quick_link.payload[
                "stylist_user_id"
            ]
        )
        self.assertEqual(
            quick_link.title,
            f"صفحه اصلی {self.salon.salon_name}",
        )
        self.assertTrue(
            quick_link.is_permanent
        )

    def test_manager_form_contains_salon_mode(self):
        client = Client()
        client.force_login(self.manager_user)

        response = client.get(
            reverse("dashboards:quick_links")
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertContains(
            response,
            'value="salon"',
        )
        self.assertContains(
            response,
            "صفحه اصلی سالن",
        )

    def test_stylist_generator_rejects_salon_mode(self):
        request = RequestFactory().post(
            "/stylist-links/",
            {
                "quick_link_mode": "salon",
            },
        )
        request.user = self.stylist_user

        generated_link, payload, errors = (
            _generate_stylist_quick_link(
                request,
                self.salon,
                self.stylist,
            )
        )

        self.assertIsNone(generated_link)
        self.assertEqual(
            payload["mode"],
            "salon",
        )
        self.assertTrue(errors)
        self.assertFalse(
            BookingQuickLink.objects.filter(
                creator=self.stylist_user,
                mode=(
                    BookingQuickLink.Mode.SALON
                ),
            ).exists()
        )

    def test_entry_records_open_and_redirects_to_salon(self):
        quick_link = self.create_salon_link()
        client = Client()

        response = client.get(
            reverse(
                "orders:quick_booking_entry",
                kwargs={
                    "token": str(
                        quick_link.token
                    )
                },
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )
        self.assertEqual(
            response.url,
            self.salon.get_absolute_url(),
        )
        self.assertEqual(
            client.session.get(
                "booking_quick_link_id"
            ),
            quick_link.pk,
        )

        quick_link.refresh_from_db()

        self.assertEqual(
            quick_link.opens_count,
            1,
        )
        self.assertEqual(
            AnalyticsEvent.objects.filter(
                event_type=(
                    BOOKING_QUICK_LINK_OPENED_EVENT
                ),
                target_object_id=quick_link.pk,
            ).count(),
            1,
        )

    def test_started_and_conversion_work_for_any_service_in_salon(self):
        quick_link = self.create_salon_link()
        request = self.request_with_link(
            quick_link
        )

        first_event = (
            record_booking_quick_link_started(
                request=request
            )
        )
        second_event = (
            record_booking_quick_link_started(
                request=request
            )
        )

        self.assertEqual(
            first_event.pk,
            second_event.pk,
        )
        self.assertEqual(
            AnalyticsEvent.objects.filter(
                event_type=(
                    BOOKING_QUICK_LINK_STARTED_EVENT
                ),
                target_object_id=quick_link.pk,
            ).count(),
            1,
        )

        order = self.create_order()

        attributed = (
            consume_booking_quick_link_from_session(
                request,
                order,
            )
        )

        self.assertEqual(
            attributed.pk,
            quick_link.pk,
        )

        order.refresh_from_db()

        self.assertEqual(
            order.booking_quick_link_id,
            quick_link.pk,
        )

        order.is_finally = True
        order.save(
            update_fields=["is_finally"]
        )

        converted = (
            mark_booking_quick_link_converted(
                order
            )
        )

        self.assertEqual(
            converted.pk,
            quick_link.pk,
        )
        self.assertEqual(
            AnalyticsEvent.objects.filter(
                event_type=(
                    BOOKING_QUICK_LINK_CONVERTED_EVENT
                ),
                order=order,
                target_object_id=quick_link.pk,
            ).count(),
            1,
        )

    def test_salon_mode_rejects_order_from_other_salon(self):
        quick_link = self.create_salon_link()
        request = self.request_with_link(
            quick_link
        )
        order = self.create_order(
            salon=self.other_salon
        )

        attributed = (
            consume_booking_quick_link_from_session(
                request,
                order,
            )
        )

        self.assertIsNone(attributed)

        order.refresh_from_db()

        self.assertIsNone(
            order.booking_quick_link_id
        )
