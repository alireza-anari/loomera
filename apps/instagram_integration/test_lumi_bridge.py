from datetime import date, time
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.accounts.models import CustomUser, SalonManager, Stylist
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus
from apps.services.models import ServicePrice, Services

from .lumi_bridge import process_inbound_with_lumi
from .models import InstagramAccountConnection, InstagramInboundMessage


FERNET_TEST_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


@override_settings(
    INSTAGRAM_TOKEN_ENCRYPTION_KEY=FERNET_TEST_KEY,
    PUBLIC_BASE_URL="https://staging.example.test",
)
class InstagramLumiBridgeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        manager_user = CustomUser.objects.create_user(
            mobile_number="09123333001", name="Lumi", family="Manager",
            password="test-password",
        )
        manager_user.is_active = True
        manager_user.save(update_fields=["is_active"])
        cls.manager = SalonManager.objects.create(user=manager_user, is_active=True)

        cls.salon_a = Salon.objects.create(
            salon_name="Salon A", salon_manager=cls.manager,
            is_active=True, address="تهران، خیابان نمونه",
        )
        cls.salon_b = Salon.objects.create(
            salon_name="Salon B", salon_manager=cls.manager, is_active=True,
        )

        stylist_user = CustomUser.objects.create_user(
            mobile_number="09123333002", name="سارا", family="احمدی",
            password="test-password",
        )
        stylist_user.is_active = True
        stylist_user.save(update_fields=["is_active"])
        cls.stylist_a = Stylist.objects.create(
            user=stylist_user, is_active=True, expert="hair",
            display_name="سارا احمدی",
        )
        cls.salon_a.stylists.add(cls.stylist_a)
        SalonMembership.objects.create(
            salon=cls.salon_a, stylist=cls.stylist_a,
            status=SalonMembershipStatus.ACTIVE,
        )

        cls.keratin = Services.objects.create(
            service_name="کراتین مو", is_active=True,
            is_platform_catalog=False, base_price=1500000,
            duration_minutes=90,
        )
        cls.haircut = Services.objects.create(
            service_name="کوتاهی مو", is_active=True,
            is_platform_catalog=False, base_price=500000,
            duration_minutes=30,
        )
        cls.foreign_service = Services.objects.create(
            service_name="خدمت سالن دیگر", is_active=True,
            is_platform_catalog=False, base_price=999999,
            duration_minutes=30,
        )
        cls.salon_a.services.add(cls.keratin, cls.haircut)
        cls.salon_b.services.add(cls.foreign_service)
        cls.keratin.stylists.add(cls.stylist_a)
        ServicePrice.objects.create(
            stylist=cls.stylist_a, service=cls.keratin, price=1700000,
        )

        cls.salon_connection = InstagramAccountConnection(
            salon=cls.salon_a, instagram_account_id="ig-lumi-salon",
        )
        cls.salon_connection.mark_connected()
        cls.salon_connection.save()

        cls.stylist_connection = InstagramAccountConnection(
            salon=cls.salon_a, stylist=cls.stylist_a,
            instagram_account_id="ig-lumi-stylist",
        )
        cls.stylist_connection.mark_connected()
        cls.stylist_connection.save()

    def _inbound(self, connection, text, mid):
        return InstagramInboundMessage.objects.create(
            connection=connection,
            provider_message_id=mid,
            sender_igsid=f"sender-{mid}",
            recipient_instagram_account_id=connection.instagram_account_id,
            message_text=text,
        )

    def test_salon_service_list_never_leaks_other_salon_service(self):
        result = process_inbound_with_lumi(
            self._inbound(self.salon_connection, "چه خدماتی دارید؟", "mid-services-salon").pk
        )
        self.assertIn("کراتین مو", result.lumi_reply_text)
        self.assertIn("کوتاهی مو", result.lumi_reply_text)
        self.assertNotIn("خدمت سالن دیگر", result.lumi_reply_text)

    def test_stylist_service_scope_only_returns_that_stylist_services(self):
        result = process_inbound_with_lumi(
            self._inbound(self.stylist_connection, "چه خدماتی انجام میدید؟", "mid-services-stylist").pk
        )
        self.assertIn("کراتین مو", result.lumi_reply_text)
        self.assertNotIn("کوتاهی مو", result.lumi_reply_text)

    def test_stylist_price_uses_that_stylist_price(self):
        result = process_inbound_with_lumi(
            self._inbound(self.stylist_connection, "قیمت کراتین چنده؟", "mid-price-stylist").pk
        )
        self.assertIn("1,700,000", result.lumi_reply_text)
        self.assertEqual(result.lumi_facts["price"]["price"], 1700000)

    @patch("apps.help_center.customer_inquiry.get_upcoming_available_stylists_for_service")
    def test_stylist_availability_is_for_same_context(self, availability):
        availability.return_value = [{
            "stylist": self.stylist_a,
            "first_slot": {
                "date": date(2026, 9, 1),
                "time": time(10, 30),
                "end_time": time(12, 0),
            },
            "price": 1700000,
        }]
        result = process_inbound_with_lumi(
            self._inbound(
                self.stylist_connection,
                "اولین وقت خالی برای کراتین کیه؟",
                "mid-availability-stylist",
            ).pk
        )
        kwargs = availability.call_args.kwargs
        self.assertEqual(kwargs["salon"], self.salon_a)
        self.assertEqual(kwargs["service"], self.keratin)
        self.assertEqual(result.lumi_facts["availability"]["stylist_id"], self.stylist_a.pk)
        self.assertIn("10:30", result.lumi_reply_text)
        self.assertIn("staging.example.test", result.lumi_reply_text)

    def test_availability_without_service_asks_for_service(self):
        result = process_inbound_with_lumi(
            self._inbound(self.salon_connection, "اولین وقت خالیتون کیه؟", "mid-availability-clarify").pk
        )
        self.assertEqual(result.lumi_disposition, "clarification")
        self.assertIn("کدوم خدمت", result.lumi_reply_text)

    def test_private_appointment_operation_is_not_executed(self):
        result = process_inbound_with_lumi(
            self._inbound(self.salon_connection, "نوبتم رو لغو کن", "mid-private-operation").pk
        )
        self.assertEqual(result.lumi_disposition, "out_of_scope")
        self.assertEqual(result.lumi_facts["reason"], "private_operation_not_supported")

    def test_unrelated_question_gets_business_scope_reply(self):
        result = process_inbound_with_lumi(
            self._inbound(self.salon_connection, "آیفون بهتره یا سامسونگ؟", "mid-unrelated").pk
        )
        self.assertEqual(result.lumi_disposition, "out_of_scope")
        self.assertIn("دستیار این مجموعه", result.lumi_reply_text)

    def test_inactive_context_never_reaches_business_inquiry(self):
        self.salon_a.is_active = False
        self.salon_a.save(update_fields=["is_active"])
        inbound = self._inbound(
            self.salon_connection, "قیمت کراتین چنده؟", "mid-inactive-context"
        )
        with patch("apps.instagram_integration.lumi_bridge.answer_business_customer_inquiry") as answerer:
            result = process_inbound_with_lumi(inbound.pk)
        answerer.assert_not_called()
        self.assertTrue(result.requires_human)
        self.assertEqual(result.lumi_disposition, "human_handoff")

    def test_processing_is_idempotent(self):
        inbound = self._inbound(self.salon_connection, "آدرس کجاست؟", "mid-idempotent")
        first = process_inbound_with_lumi(inbound.pk)
        original = first.lumi_reply_text
        self.salon_a.address = "آدرس تغییر کرده"
        self.salon_a.save(update_fields=["address"])
        second = process_inbound_with_lumi(inbound.pk)
        self.assertEqual(second.lumi_reply_text, original)
