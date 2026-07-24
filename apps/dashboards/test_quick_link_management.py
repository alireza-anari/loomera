from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import SalonManager, Stylist
from apps.analytics.models import AnalyticsEvent
from apps.orders.models import BookingQuickLink
from apps.orders.quick_link_management import (
    change_booking_quick_link_status,
    clone_booking_quick_link,
    update_booking_quick_link_metadata,
)
from apps.orders.quick_links import BOOKING_QUICK_LINK_OPENED_EVENT
from apps.salons.models import (
    Salon,
    SalonMembership,
    SalonMembershipStatus,
)
from apps.services.models import Services


User = get_user_model()


class QuickLinkManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = User.objects.create_user(
            mobile_number="09127771001",
            password="test-pass-123",
            name="مدیر",
            family="لینک",
        )
        cls.manager_user.is_active = True
        cls.manager_user.save(update_fields=["is_active"])

        cls.other_manager_user = User.objects.create_user(
            mobile_number="09127771002",
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
            salon_name="سالن مدیریت",
            salon_manager=cls.manager,
            is_active=True,
        )
        cls.other_salon = Salon.objects.create(
            salon_name="سالن دیگر",
            salon_manager=cls.other_manager,
            is_active=True,
        )

        cls.stylist_user = User.objects.create_user(
            mobile_number="09127771003",
            password="test-pass-123",
            name="متخصص",
            family="لینک",
        )
        cls.stylist_user.is_active = True
        cls.stylist_user.save(update_fields=["is_active"])

        cls.stylist = Stylist.objects.create(
            user=cls.stylist_user,
            expert="مو",
            is_active=True,
        )
        cls.salon.stylists.add(cls.stylist)

        cls.service = Services.objects.create(
            service_name="خدمت مدیریت",
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
        cls.service.stylists.add(cls.stylist)

        SalonMembership.objects.create(
            salon=cls.salon,
            stylist=cls.stylist,
            status=SalonMembershipStatus.ACTIVE,
        )

    def create_link(
        self,
        *,
        creator=None,
        salon=None,
        service=None,
        stylist=None,
        title="لینک اصلی",
        **overrides,
    ):
        creator = creator or self.manager_user
        salon = salon or self.salon
        service = service or self.service
        mode = (
            BookingQuickLink.Mode.SERVICE_STYLIST
            if stylist
            else BookingQuickLink.Mode.SERVICE
        )

        values = {
            "creator": creator,
            "salon": salon,
            "service": service,
            "stylist": stylist,
            "title": title,
            "mode": mode,
            "placement": BookingQuickLink.Placement.DIRECT,
            "campaign_name": "کمپین اصلی",
            "internal_note": "یادداشت اصلی",
            "payload": {
                "mode": mode,
                "salon_id": salon.pk,
                "service_ids": [service.pk],
                "stylist_user_id": (
                    stylist.pk if stylist else None
                ),
                "date": "",
                "time": "",
                "summary": {},
            },
            "is_permanent": True,
        }
        values.update(overrides)
        return BookingQuickLink.objects.create(**values)

    def manager_url(self):
        return reverse("dashboards:quick_links")

    def stylist_client(self):
        client = Client()
        client.force_login(self.stylist_user)
        session = client.session
        session["active_stylist_salon_id"] = str(self.salon.pk)
        session.save()
        return client

    def test_edit_is_metadata_only_and_invalid_edit_is_atomic(self):
        quick_link = self.create_link()
        token = quick_link.token
        payload = dict(quick_link.payload)

        update_booking_quick_link_metadata(
            links_queryset=BookingQuickLink.objects.filter(
                salon=self.salon
            ),
            link_id=quick_link.pk,
            title="عنوان جدید",
            placement=BookingQuickLink.Placement.MIRROR_LABEL,
            campaign_name="کمپین جدید",
            internal_note="یادداشت جدید",
            is_permanent=False,
        )

        quick_link.refresh_from_db()
        self.assertEqual(quick_link.token, token)
        self.assertEqual(quick_link.payload, payload)
        self.assertEqual(
            quick_link.placement,
            BookingQuickLink.Placement.MIRROR_LABEL,
        )
        self.assertFalse(quick_link.is_permanent)
        self.assertIsNotNone(quick_link.expires_at)

        with self.assertRaises(ValidationError):
            update_booking_quick_link_metadata(
                links_queryset=BookingQuickLink.objects.filter(
                    salon=self.salon
                ),
                link_id=quick_link.pk,
                title="خراب",
                placement="bad-placement",
                campaign_name="خراب",
                internal_note="خراب",
                is_permanent=True,
            )

        quick_link.refresh_from_db()
        self.assertEqual(quick_link.title, "عنوان جدید")

    def test_clone_resets_identity_and_history(self):
        source = self.create_link(
            opens_count=5,
            bookings_count=2,
            last_opened_at=timezone.now(),
            last_converted_at=timezone.now(),
        )

        cloned, _message = clone_booking_quick_link(
            links_queryset=BookingQuickLink.objects.filter(
                salon=self.salon
            ),
            link_id=source.pk,
            creator=self.manager_user,
        )

        self.assertNotEqual(cloned.token, source.token)
        self.assertEqual(cloned.opens_count, 0)
        self.assertEqual(cloned.bookings_count, 0)
        self.assertIsNone(cloned.last_opened_at)
        self.assertIsNone(cloned.last_converted_at)
        self.assertTrue(cloned.is_active)
        self.assertEqual(cloned.payload, source.payload)

    def test_safe_delete_hard_deletes_only_without_history(self):
        empty_link = self.create_link()

        deleted, _message = change_booking_quick_link_status(
            links_queryset=BookingQuickLink.objects.filter(
                salon=self.salon
            ),
            link_id=empty_link.pk,
            action="delete",
        )

        self.assertIsNone(deleted)
        self.assertFalse(
            BookingQuickLink.objects.filter(
                pk=empty_link.pk
            ).exists()
        )

        history_link = self.create_link()
        content_type = ContentType.objects.get_for_model(
            BookingQuickLink,
            for_concrete_model=False,
        )
        AnalyticsEvent.objects.create(
            category="appointment",
            event_type=BOOKING_QUICK_LINK_OPENED_EVENT,
            occurred_at=timezone.now(),
            salon=self.salon,
            target_content_type=content_type,
            target_object_id=history_link.pk,
            session_key="history",
            source=history_link.placement,
            metadata={"quick_link_id": history_link.pk},
        )

        archived, _message = change_booking_quick_link_status(
            links_queryset=BookingQuickLink.objects.filter(
                salon=self.salon
            ),
            link_id=history_link.pk,
            action="delete",
        )

        archived.refresh_from_db()
        self.assertIsNotNone(archived.archived_at)
        self.assertFalse(archived.is_active)

    def test_archived_link_cannot_be_enabled(self):
        quick_link = self.create_link()
        quick_link.mark_archived()

        with self.assertRaises(ValidationError):
            change_booking_quick_link_status(
                links_queryset=BookingQuickLink.objects.filter(
                    salon=self.salon
                ),
                link_id=quick_link.pk,
                action="enable",
            )

    def test_manager_scope_and_clone_owner(self):
        same_salon = self.create_link(
            creator=self.stylist_user,
            stylist=self.stylist,
        )
        other_salon = self.create_link(
            creator=self.other_manager_user,
            salon=self.other_salon,
            service=self.other_service,
        )

        client = Client()
        client.force_login(self.manager_user)

        response = client.post(
            self.manager_url(),
            {
                "quick_link_action": "edit",
                "quick_link_id": str(same_salon.pk),
                "quick_link_title": "ویرایش مدیر",
                "placement": BookingQuickLink.Placement.RECEPTION,
                "campaign_name": "",
                "internal_note": "",
                "is_permanent": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        same_salon.refresh_from_db()
        self.assertEqual(same_salon.title, "ویرایش مدیر")

        client.post(
            self.manager_url(),
            {
                "quick_link_action": "edit",
                "quick_link_id": str(other_salon.pk),
                "quick_link_title": "نباید تغییر کند",
                "placement": BookingQuickLink.Placement.RECEPTION,
                "campaign_name": "",
                "internal_note": "",
                "is_permanent": "on",
            },
        )
        other_salon.refresh_from_db()
        self.assertEqual(other_salon.title, "لینک اصلی")

        client.post(
            self.manager_url(),
            {
                "quick_link_action": "clone",
                "quick_link_id": str(same_salon.pk),
            },
        )
        cloned = (
            BookingQuickLink.objects.filter(
                salon=self.salon,
                creator=self.manager_user,
                stylist=self.stylist,
            )
            .exclude(pk=same_salon.pk)
            .get()
        )
        self.assertEqual(cloned.creator_id, self.manager_user.pk)

    def test_stylist_scope_and_controls_render(self):
        own_link = self.create_link(
            creator=self.stylist_user,
            stylist=self.stylist,
            title="لینک متخصص",
        )
        manager_link = self.create_link(
            creator=self.manager_user,
            stylist=self.stylist,
            title="لینک مدیر",
        )

        client = self.stylist_client()
        url = reverse("dashboards:stylist_quick_links")

        response = client.post(
            url,
            {
                "quick_link_action": "edit",
                "quick_link_id": str(own_link.pk),
                "quick_link_title": "ویرایش متخصص",
                "placement": BookingQuickLink.Placement.WHATSAPP,
                "campaign_name": "",
                "internal_note": "",
                "is_permanent": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        own_link.refresh_from_db()
        self.assertEqual(own_link.title, "ویرایش متخصص")

        client.post(
            url,
            {
                "quick_link_action": "archive",
                "quick_link_id": str(manager_link.pk),
            },
        )
        manager_link.refresh_from_db()
        self.assertIsNone(manager_link.archived_at)

        manager_client = Client()
        manager_client.force_login(self.manager_user)
        manager_page = manager_client.get(self.manager_url())
        self.assertContains(manager_page, 'value="clone"')
        self.assertContains(manager_page, "حذف امن")

        stylist_page = client.get(url)
        self.assertContains(stylist_page, "ویرایش مشخصات")
        self.assertContains(stylist_page, "بایگانی")
