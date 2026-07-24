from __future__ import annotations

from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from khayyam import JalaliDate as KhayyamJalaliDate

from apps.accounts.models import CustomUser, SalonManager, Stylist
from apps.salons.models import Salon
from apps.services.models import GroupServices, Services
from apps.stylists.models import StylistSchedule


class PublicBookingApiSecurityTests(TestCase):
    def _user(self, *, mobile, name="کاربر", family="تست"):
        return CustomUser.objects.create(
            mobile_number=mobile,
            name=name,
            family=family,
            is_active=True,
        )

    def _manager(self, *, mobile="09121000001"):
        return SalonManager.objects.create(
            user=self._user(mobile=mobile, name="مدیر", family="سالن"),
            is_active=True,
        )

    def _salon(self, *, name="سالن تست", is_active=True, mobile="09121000002"):
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

    def _jalali_query_for_date(self, date_value):
        jalali = KhayyamJalaliDate(date_value)
        return {
            "year": str(jalali.year),
            "month": str(jalali.month),
        }

    def test_availability_rejects_invalid_salon_id(self):
        response = self.client.get(
            reverse("orders:api_availability"),
            data={"salon_id": "abc", "month": "1", "year": "1405"},
        )

        self.assertEqual(response.status_code, 400)

    def test_availability_rejects_inactive_salon(self):
        salon = self._salon(is_active=False)

        response = self.client.get(
            reverse("orders:api_availability"),
            data={"salon_id": str(salon.pk), "month": "1", "year": "1405"},
        )

        self.assertEqual(response.status_code, 404)

    def test_availability_rejects_invalid_month(self):
        salon = self._salon(is_active=True)

        response = self.client.get(
            reverse("orders:api_availability"),
            data={"salon_id": str(salon.pk), "month": "13", "year": "1405"},
        )

        self.assertEqual(response.status_code, 400)

    def test_availability_hides_hidden_stylist_schedule(self):
        salon = self._salon(is_active=True)
        group = self._group()
        service = self._service("پاکسازی تست", group=group)

        public_stylist = self._stylist(
            mobile="09121000101",
            name="متخصص عمومی",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )
        hidden_stylist = self._stylist(
            mobile="09121000102",
            name="متخصص مخفی",
            public_visibility=Stylist.PublicVisibility.HIDDEN,
        )

        self._connect(salon=salon, service=service, stylist=public_stylist)
        self._connect(salon=salon, service=service, stylist=hidden_stylist)

        date_value = timezone.localdate()
        StylistSchedule.objects.create(
            salon=salon,
            stylist=public_stylist,
            service=service,
            date=date_value,
            start_time=time(10, 0),
            end_time=time(12, 0),
        )
        StylistSchedule.objects.create(
            salon=salon,
            stylist=hidden_stylist,
            service=service,
            date=date_value,
            start_time=time(13, 0),
            end_time=time(15, 0),
        )

        payload = {
            "salon_id": str(salon.pk),
            **self._jalali_query_for_date(date_value),
        }

        response = self.client.get(reverse("orders:api_availability"), data=payload)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn(str(public_stylist.user_id), data["schedules"])
        self.assertNotIn(str(hidden_stylist.user_id), data["schedules"])

    def test_availability_hides_non_catalog_service_schedule(self):
        salon = self._salon(is_active=True)
        group = self._group()
        private_service = self._service(
            "خدمت اختصاصی تست",
            group=group,
            is_platform_catalog=False,
        )
        stylist = self._stylist(
            mobile="09121000103",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )

        self._connect(salon=salon, service=private_service, stylist=stylist)

        date_value = timezone.localdate()
        StylistSchedule.objects.create(
            salon=salon,
            stylist=stylist,
            service=private_service,
            date=date_value,
            start_time=time(10, 0),
            end_time=time(12, 0),
        )

        response = self.client.get(
            reverse("orders:api_availability"),
            data={
                "salon_id": str(salon.pk),
                **self._jalali_query_for_date(date_value),
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertNotIn(str(stylist.user_id), data["schedules"])

    def test_stylists_for_service_rejects_invalid_service_id(self):
        salon = self._salon(is_active=True)

        response = self.client.get(
            reverse("orders:api_stylists_for_service"),
            data={"salon_id": str(salon.pk), "service_id": "abc"},
        )

        self.assertEqual(response.status_code, 400)

    def test_stylists_for_service_rejects_non_catalog_service(self):
        salon = self._salon(is_active=True)
        group = self._group()
        service = self._service(
            "خدمت اختصاصی تست",
            group=group,
            is_platform_catalog=False,
        )
        salon.services.add(service)

        response = self.client.get(
            reverse("orders:api_stylists_for_service"),
            data={"salon_id": str(salon.pk), "service_id": str(service.pk)},
        )

        self.assertEqual(response.status_code, 404)

    def test_stylists_for_service_hides_hidden_stylist(self):
        salon = self._salon(is_active=True)
        group = self._group()
        service = self._service("براشینگ تست", group=group)

        public_stylist = self._stylist(
            mobile="09121000104",
            name="متخصص عمومی",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )
        hidden_stylist = self._stylist(
            mobile="09121000105",
            name="متخصص مخفی",
            public_visibility=Stylist.PublicVisibility.HIDDEN,
        )

        self._connect(salon=salon, service=service, stylist=public_stylist)
        self._connect(salon=salon, service=service, stylist=hidden_stylist)

        date_value = timezone.localdate() + timedelta(days=1)

        StylistSchedule.objects.create(
            salon=salon,
            stylist=public_stylist,
            service=service,
            date=date_value,
            start_time=time(10, 0),
            end_time=time(12, 0),
        )
        StylistSchedule.objects.create(
            salon=salon,
            stylist=hidden_stylist,
            service=service,
            date=date_value,
            start_time=time(13, 0),
            end_time=time(15, 0),
        )

        response = self.client.get(
            reverse("orders:api_stylists_for_service"),
            data={"salon_id": str(salon.pk), "service_id": str(service.pk)},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        stylist_ids = {item["id"] for item in data["stylists"]}
        self.assertIn(public_stylist.user_id, stylist_ids)
        self.assertNotIn(hidden_stylist.user_id, stylist_ids)

        self.assertEqual(data["best_available"]["id"], public_stylist.user_id)
