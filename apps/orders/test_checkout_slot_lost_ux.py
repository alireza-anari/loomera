from __future__ import annotations

from datetime import timedelta

from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.orders.models import Order
from apps.orders.views import _CHECKOUT_SLOT_LOST_SESSION_KEY
from tests_stage1_helpers import Stage1DomainFactoryMixin


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    ONLINE_PAYMENT_ENABLED=False,
    PAYMENT_MODE="mock",
)
class CheckoutSlotLostUXTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.customer = self.make_customer(password="StrongPass123!")
        self.other_customer = self.make_customer(password="StrongPass123!")
        self.manager = self.make_salon_manager()
        self.stylist = self.make_stylist()
        self.service = self.make_service(name="اصلاح مو", duration_minutes=30)
        self.salon = self.make_salon(manager=self.manager)
        self.connect_service(
            salon=self.salon,
            stylist=self.stylist,
            service=self.service,
            price=120_000,
        )

        self.target_date = timezone.localdate() + timedelta(days=3)
        self.add_schedule(
            stylist=self.stylist,
            salon=self.salon,
            service=self.service,
            date_value=self.target_date,
            start=timezone.datetime.strptime("10:00", "%H:%M").time(),
            end=timezone.datetime.strptime("14:00", "%H:%M").time(),
        )

    def _prepare_checkout_session(self):
        session = self.client.session
        session["salon_id"] = self.salon.id
        session["stylist_selections"] = [
            {
                "serviceId": self.service.id,
                "stylistId": str(self.stylist.user_id),
                "stylistName": self.stylist.get_fullName(),
                "requestedStylistId": str(self.stylist.user_id),
                "requestedStylistName": self.stylist.get_fullName(),
            }
        ]
        session["datetime_selections"] = {
            f"{self.stylist.user_id}_{self.service.id}": {
                "date": self.target_date.isoformat(),
                "time": "10:00",
            }
        }
        session.save()

    def _create_conflicting_booking(self):
        order = self.make_order(
            customer=self.other_customer,
            salon=self.salon,
            status="pending",
            selected_payment_method="pay_in_salon",
        )
        self.make_order_detail(
            order=order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.target_date,
            start=timezone.datetime.strptime("10:00", "%H:%M").time(),
            end=timezone.datetime.strptime("10:30", "%H:%M").time(),
        )
        return order

    def test_checkout_slot_conflict_redirects_to_datetime_with_persistent_notice(self):
        self.client.force_login(self.customer.user)
        self._prepare_checkout_session()
        self._create_conflicting_booking()

        response = self.client.post(
            reverse("orders:checkout"),
            data={
                "form_action": "confirm_checkout",
                "coupon_code": "",
                "payment_method": "pay_in_salon",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response["Location"].endswith(reverse("orders:select_dateTime"))
        )
        self.assertEqual(Order.objects.filter(customer=self.customer).count(), 0)

        session = self.client.session
        self.assertIn(_CHECKOUT_SLOT_LOST_SESSION_KEY, session)
        notice = session[_CHECKOUT_SLOT_LOST_SESSION_KEY]
        self.assertEqual(notice["title"], "این زمان همین الان پر شد")
        self.assertIn("دیگر آزاد نیست", notice["message"])

        flashed_messages = [str(item) for item in get_messages(response.wsgi_request)]
        self.assertTrue(
            any("زمان انتخاب‌شده دیگر آزاد نیست" in item for item in flashed_messages)
        )

    def test_slot_lost_notice_is_rendered_once_on_datetime_page(self):
        self.client.force_login(self.customer.user)
        self._prepare_checkout_session()

        session = self.client.session
        session[_CHECKOUT_SLOT_LOST_SESSION_KEY] = {
            "title": "این زمان همین الان پر شد",
            "message": "زمان ۱۰:۰۰ تا ۱۰:۳۰ دیگر آزاد نیست.",
            "hint": "انتخاب‌های خدمت و متخصص حفظ شده‌اند؛ فقط یک زمان آزاد جدید انتخاب کن.",
            "action_label": "انتخاب زمان جدید",
        }
        session.save()

        first_response = self.client.get(reverse("orders:select_dateTime"))

        self.assertEqual(first_response.status_code, 200)
        self.assertContains(first_response, "این زمان همین الان پر شد")
        self.assertContains(first_response, "انتخاب زمان جدید")
        self.assertNotIn(_CHECKOUT_SLOT_LOST_SESSION_KEY, self.client.session)

        second_response = self.client.get(reverse("orders:select_dateTime"))

        self.assertEqual(second_response.status_code, 200)
        self.assertNotContains(second_response, "این زمان همین الان پر شد")
