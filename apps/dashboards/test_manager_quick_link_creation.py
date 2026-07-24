from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import (
    Client,
    TestCase,
)
from django.urls import reverse

from apps.accounts.models import SalonManager
from apps.orders.models import BookingQuickLink
from apps.salons.models import Salon
from apps.services.models import Services


User = get_user_model()


class ManagerQuickLinkCreationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = User.objects.create_user(
            mobile_number="09129999001",
            password="test-pass-123",
            name="مدیر",
            family="ساخت لینک",
        )
        cls.manager_user.is_active = True
        cls.manager_user.save(
            update_fields=["is_active"]
        )

        cls.other_manager_user = (
            User.objects.create_user(
                mobile_number="09129999002",
                password="test-pass-123",
                name="مدیر",
                family="سالن دیگر",
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
            salon_name="سالن ساخت لینک",
            salon_manager=cls.manager,
            is_active=True,
        )

        cls.other_salon = Salon.objects.create(
            salon_name="سالن دیگر",
            salon_manager=cls.other_manager,
            is_active=True,
        )

        cls.service = Services.objects.create(
            service_name="خدمت ساخت لینک",
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

    def setUp(self):
        self.client = Client()
        self.client.force_login(
            self.manager_user
        )

    def page_url(self):
        return reverse(
            "dashboards:quick_links"
        )

    def valid_post_data(self):
        return {
            "quick_link_mode": (
                BookingQuickLink.Mode.SERVICE
            ),
            "service_id": str(
                self.service.pk
            ),
            "stylist_id": "",
            "appointment_date": "",
            "appointment_time": "",
            "quick_link_title": (
                "لیبل آینه سالن"
            ),
            "placement": (
                BookingQuickLink.Placement
                .MIRROR_LABEL
            ),
            "campaign_name": (
                "نصب لیبل مرداد"
            ),
            "internal_note": (
                "نصب روی آینه سمت پذیرش"
            ),
            "is_permanent": "on",
        }

    def test_page_renders_creation_form_and_metadata_fields(self):
        response = self.client.get(
            self.page_url()
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "ساخت لینک رزرو جدید",
        )

        self.assertContains(
            response,
            'name="placement"',
        )

        self.assertContains(
            response,
            'name="campaign_name"',
        )

        self.assertContains(
            response,
            'name="internal_note"',
        )

        workspace = response.context[
            "quick_link_create_workspace"
        ]

        placement_values = {
            value
            for value, _label
            in workspace["placement_options"]
        }

        self.assertIn(
            (
                BookingQuickLink.Placement
                .MIRROR_LABEL
            ),
            placement_values,
        )

    def test_valid_post_creates_link_with_metadata(self):
        response = self.client.post(
            self.page_url(),
            self.valid_post_data(),
        )

        self.assertRedirects(
            response,
            self.page_url(),
            fetch_redirect_response=False,
        )

        quick_link = (
            BookingQuickLink.objects.get()
        )

        self.assertEqual(
            quick_link.salon_id,
            self.salon.pk,
        )

        self.assertEqual(
            quick_link.creator_id,
            self.manager_user.pk,
        )

        self.assertEqual(
            quick_link.service_id,
            self.service.pk,
        )

        self.assertEqual(
            quick_link.placement,
            (
                BookingQuickLink.Placement
                .MIRROR_LABEL
            ),
        )

        self.assertEqual(
            quick_link.campaign_name,
            "نصب لیبل مرداد",
        )

        self.assertEqual(
            quick_link.internal_note,
            "نصب روی آینه سمت پذیرش",
        )

        self.assertTrue(
            quick_link.is_permanent
        )

        page_response = self.client.get(
            self.page_url()
        )

        self.assertEqual(
            page_response.status_code,
            200,
        )

        self.assertContains(
            page_response,
            "لینک با موفقیت ساخته شد",
        )

        self.assertContains(
            page_response,
            str(quick_link.token),
        )

    def test_invalid_placement_does_not_create_link(self):
        post_data = self.valid_post_data()
        post_data["placement"] = "invalid-place"

        response = self.client.post(
            self.page_url(),
            post_data,
            follow=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            BookingQuickLink.objects.exists()
        )

        self.assertContains(
            response,
            (
                "محل استفاده انتخاب‌شده "
                "برای لینک معتبر نیست."
            ),
        )

        workspace = response.context[
            "quick_link_create_workspace"
        ]

        self.assertEqual(
            workspace["campaign_name"],
            "نصب لیبل مرداد",
        )

        self.assertEqual(
            workspace["internal_note"],
            "نصب روی آینه سمت پذیرش",
        )

    def test_service_from_other_salon_is_rejected(self):
        post_data = self.valid_post_data()

        post_data["service_id"] = str(
            self.other_service.pk
        )

        response = self.client.post(
            self.page_url(),
            post_data,
            follow=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            BookingQuickLink.objects.exists()
        )

        self.assertContains(
            response,
            (
                "خدمت انتخاب‌شده برای "
                "این مجموعه معتبر نیست."
            ),
        )

    def test_default_placement_is_direct(self):
        post_data = self.valid_post_data()
        post_data.pop("placement")

        response = self.client.post(
            self.page_url(),
            post_data,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        quick_link = (
            BookingQuickLink.objects.get()
        )

        self.assertEqual(
            quick_link.placement,
            BookingQuickLink.Placement.DIRECT,
        )

    def test_old_online_booking_page_no_longer_contains_creation_panel(self):
        template_path = (
            Path(settings.BASE_DIR)
            / "templates"
            / "dashboards"
            / "online_booking.html"
        )

        source = template_path.read_text(
            encoding="utf-8"
        )

        self.assertNotIn(
            'id="online-booking-section-quick-link"',
            source,
        )

        self.assertIn(
            'href="{{ quick_links_url }}"',
            source,
        )

        self.assertIn(
            "لینک‌های رزرو",
            source,
        )
