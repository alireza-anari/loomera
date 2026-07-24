from __future__ import annotations

import json
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser, SalonManager, Stylist
from apps.salons.models import Salon
from apps.services.models import GroupServices, Services


class BookingSessionSecurityTests(TestCase):
    def _user(self, *, mobile, name="کاربر", family="تست"):
        return CustomUser.objects.create(
            mobile_number=mobile,
            name=name,
            family=family,
            is_active=True,
        )

    def _manager(self, *, mobile="09123000001"):
        return SalonManager.objects.create(
            user=self._user(mobile=mobile, name="مدیر", family="سالن"),
            is_active=True,
        )

    def _salon(self, *, name="سالن تست", is_active=True, mobile="09123000002"):
        return Salon.objects.create(
            salon_name=name,
            salon_manager=self._manager(mobile=mobile),
            is_active=is_active,
            address="تهران",
        )

    def _group(self, title="گروه تست", *, is_active=True):
        return GroupServices.objects.create(
            group_title=title,
            slug=title.replace(" ", "-"),
            group_image="test/group.jpg",
            is_active=is_active,
        )

    def _service(
        self,
        name="خدمت تست",
        *,
        group=None,
        is_active=True,
        is_platform_catalog=True,
    ):
        service = Services.objects.create(
            service_name=name,
            slug=name.replace(" ", "-"),
            is_active=is_active,
            is_platform_catalog=is_platform_catalog,
            duration_minutes=30,
            base_price=100000,
        )
        if group is not None:
            service.service_group.add(group)
        return service

    def _stylist(
        self,
        *,
        mobile,
        name="متخصص",
        is_active=True,
        public_visibility=Stylist.PublicVisibility.PUBLIC,
    ):
        return Stylist.objects.create(
            user=self._user(mobile=mobile, name=name, family="تست"),
            is_active=is_active,
            expert="تخصص تست",
            public_visibility=public_visibility,
        )

    def _connect(self, *, salon, service, stylist):
        salon.services.add(service)
        salon.stylists.add(stylist)
        service.stylists.add(stylist)

    def _selection(self, *, service, stylist="any"):
        stylist_id = "any" if stylist == "any" else str(stylist.user_id)
        stylist_name = "هر متخصص" if stylist == "any" else stylist.get_fullName()

        return {
            "serviceId": str(service.pk),
            "stylistId": stylist_id,
            "requestedStylistId": stylist_id,
            "stylistName": stylist_name,
            "requestedStylistName": stylist_name,
        }

    def _datetime_payload(
        self, *, service, stylist="any", date_value=None, time_value="10:00"
    ):
        stylist_id = "any" if stylist == "any" else str(stylist.user_id)
        date_value = date_value or timezone.localdate() + timedelta(days=1)
        key = f"{stylist_id}_{service.pk}"

        return {
            key: {
                "date": date_value.strftime("%Y-%m-%d"),
                "time": time_value,
                "stylist_id": stylist_id,
                "stylist_name": (
                    "هر متخصص" if stylist == "any" else stylist.get_fullName()
                ),
            }
        }

    def test_select_stylists_get_rejects_private_service(self):
        salon = self._salon(is_active=True)
        group = self._group()
        private_service = self._service(
            "خدمت خصوصی",
            group=group,
            is_active=True,
            is_platform_catalog=False,
        )
        salon.services.add(private_service)

        response = self.client.get(
            reverse("orders:select_stylists"),
            data={
                "salon_id": str(salon.pk),
                "selected_services": str(private_service.pk),
            },
        )

        self.assertEqual(response.status_code, 302)

    def test_select_stylists_post_rejects_hidden_stylist(self):
        salon = self._salon(is_active=True)
        group = self._group()
        service = self._service("خدمت عمومی", group=group)
        hidden_stylist = self._stylist(
            mobile="09123000101",
            public_visibility=Stylist.PublicVisibility.HIDDEN,
        )
        self._connect(salon=salon, service=service, stylist=hidden_stylist)

        response = self.client.post(
            reverse("orders:select_stylists"),
            data={
                "salon_id": str(salon.pk),
                "stylist_selections": json.dumps(
                    [self._selection(service=service, stylist=hidden_stylist)]
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("stylist_selections", self.client.session)

    def test_select_stylists_post_accepts_public_stylist(self):
        salon = self._salon(is_active=True)
        group = self._group()
        service = self._service("خدمت عمومی", group=group)
        stylist = self._stylist(
            mobile="09123000102",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )
        self._connect(salon=salon, service=service, stylist=stylist)

        response = self.client.post(
            reverse("orders:select_stylists"),
            data={
                "salon_id": str(salon.pk),
                "stylist_selections": json.dumps(
                    [self._selection(service=service, stylist=stylist)]
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["salon_id"], str(salon.pk))
        self.assertEqual(
            self.client.session["stylist_selections"][0]["serviceId"],
            str(service.pk),
        )

    def test_datetime_post_rejects_private_service_tampering(self):
        salon = self._salon(is_active=True)
        group = self._group()
        private_service = self._service(
            "خدمت خصوصی",
            group=group,
            is_active=True,
            is_platform_catalog=False,
        )
        salon.services.add(private_service)

        booking_data = {
            "salon_id": str(salon.pk),
            "stylist_selections": [self._selection(service=private_service)],
            "datetime_selections": self._datetime_payload(service=private_service),
        }

        response = self.client.post(
            reverse("orders:select_dateTime"),
            data={"booking_data": json.dumps(booking_data)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("datetime_selections", self.client.session)

    def test_datetime_post_rejects_past_date(self):
        salon = self._salon(is_active=True)
        group = self._group()
        service = self._service("خدمت عمومی", group=group)
        stylist = self._stylist(
            mobile="09123000103",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )
        self._connect(salon=salon, service=service, stylist=stylist)

        booking_data = {
            "salon_id": str(salon.pk),
            "stylist_selections": [self._selection(service=service, stylist=stylist)],
            "datetime_selections": self._datetime_payload(
                service=service,
                stylist=stylist,
                date_value=timezone.localdate() - timedelta(days=1),
            ),
        }

        response = self.client.post(
            reverse("orders:select_dateTime"),
            data={"booking_data": json.dumps(booking_data)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("datetime_selections", self.client.session)

    def test_datetime_post_accepts_valid_public_selection(self):
        salon = self._salon(is_active=True)
        group = self._group()
        service = self._service("خدمت عمومی", group=group)
        stylist = self._stylist(
            mobile="09123000104",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )
        self._connect(salon=salon, service=service, stylist=stylist)

        booking_data = {
            "salon_id": str(salon.pk),
            "stylist_selections": [self._selection(service=service, stylist=stylist)],
            "datetime_selections": self._datetime_payload(
                service=service,
                stylist=stylist,
            ),
        }

        response = self.client.post(
            reverse("orders:select_dateTime"),
            data={"booking_data": json.dumps(booking_data)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["salon_id"], str(salon.pk))
        self.assertIn("datetime_selections", self.client.session)
