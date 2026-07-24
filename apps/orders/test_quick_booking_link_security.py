from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser, SalonManager, Stylist
from apps.orders.views import QuickBookingEntryView
from apps.salons.models import Salon
from apps.services.models import GroupServices, Services


class QuickBookingLinkSecurityTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _user(self, *, mobile, name="کاربر", family="تست"):
        return CustomUser.objects.create(
            mobile_number=mobile,
            name=name,
            family=family,
            is_active=True,
        )

    def _manager(self, *, mobile="09122000001"):
        return SalonManager.objects.create(
            user=self._user(mobile=mobile, name="مدیر", family="سالن"),
            is_active=True,
        )

    def _salon(self, *, name="سالن تست", is_active=True, mobile="09122000002"):
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

    def _request_with_session(self, path="/quick/test/"):
        request = self.factory.get(path)
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def _call_quick_entry(self, payload):
        request = self._request_with_session()
        with patch(
            "apps.orders.views.resolve_booking_quick_link_token",
            return_value=(None, payload),
        ):
            response = QuickBookingEntryView.as_view()(request, token="test-token")
        return response, request

    def test_quick_entry_rejects_non_catalog_service(self):
        salon = self._salon(is_active=True)
        group = self._group()
        service = self._service(
            "خدمت اختصاصی",
            group=group,
            is_active=True,
            is_platform_catalog=False,
        )
        salon.services.add(service)

        response, request = self._call_quick_entry(
            {
                "mode": "service",
                "salon_id": salon.pk,
                "service_ids": [service.pk],
            }
        )

        self.assertEqual(response.status_code, 410)
        self.assertNotIn("stylist_selections", request.session)

    def test_quick_entry_rejects_hidden_stylist(self):
        salon = self._salon(is_active=True)
        stylist = self._stylist(
            mobile="09122000101",
            public_visibility=Stylist.PublicVisibility.HIDDEN,
        )
        salon.stylists.add(stylist)

        response, request = self._call_quick_entry(
            {
                "mode": "stylist",
                "salon_id": salon.pk,
                "stylist_user_id": stylist.user_id,
                "service_ids": [],
            }
        )

        self.assertEqual(response.status_code, 410)
        self.assertNotIn("stylist_selections", request.session)

    def test_quick_entry_rejects_service_not_offered_by_stylist(self):
        salon = self._salon(is_active=True)
        group = self._group()
        service = self._service("خدمت عمومی", group=group)
        stylist = self._stylist(
            mobile="09122000102",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )

        salon.services.add(service)
        salon.stylists.add(stylist)

        response, request = self._call_quick_entry(
            {
                "mode": "service_stylist",
                "salon_id": salon.pk,
                "stylist_user_id": stylist.user_id,
                "service_ids": [service.pk],
            }
        )

        self.assertEqual(response.status_code, 410)
        self.assertNotIn("stylist_selections", request.session)

    def test_quick_entry_rejects_invalid_time_payload(self):
        salon = self._salon(is_active=True)
        group = self._group()
        service = self._service("خدمت عمومی", group=group)
        stylist = self._stylist(
            mobile="09122000103",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )
        self._connect(salon=salon, service=service, stylist=stylist)

        response, request = self._call_quick_entry(
            {
                "mode": "service_stylist_time",
                "salon_id": salon.pk,
                "stylist_user_id": stylist.user_id,
                "service_ids": [service.pk],
                "date": "not-a-date",
                "time": "25:99",
            }
        )

        self.assertEqual(response.status_code, 410)
        self.assertNotIn("datetime_selections", request.session)

    def test_quick_entry_accepts_valid_service_stylist_time(self):
        salon = self._salon(is_active=True)
        group = self._group()
        service = self._service("خدمت عمومی", group=group)
        stylist = self._stylist(
            mobile="09122000104",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )
        self._connect(salon=salon, service=service, stylist=stylist)

        future_date = timezone.localdate() + timedelta(days=1)

        response, request = self._call_quick_entry(
            {
                "mode": "service_stylist_time",
                "salon_id": salon.pk,
                "stylist_user_id": stylist.user_id,
                "service_ids": [service.pk],
                "date": future_date.strftime("%Y-%m-%d"),
                "time": "10:00",
            }
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("stylist_selections", request.session)
        self.assertIn("datetime_selections", request.session)

    def test_quick_link_stylist_services_rejects_hidden_stylist(self):
        salon = self._salon(is_active=True)
        stylist = self._stylist(
            mobile="09122000105",
            public_visibility=Stylist.PublicVisibility.HIDDEN,
        )
        salon.stylists.add(stylist)

        response = self.client.get(
            reverse("orders:quick_link_stylist_services"),
            data={
                "salon_id": str(salon.pk),
                "stylist_id": str(stylist.user_id),
            },
        )

        self.assertEqual(response.status_code, 404)

    def test_quick_link_stylist_services_post_rejects_private_service(self):
        salon = self._salon(is_active=True)
        group = self._group()
        public_service = self._service("خدمت عمومی", group=group)
        private_service = self._service(
            "خدمت اختصاصی",
            group=group,
            is_platform_catalog=False,
        )
        stylist = self._stylist(
            mobile="09122000106",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )

        self._connect(salon=salon, service=public_service, stylist=stylist)
        self._connect(salon=salon, service=private_service, stylist=stylist)

        response = self.client.post(
            reverse("orders:quick_link_stylist_services"),
            data={
                "salon_id": str(salon.pk),
                "stylist_id": str(stylist.user_id),
                "selected_services": [str(private_service.pk)],
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("stylist_selections", self.client.session)

    def test_quick_link_stylist_services_post_accepts_valid_service(self):
        salon = self._salon(is_active=True)
        group = self._group()
        service = self._service("خدمت عمومی", group=group)
        stylist = self._stylist(
            mobile="09122000107",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )
        self._connect(salon=salon, service=service, stylist=stylist)

        response = self.client.post(
            reverse("orders:quick_link_stylist_services"),
            data={
                "salon_id": str(salon.pk),
                "stylist_id": str(stylist.user_id),
                "selected_services": [str(service.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)

        session = self.client.session
        self.assertEqual(session["salon_id"], str(salon.pk))
        self.assertEqual(
            session["stylist_selections"][0]["serviceId"],
            str(service.pk),
        )
