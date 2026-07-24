from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models.deletion import PROTECT, ProtectedError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Customer, SalonManager
from apps.orders.models import BookingQuickLink, Order
from apps.salons.models import Salon
from apps.services.models import Services

User = get_user_model()


class BookingQuickLinkModelContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.creator = User.objects.create_user(
            mobile_number="09129991001",
            password="test-pass-123",
            name="مدیر",
            family="لینک",
        )
        cls.creator.is_active = True
        cls.creator.save(update_fields=["is_active"])

        cls.manager = SalonManager.objects.create(
            user=cls.creator,
            is_active=True,
        )
        cls.salon = Salon.objects.create(
            salon_name="سالن قرارداد لینک",
            salon_manager=cls.manager,
            is_active=True,
        )

        cls.service = Services.objects.create(
            service_name="خدمت قرارداد لینک",
            is_active=True,
            duration_minutes=30,
            base_price=100000,
        )
        cls.salon.services.add(cls.service)

        cls.customer_user = User.objects.create_user(
            mobile_number="09129991002",
            password="test-pass-123",
            name="مشتری",
            family="لینک",
        )
        cls.customer = Customer.objects.create(user=cls.customer_user)

    def create_quick_link(self, **overrides):
        values = {
            "creator": self.creator,
            "salon": self.salon,
            "service": self.service,
            "mode": BookingQuickLink.Mode.SERVICE,
            "payload": {
                "mode": BookingQuickLink.Mode.SERVICE,
                "salon_id": self.salon.pk,
                "service_ids": [self.service.pk],
                "stylist_user_id": None,
                "date": "",
                "time": "",
                "summary": {},
            },
        }
        values.update(overrides)
        return BookingQuickLink.objects.create(**values)

    def test_legacy_safe_defaults_are_applied(self):
        quick_link = self.create_quick_link()

        self.assertEqual(
            quick_link.placement,
            BookingQuickLink.Placement.OTHER,
        )
        self.assertEqual(quick_link.campaign_name, "")
        self.assertEqual(quick_link.internal_note, "")
        self.assertEqual(quick_link.opens_count, 0)
        self.assertIsNone(quick_link.last_converted_at)
        self.assertIsNone(quick_link.archived_at)

    def test_placement_choices_match_management_contract(self):
        self.assertEqual(
            set(BookingQuickLink.Placement.values),
            {
                "direct",
                "mirror_label",
                "reception",
                "table_stand",
                "booking_card",
                "instagram_bio",
                "instagram_story",
                "whatsapp",
                "other",
            },
        )

    def test_archived_link_is_not_openable_and_preserves_counters(self):
        quick_link = self.create_quick_link(
            opens_count=7,
            bookings_count=3,
        )

        quick_link.mark_archived()
        quick_link.refresh_from_db()

        self.assertFalse(quick_link.can_open)
        self.assertEqual(quick_link.status_label, "بایگانی‌شده")
        self.assertEqual(quick_link.status_tone, "muted")
        self.assertFalse(quick_link.is_active)
        self.assertIsNotNone(quick_link.archived_at)
        self.assertEqual(quick_link.disabled_at, quick_link.archived_at)
        self.assertEqual(quick_link.opens_count, 7)
        self.assertEqual(quick_link.bookings_count, 3)

    def test_archived_link_cannot_be_reenabled_implicitly(self):
        quick_link = self.create_quick_link(
            archived_at=timezone.now(),
            is_active=False,
        )

        with self.assertRaises(ValidationError) as raised:
            quick_link.mark_enabled()

        self.assertEqual(
            raised.exception.messages,
            ["لینک بایگانی‌شده را نمی‌توان فعال کرد."],
        )
    def test_order_attribution_relation_is_nullable_and_protects_history(self):
        quick_link = self.create_quick_link()
        order = Order.objects.create(
            customer=self.customer,
            salon=self.salon,
            booking_quick_link=quick_link,
            selected_payment_method="pay_in_salon",
        )

        field = Order._meta.get_field("booking_quick_link")

        self.assertTrue(field.null)
        self.assertTrue(field.blank)
        self.assertIs(field.remote_field.on_delete, PROTECT)
        self.assertEqual(order.booking_quick_link_id, quick_link.pk)
        self.assertEqual(
            list(
                quick_link.attributed_orders.values_list(
                    "pk",
                    flat=True,
                )
            ),
            [order.pk],
        )

        with self.assertRaises(ProtectedError):
            quick_link.delete()

        self.assertTrue(BookingQuickLink.objects.filter(pk=quick_link.pk).exists())
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())
