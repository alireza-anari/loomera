from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import (
    Client,
    TestCase,
    override_settings,
)
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import (
    SalonManager,
    Stylist,
)
from apps.orders.models import BookingQuickLink
from apps.salons.models import (
    Salon,
    SalonMembership,
    SalonMembershipStatus,
)
from apps.services.models import Services


User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["testserver"],
)
class BookingQuickLinkQREndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = User.objects.create_user(
            mobile_number="09129996001",
            password="test-pass-123",
            name="مدیر",
            family="اول",
        )
        cls.manager_user.is_active = True
        cls.manager_user.save(
            update_fields=["is_active"]
        )

        cls.other_manager_user = (
            User.objects.create_user(
                mobile_number="09129996002",
                password="test-pass-123",
                name="مدیر",
                family="دوم",
            )
        )
        cls.other_manager_user.is_active = True
        cls.other_manager_user.save(
            update_fields=["is_active"]
        )

        cls.manager = SalonManager.objects.create(
            user=cls.manager_user,
            is_active=True,
        )

        cls.other_manager = (
            SalonManager.objects.create(
                user=cls.other_manager_user,
                is_active=True,
            )
        )

        cls.salon = Salon.objects.create(
            salon_name="Karino",
            salon_manager=cls.manager,
            is_active=True,
        )

        cls.other_salon = Salon.objects.create(
            salon_name="Other Salon",
            salon_manager=cls.other_manager,
            is_active=True,
        )

        cls.service = Services.objects.create(
            service_name="خدمت QR Endpoint",
            is_active=True,
            duration_minutes=30,
            base_price=100000,
        )

        cls.other_service = Services.objects.create(
            service_name="خدمت سالن دیگر",
            is_active=True,
            duration_minutes=30,
            base_price=120000,
        )

        cls.salon.services.add(cls.service)
        cls.other_salon.services.add(
            cls.other_service
        )

        cls.stylist_user = User.objects.create_user(
            mobile_number="09129996003",
            password="test-pass-123",
            name="متخصص",
            family="اول",
        )
        cls.stylist_user.is_active = True
        cls.stylist_user.save(
            update_fields=["is_active"]
        )

        cls.other_stylist_user = (
            User.objects.create_user(
                mobile_number="09129996004",
                password="test-pass-123",
                name="متخصص",
                family="دوم",
            )
        )
        cls.other_stylist_user.is_active = True
        cls.other_stylist_user.save(
            update_fields=["is_active"]
        )

        cls.stylist = Stylist.objects.create(
            user=cls.stylist_user,
            expert="مو",
            is_active=True,
        )

        cls.other_stylist = Stylist.objects.create(
            user=cls.other_stylist_user,
            expert="پوست",
            is_active=True,
        )

        cls.salon.stylists.add(
            cls.stylist,
            cls.other_stylist,
        )

        cls.other_salon.stylists.add(
            cls.stylist
        )

        cls.service.stylists.add(
            cls.stylist,
            cls.other_stylist,
        )

        cls.other_service.stylists.add(
            cls.stylist
        )

        SalonMembership.objects.create(
            salon=cls.salon,
            stylist=cls.stylist,
            status=SalonMembershipStatus.ACTIVE,
        )

        SalonMembership.objects.create(
            salon=cls.other_salon,
            stylist=cls.stylist,
            status=SalonMembershipStatus.ACTIVE,
        )

        SalonMembership.objects.create(
            salon=cls.salon,
            stylist=cls.other_stylist,
            status=SalonMembershipStatus.ACTIVE,
        )

    def create_link(
        self,
        *,
        creator=None,
        salon=None,
        service=None,
        stylist=None,
        mode=None,
        payload=None,
        **overrides,
    ):
        creator = creator or self.manager_user
        salon = salon or self.salon
        service = service or self.service

        if mode is None:
            mode = (
                BookingQuickLink.Mode.SERVICE_STYLIST
                if stylist
                else BookingQuickLink.Mode.SERVICE
            )

        if payload is None:
            payload = {
                "mode": mode,
                "salon_id": salon.pk,
                "service_ids": [service.pk],
                "stylist_user_id": (
                    stylist.pk if stylist else None
                ),
                "date": "",
                "time": "",
                "summary": {},
            }

        values = {
            "creator": creator,
            "salon": salon,
            "service": service,
            "stylist": stylist,
            "mode": mode,
            "placement": (
                BookingQuickLink.Placement.TABLE_STAND
            ),
            "campaign_name": "کمپین QR Endpoint",
            "payload": payload,
            "is_permanent": True,
        }

        values.update(overrides)

        return BookingQuickLink.objects.create(
            **values
        )

    def activate_stylist_salon(
        self,
        client,
        salon,
    ):
        session = client.session
        session["active_stylist_salon_id"] = (
            salon.pk
        )
        session.save()

    def test_anonymous_manager_preview_requires_login(self):
        quick_link = self.create_link()

        response = Client().get(
            reverse(
                "dashboards:quick_link_qr_preview",
                kwargs={"link_id": quick_link.pk},
            )
        )

        self.assertEqual(response.status_code, 302)

    def test_manager_can_preview_stylist_created_link_in_own_salon(self):
        quick_link = self.create_link(
            creator=self.stylist_user,
            stylist=self.stylist,
        )

        client = Client()
        client.force_login(self.manager_user)

        response = client.get(
            reverse(
                "dashboards:quick_link_qr_preview",
                kwargs={"link_id": quick_link.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "image/png",
        )
        self.assertTrue(
            response.content.startswith(
                b"\x89PNG\r\n\x1a\n"
            )
        )
        self.assertIn(
            "inline;",
            response["Content-Disposition"],
        )
        self.assertEqual(
            response["Cache-Control"],
            "private, no-store, max-age=0",
        )

    def test_manager_cannot_access_other_salon_link(self):
        quick_link = self.create_link(
            creator=self.other_manager_user,
            salon=self.other_salon,
            service=self.other_service,
        )

        client = Client()
        client.force_login(self.manager_user)

        response = client.get(
            reverse(
                "dashboards:quick_link_qr_preview",
                kwargs={"link_id": quick_link.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_active_link_download_is_attachment(self):
        quick_link = self.create_link()

        client = Client()
        client.force_login(self.manager_user)

        response = client.get(
            reverse(
                "dashboards:quick_link_qr_download",
                kwargs={"link_id": quick_link.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "image/png",
        )
        self.assertIn(
            "attachment;",
            response["Content-Disposition"],
        )
        self.assertIn(
            "filename*=UTF-8''",
            response["Content-Disposition"],
        )
        self.assertEqual(
            response[
                "X-Loomera-QR-Warning-Count"
            ],
            "0",
        )

    def test_inactive_download_requires_explicit_confirmation(self):
        quick_link = self.create_link(
            is_active=False,
        )

        client = Client()
        client.force_login(self.manager_user)

        download_url = reverse(
            "dashboards:quick_link_qr_download",
            kwargs={"link_id": quick_link.pk},
        )

        blocked_response = client.get(download_url)

        self.assertEqual(
            blocked_response.status_code,
            409,
        )

        payload = blocked_response.json()

        self.assertEqual(
            payload["code"],
            "quick_link_qr_confirmation_required",
        )

        self.assertTrue(
            any(
                "غیرفعال" in warning
                for warning in payload["warnings"]
            )
        )

        confirmed_response = client.get(
            download_url,
            {"confirm": "1"},
        )

        self.assertEqual(
            confirmed_response.status_code,
            200,
        )

        self.assertIn(
            "attachment;",
            confirmed_response[
                "Content-Disposition"
            ],
        )

    def test_inactive_preview_is_available_with_warning_header(self):
        quick_link = self.create_link(
            is_active=False,
        )

        client = Client()
        client.force_login(self.manager_user)

        response = client.get(
            reverse(
                "dashboards:quick_link_qr_preview",
                kwargs={"link_id": quick_link.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response[
                "X-Loomera-QR-Warning-Count"
            ],
            "1",
        )

    def test_fixed_time_download_requires_confirmation(self):
        fixed_mode = (
            BookingQuickLink.Mode
            .SERVICE_STYLIST_TIME
        )

        quick_link = self.create_link(
            stylist=self.stylist,
            mode=fixed_mode,
            payload={
                "mode": fixed_mode,
                "salon_id": self.salon.pk,
                "service_ids": [self.service.pk],
                "stylist_user_id": self.stylist.pk,
                "date": "2026-08-01",
                "time": "10:00",
                "summary": {},
            },
            expires_at=(
                timezone.now()
                + timedelta(days=2)
            ),
        )

        client = Client()
        client.force_login(self.manager_user)

        response = client.get(
            reverse(
                "dashboards:quick_link_qr_download",
                kwargs={"link_id": quick_link.pk},
            )
        )

        self.assertEqual(response.status_code, 409)

        self.assertTrue(
            any(
                "چاپ دائمی" in warning
                for warning
                in response.json()["warnings"]
            )
        )

    def test_stylist_can_preview_own_link_in_active_salon(self):
        quick_link = self.create_link(
            creator=self.stylist_user,
            stylist=self.stylist,
        )

        client = Client()
        client.force_login(self.stylist_user)

        self.activate_stylist_salon(
            client,
            self.salon,
        )

        response = client.get(
            reverse(
                (
                    "dashboards:"
                    "stylist_quick_link_qr_preview"
                ),
                kwargs={"link_id": quick_link.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "image/png",
        )

    def test_stylist_cannot_access_other_stylist_link(self):
        quick_link = self.create_link(
            creator=self.other_stylist_user,
            stylist=self.other_stylist,
        )

        client = Client()
        client.force_login(self.stylist_user)

        self.activate_stylist_salon(
            client,
            self.salon,
        )

        response = client.get(
            reverse(
                (
                    "dashboards:"
                    "stylist_quick_link_qr_preview"
                ),
                kwargs={"link_id": quick_link.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_stylist_cannot_access_manager_created_link(self):
        quick_link = self.create_link(
            creator=self.manager_user,
            stylist=self.stylist,
        )

        client = Client()
        client.force_login(self.stylist_user)

        self.activate_stylist_salon(
            client,
            self.salon,
        )

        response = client.get(
            reverse(
                (
                    "dashboards:"
                    "stylist_quick_link_qr_preview"
                ),
                kwargs={"link_id": quick_link.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_stylist_active_salon_scope_is_enforced(self):
        quick_link = self.create_link(
            creator=self.stylist_user,
            salon=self.other_salon,
            service=self.other_service,
            stylist=self.stylist,
        )

        client = Client()
        client.force_login(self.stylist_user)

        self.activate_stylist_salon(
            client,
            self.salon,
        )

        response = client.get(
            reverse(
                (
                    "dashboards:"
                    "stylist_quick_link_qr_preview"
                ),
                kwargs={"link_id": quick_link.pk},
            )
        )

        self.assertEqual(response.status_code, 404)
