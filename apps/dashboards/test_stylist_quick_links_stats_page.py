from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Customer, SalonManager, Stylist
from apps.analytics.models import AnalyticsEvent
from apps.orders.models import BookingQuickLink, Order
from apps.orders.quick_links import (
    BOOKING_QUICK_LINK_CONVERTED_EVENT,
    BOOKING_QUICK_LINK_OPENED_EVENT,
    BOOKING_QUICK_LINK_STARTED_EVENT,
)
from apps.salons.models import (
    Salon,
    SalonMembership,
    SalonMembershipStatus,
)
from apps.services.models import Services


User = get_user_model()


class StylistQuickLinksStatsPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = User.objects.create_user(
            mobile_number="09128881001",
            password="test-pass-123",
            name="مدیر",
            family="متخصص",
        )
        cls.manager_user.is_active = True
        cls.manager_user.save(update_fields=["is_active"])

        cls.other_manager_user = User.objects.create_user(
            mobile_number="09128881002",
            password="test-pass-123",
            name="مدیر",
            family="دیگر",
        )
        cls.other_manager_user.is_active = True
        cls.other_manager_user.save(update_fields=["is_active"])

        cls.manager = SalonManager.objects.create(
            user=cls.manager_user,
            is_active=True,
        )
        cls.other_manager = SalonManager.objects.create(
            user=cls.other_manager_user,
            is_active=True,
        )

        cls.salon = Salon.objects.create(
            salon_name="سالن متخصص",
            salon_manager=cls.manager,
            is_active=True,
        )
        cls.other_salon = Salon.objects.create(
            salon_name="سالن دیگر",
            salon_manager=cls.other_manager,
            is_active=True,
        )

        cls.stylist_user = User.objects.create_user(
            mobile_number="09128881003",
            password="test-pass-123",
            name="متخصص",
            family="اصلی",
        )
        cls.stylist_user.is_active = True
        cls.stylist_user.save(update_fields=["is_active"])

        cls.other_stylist_user = User.objects.create_user(
            mobile_number="09128881004",
            password="test-pass-123",
            name="متخصص",
            family="دیگر",
        )
        cls.other_stylist_user.is_active = True
        cls.other_stylist_user.save(update_fields=["is_active"])

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

        cls.salon.stylists.add(cls.stylist, cls.other_stylist)
        cls.other_salon.stylists.add(cls.stylist)

        cls.service = Services.objects.create(
            service_name="خدمت متخصص",
            is_active=True,
            duration_minutes=30,
            base_price=100000,
        )
        cls.other_service = Services.objects.create(
            service_name="خدمت دیگر",
            is_active=True,
            duration_minutes=30,
            base_price=120000,
        )

        cls.salon.services.add(cls.service)
        cls.other_salon.services.add(cls.other_service)
        cls.service.stylists.add(cls.stylist, cls.other_stylist)
        cls.other_service.stylists.add(cls.stylist)

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

        cls.customer_user = User.objects.create_user(
            mobile_number="09128881005",
            password="test-pass-123",
            name="مشتری",
            family="آمار",
        )
        cls.customer = Customer.objects.create(user=cls.customer_user)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.stylist_user)
        session = self.client.session
        session["active_stylist_salon_id"] = str(self.salon.pk)
        session.save()

    def page_url(self):
        return reverse("dashboards:stylist_quick_links")

    def create_link(
        self,
        *,
        creator=None,
        salon=None,
        stylist=None,
        service=None,
        title="",
        **overrides,
    ):
        creator = creator or self.stylist_user
        salon = salon or self.salon
        stylist = stylist or self.stylist
        service = service or self.service
        values = {
            "creator": creator,
            "salon": salon,
            "stylist": stylist,
            "service": service,
            "title": title,
            "mode": BookingQuickLink.Mode.SERVICE_STYLIST,
            "placement": BookingQuickLink.Placement.INSTAGRAM_BIO,
            "campaign_name": "کمپین متخصص",
            "payload": {
                "mode": BookingQuickLink.Mode.SERVICE_STYLIST,
                "salon_id": salon.pk,
                "service_ids": [service.pk],
                "stylist_user_id": stylist.pk,
                "date": "",
                "time": "",
                "summary": {
                    "service": service.service_name,
                    "stylist": stylist.get_fullName(),
                },
            },
            "is_permanent": True,
        }
        values.update(overrides)
        return BookingQuickLink.objects.create(**values)

    def create_event(self, *, quick_link, event_type, session_key, order=None):
        content_type = ContentType.objects.get_for_model(
            BookingQuickLink,
            for_concrete_model=False,
        )
        return AnalyticsEvent.objects.create(
            category="appointment",
            event_type=event_type,
            occurred_at=timezone.now(),
            salon=quick_link.salon,
            stylist=quick_link.stylist,
            order=order,
            target_content_type=content_type,
            target_object_id=quick_link.pk,
            session_key=session_key,
            source=quick_link.placement,
            metadata={"quick_link_id": quick_link.pk},
        )

    def test_anonymous_user_is_redirected(self):
        response = Client().get(self.page_url())
        self.assertEqual(response.status_code, 302)

    def test_scope_only_returns_own_links_in_active_salon(self):
        own_link = self.create_link(title="لینک خودم")
        manager_link = self.create_link(
            creator=self.manager_user,
            title="لینک مدیر برای من",
        )
        other_stylist_link = self.create_link(
            creator=self.other_stylist_user,
            stylist=self.other_stylist,
            title="لینک متخصص دیگر",
        )
        other_salon_link = self.create_link(
            salon=self.other_salon,
            service=self.other_service,
            title="لینک سالن دیگر",
        )

        response = self.client.get(self.page_url())
        self.assertEqual(response.status_code, 200)

        returned_ids = {
            row["id"]
            for row in response.context["quick_link_workspace"]["links"]
        }
        self.assertIn(own_link.pk, returned_ids)
        self.assertNotIn(manager_link.pk, returned_ids)
        self.assertNotIn(other_stylist_link.pk, returned_ids)
        self.assertNotIn(other_salon_link.pk, returned_ids)

    def test_stats_and_qr_urls_are_available(self):
        quick_link = self.create_link(title="لینک آماری")
        self.create_event(
            quick_link=quick_link,
            event_type=BOOKING_QUICK_LINK_OPENED_EVENT,
            session_key="stylist-session",
        )
        self.create_event(
            quick_link=quick_link,
            event_type=BOOKING_QUICK_LINK_STARTED_EVENT,
            session_key="stylist-session",
        )
        order = Order.objects.create(
            customer=self.customer,
            salon=self.salon,
            status="confirmed",
            is_finally=True,
            selected_payment_method="pay_in_salon",
            booking_quick_link=quick_link,
        )
        self.create_event(
            quick_link=quick_link,
            event_type=BOOKING_QUICK_LINK_CONVERTED_EVENT,
            session_key="stylist-session",
            order=order,
        )

        response = self.client.get(
            self.page_url(),
            {"period": "7", "sort": "conversions"},
        )
        workspace = response.context["quick_link_workspace"]
        row = workspace["links"][0]

        self.assertEqual(workspace["period"]["key"], "7")
        self.assertEqual(workspace["sort"], "conversions")
        self.assertEqual(workspace["summary"]["total_opens"], 1)
        self.assertEqual(workspace["summary"]["unique_visitors"], 1)
        self.assertEqual(workspace["summary"]["started_count"], 1)
        self.assertEqual(workspace["summary"]["converted_count"], 1)
        self.assertEqual(workspace["summary"]["conversion_rate"], 100.0)
        self.assertEqual(row["converted_count"], 1)
        self.assertEqual(
            row["qr_preview_url"],
            reverse(
                "dashboards:stylist_quick_link_qr_preview",
                kwargs={"link_id": quick_link.pk},
            ),
        )
        self.assertEqual(
            row["qr_download_url"],
            reverse(
                "dashboards:stylist_quick_link_qr_download",
                kwargs={"link_id": quick_link.pk},
            ),
        )

    def test_valid_post_creates_scoped_link_with_metadata(self):
        response = self.client.post(
            self.page_url(),
            {
                "quick_link_mode": BookingQuickLink.Mode.STYLIST,
                "service_id": "",
                "appointment_date": "",
                "appointment_time": "",
                "quick_link_title": "لینک بیوی من",
                "placement": BookingQuickLink.Placement.INSTAGRAM_BIO,
                "campaign_name": "بیوی مرداد",
                "internal_note": "فقط برای صفحه شخصی متخصص",
                "is_permanent": "on",
            },
        )
        self.assertEqual(response.status_code, 200)

        quick_link = BookingQuickLink.objects.get()
        self.assertEqual(quick_link.creator_id, self.stylist_user.pk)
        self.assertEqual(quick_link.salon_id, self.salon.pk)
        self.assertEqual(quick_link.stylist_id, self.stylist.pk)
        self.assertEqual(
            quick_link.placement,
            BookingQuickLink.Placement.INSTAGRAM_BIO,
        )
        self.assertEqual(quick_link.campaign_name, "بیوی مرداد")
        self.assertEqual(
            quick_link.internal_note,
            "فقط برای صفحه شخصی متخصص",
        )
        self.assertTrue(quick_link.is_permanent)
        self.assertContains(response, "لینک با موفقیت ساخته شد")

    def test_invalid_placement_is_rejected_and_values_are_preserved(self):
        response = self.client.post(
            self.page_url(),
            {
                "quick_link_mode": BookingQuickLink.Mode.STYLIST,
                "placement": "invalid-placement",
                "campaign_name": "کمپین حفظ شود",
                "internal_note": "یادداشت حفظ شود",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BookingQuickLink.objects.exists())
        self.assertContains(
            response,
            "محل استفاده انتخاب‌شده برای لینک معتبر نیست.",
        )
        workspace = response.context["quick_link_workspace"]
        self.assertEqual(workspace["campaign_name"], "کمپین حفظ شود")
        self.assertEqual(workspace["internal_note"], "یادداشت حفظ شود")

    def test_invalid_period_and_sort_fall_back(self):
        self.create_link(title="Fallback")
        response = self.client.get(
            self.page_url(),
            {"period": "bad", "sort": "bad"},
        )
        self.assertEqual(response.status_code, 200)
        workspace = response.context["quick_link_workspace"]
        self.assertEqual(workspace["period"]["key"], "30")
        self.assertEqual(workspace["sort"], "newest")

    def test_manager_created_link_cannot_be_modified_by_stylist(self):
        manager_link = self.create_link(
            creator=self.manager_user,
            title="مدیر ساخته",
        )
        response = self.client.post(
            self.page_url(),
            {
                "quick_link_action": "disable",
                "quick_link_id": str(manager_link.pk),
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        manager_link.refresh_from_db()
        self.assertTrue(manager_link.is_active)
