from __future__ import annotations

from datetime import time

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser, Customer, SalonManager, Stylist
from apps.orders.models import Order, OrderDetail
from apps.salons.models import Salon
from apps.services.models import GroupServices, Services


class AppointmentICSSecurityTests(TestCase):
    def _user(self, *, mobile, name="کاربر", family="تست"):
        return CustomUser.objects.create(
            mobile_number=mobile,
            name=name,
            family=family,
            is_active=True,
        )

    def _customer(self, *, mobile="09125000001"):
        user = self._user(mobile=mobile, name="مشتری", family="تست")
        return Customer.objects.create(user=user)

    def _manager(self, *, mobile="09125000002"):
        user = self._user(mobile=mobile, name="مدیر", family="سالن")
        return SalonManager.objects.create(user=user, is_active=True)

    def _salon(self, *, name="سالن تست", address="تهران"):
        return Salon.objects.create(
            salon_name=name,
            salon_manager=self._manager(),
            is_active=True,
            address=address,
        )

    def _group(self):
        return GroupServices.objects.create(
            group_title="گروه تست",
            slug="test-group",
            group_image="test/group.jpg",
            is_active=True,
        )

    def _service(self, group, *, name="خدمت تست"):
        service = Services.objects.create(
            service_name=name,
            slug="test-service",
            is_active=True,
            is_platform_catalog=True,
            duration_minutes=30,
            base_price=100000,
        )
        service.service_group.add(group)
        return service

    def _stylist(self, salon, service, *, mobile="09125000003", name="متخصص"):
        stylist = Stylist.objects.create(
            user=self._user(mobile=mobile, name=name, family="تست"),
            is_active=True,
            expert="تست",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )
        salon.stylists.add(stylist)
        service.stylists.add(stylist)
        return stylist

    def _appointment(
        self,
        *,
        customer=None,
        salon_name="سالن تست",
        service_name="خدمت تست",
        address="تهران",
    ):
        customer = customer or self._customer()
        salon = self._salon(name=salon_name, address=address)
        group = self._group()
        service = self._service(group, name=service_name)
        salon.services.add(service)
        stylist = self._stylist(salon, service)

        order = Order.objects.create(
            customer=customer,
            salon=salon,
            status="completed",
            is_finally=True,
            is_paid=True,
            total_amount=100000,
        )

        appointment = OrderDetail.objects.create(
            order=order,
            service=service,
            stylist=stylist,
            salon=salon,
            price=100000,
            date=timezone.localdate(),
            time=time(10, 0),
            end_time=time(10, 30),
        )
        return appointment

    def test_ics_requires_owner(self):
        owner = self._customer(mobile="09125000101")
        other = self._customer(mobile="09125000102")
        appointment = self._appointment(customer=owner)

        self.client.force_login(other.user)

        response = self.client.get(
            reverse("orders:appointment_ics", kwargs={"pk": appointment.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_ics_returns_calendar_for_owner(self):
        customer = self._customer(mobile="09125000103")
        appointment = self._appointment(customer=customer)

        self.client.force_login(customer.user)

        response = self.client.get(
            reverse("orders:appointment_ics", kwargs={"pk": appointment.pk})
        )

        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")

        self.assertIn("BEGIN:VCALENDAR", body)
        self.assertIn("BEGIN:VEVENT", body)
        self.assertIn("END:VCALENDAR", body)
        self.assertIn("text/calendar", response["Content-Type"])

    @override_settings(
        BRAND_DOMAIN="loomera.local\r\nX-INJECTED:1",
        LOOMERA_CALENDAR_NAME="Loomera\r\nX-CAL-INJECTED:1",
        LOOMERA_CALENDAR_PRODID="-//Loomera//\r\nX-PROD-INJECTED:1",
    )
    def test_ics_escapes_crlf_injection(self):
        customer = self._customer(mobile="09125000104")
        appointment = self._appointment(
            customer=customer,
            salon_name="سالن تست\r\nATTENDEE:evil@example.com",
            service_name="خدمت تست\r\nX-EVIL:1",
            address="تهران\r\nURL:https://evil.example",
        )

        self.client.force_login(customer.user)

        response = self.client.get(
            reverse("orders:appointment_ics", kwargs={"pk": appointment.pk})
        )

        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")

        self.assertNotIn("\r\nATTENDEE:", body)
        self.assertNotIn("\r\nX-EVIL:", body)
        self.assertNotIn("\r\nURL:https://evil.example", body)
        self.assertNotIn("\r\nX-INJECTED:", body)
        self.assertNotIn("\r\nX-CAL-INJECTED:", body)
        self.assertNotIn("\r\nX-PROD-INJECTED:", body)

    @override_settings(APPOINTMENT_ICS_TEXT_MAX_CHARS=20)
    def test_ics_limits_long_text_fields(self):
        customer = self._customer(mobile="09125000105")
        long_address = "الف" * 200
        appointment = self._appointment(
            customer=customer,
            salon_name="سالن تست طولانی",
            service_name="خدمت تست طولانی",
            address=long_address,
        )

        self.client.force_login(customer.user)

        response = self.client.get(
            reverse("orders:appointment_ics", kwargs={"pk": appointment.pk})
        )

        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")

        self.assertNotIn("الف" * 100, body)
