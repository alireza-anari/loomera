from __future__ import annotations

from datetime import time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Customer, CustomUser, SalonManager, Stylist
from apps.dashboards.forms import DashboardManualBookingForm
from apps.orders.models import Order, OrderDetail
from apps.salons.models import Salon
from apps.services.models import Services
from apps.stylists.models import StylistSchedule


class ManualBookingAvailabilityTests(TestCase):
    def setUp(self):
        self.onboarding_guard = patch(
            "apps.dashboards.views._redirect_to_required_onboarding",
            return_value=None,
        )
        self.onboarding_guard.start()
        self.addCleanup(self.onboarding_guard.stop)

        self.manager_user = CustomUser.objects.create(
            mobile_number="09121110001",
            name="مدیر",
            family="تست",
            is_active=True,
        )
        self.manager = SalonManager.objects.create(
            user=self.manager_user,
            is_active=True,
        )
        self.salon = Salon.objects.create(
            salon_name="مجموعه تست",
            salon_manager=self.manager,
            is_active=True,
            address="تهران",
        )
        stylist_user = CustomUser.objects.create(
            mobile_number="09121110002",
            name="متخصص",
            family="تست",
            is_active=True,
        )
        self.stylist = Stylist.objects.create(
            user=stylist_user,
            is_active=True,
            expert="تست",
            public_visibility=Stylist.PublicVisibility.HIDDEN,
        )
        customer_user = CustomUser.objects.create(
            mobile_number="09121110003",
            name="مشتری",
            family="تست",
            is_active=True,
        )
        self.customer = Customer.objects.create(
            user=customer_user,
            added_by_salon=self.salon,
        )
        self.service = Services.objects.create(
            service_name="خدمت تست",
            slug="manual-booking-availability-test",
            is_active=True,
            is_platform_catalog=True,
            duration_minutes=30,
            buffer_minutes=15,
            base_price=100000,
        )
        self.salon.stylists.add(self.stylist)
        self.salon.services.add(self.service)
        self.service.stylists.add(self.stylist)

        self.target_date = timezone.localdate() + timedelta(days=1)
        StylistSchedule.objects.create(
            salon=self.salon,
            stylist=self.stylist,
            service=self.service,
            date=self.target_date,
            start_time=time(10, 0),
            end_time=time(12, 0),
        )

    def test_manual_booking_form_accepts_slot_inside_schedule(self):
        form = DashboardManualBookingForm(
            data={
                "customer": str(self.customer.pk),
                "service": str(self.service.pk),
                "stylist": str(self.stylist.pk),
                "appointment_date": self.target_date.isoformat(),
                "start_time": "10:00",
                "notes": "",
            },
            salon=self.salon,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertEqual(form.cleaned_data["resolved_end_time"], time(10, 30))

    def test_manager_availability_returns_only_days_with_real_slots_even_for_hidden_stylist(self):
        self.client.force_login(self.manager_user)
        response = self.client.get(
            reverse(
                "dashboards:manual_booking_availability",
                kwargs={"salon_id": self.salon.pk},
            ),
            {
                "service_id": self.service.pk,
                "stylist_id": self.stylist.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["availability"]), 1)
        self.assertEqual(payload["availability"][0]["value"], self.target_date.isoformat())
        self.assertIn("10:00", payload["availability"][0]["times"])
        self.assertNotIn("11:30", payload["availability"][0]["times"])

    def test_existing_booking_is_removed_from_manager_availability(self):
        order = Order.objects.create(
            customer=self.customer,
            salon=self.salon,
            status="confirmed",
            is_finally=True,
            is_paid=False,
            total_amount=100000,
        )
        OrderDetail.objects.create(
            order=order,
            salon=self.salon,
            service=self.service,
            stylist=self.stylist,
            price=100000,
            date=self.target_date,
            time=time(10, 0),
            end_time=time(10, 30),
        )

        self.client.force_login(self.manager_user)
        response = self.client.get(
            reverse(
                "dashboards:manual_booking_availability",
                kwargs={"salon_id": self.salon.pk},
            ),
            {
                "service_id": self.service.pk,
                "stylist_id": self.stylist.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        times = response.json()["availability"][0]["times"]
        self.assertNotIn("10:00", times)
        self.assertNotIn("10:15", times)
        self.assertNotIn("10:30", times)
        self.assertIn("10:45", times)

    def test_foreign_manager_cannot_read_availability(self):
        foreign_user = CustomUser.objects.create(
            mobile_number="09121110004",
            name="مدیر",
            family="دیگر",
            is_active=True,
        )
        SalonManager.objects.create(user=foreign_user, is_active=True)
        self.client.force_login(foreign_user)

        response = self.client.get(
            reverse(
                "dashboards:manual_booking_availability",
                kwargs={"salon_id": self.salon.pk},
            ),
            {"service_id": self.service.pk, "stylist_id": self.stylist.pk},
        )

        self.assertEqual(response.status_code, 404)
