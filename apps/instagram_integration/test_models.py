from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.accounts.models import CustomUser, SalonManager, Stylist
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus

from .models import InstagramAccountConnection, InstagramConnectionStatus


FERNET_TEST_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


@override_settings(INSTAGRAM_TOKEN_ENCRYPTION_KEY=FERNET_TEST_KEY)
class InstagramAccountConnectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        manager_user = CustomUser.objects.create_user(
            mobile_number="09120000001",
            name="Manager",
            family="Test",
            password="test-password",
        )
        cls.manager = SalonManager.objects.create(
            user=manager_user,
            is_active=True,
        )
        cls.salon_a = Salon.objects.create(
            salon_name="Instagram Salon A",
            salon_manager=cls.manager,
            is_active=True,
        )
        cls.salon_b = Salon.objects.create(
            salon_name="Instagram Salon B",
            salon_manager=cls.manager,
            is_active=True,
        )

        stylist_user = CustomUser.objects.create_user(
            mobile_number="09120000002",
            name="Stylist",
            family="Test",
            password="test-password",
        )
        cls.stylist = Stylist.objects.create(
            user=stylist_user,
            is_active=True,
            expert="hair",
        )
        SalonMembership.objects.create(
            salon=cls.salon_a,
            stylist=cls.stylist,
            status=SalonMembershipStatus.ACTIVE,
        )

    def test_salon_context_is_valid_without_stylist(self):
        connection = InstagramAccountConnection(
            salon=self.salon_a,
            instagram_account_id="ig-salon-a",
            username="salon_a",
        )
        connection.full_clean()
        self.assertEqual(connection.context_kind, "salon")

    def test_stylist_context_requires_active_membership_in_same_salon(self):
        connection = InstagramAccountConnection(
            salon=self.salon_a,
            stylist=self.stylist,
            instagram_account_id="ig-stylist-a",
            username="stylist_a",
        )
        connection.full_clean()
        self.assertEqual(connection.context_kind, "stylist")

    def test_cross_salon_stylist_context_is_rejected(self):
        connection = InstagramAccountConnection(
            salon=self.salon_b,
            stylist=self.stylist,
            instagram_account_id="ig-wrong-salon",
        )
        with self.assertRaises(ValidationError):
            connection.full_clean()

    def test_inactive_membership_is_rejected(self):
        membership = SalonMembership.objects.get(
            salon=self.salon_a,
            stylist=self.stylist,
        )
        membership.status = SalonMembershipStatus.PAUSED
        membership.save(update_fields=["status"])

        connection = InstagramAccountConnection(
            salon=self.salon_a,
            stylist=self.stylist,
            instagram_account_id="ig-paused-stylist",
        )
        with self.assertRaises(ValidationError):
            connection.full_clean()

    def test_token_is_encrypted_at_rest_and_round_trips(self):
        connection = InstagramAccountConnection(
            salon=self.salon_a,
            instagram_account_id="ig-token-test",
        )
        raw = "EAAB-test-token-value"
        connection.set_access_token(raw)

        self.assertNotEqual(connection.encrypted_access_token, raw)
        self.assertNotIn(raw, connection.encrypted_access_token)
        self.assertEqual(connection.get_access_token(), raw)

    def test_disconnection_removes_stored_token(self):
        connection = InstagramAccountConnection(
            salon=self.salon_a,
            instagram_account_id="ig-disconnect-test",
        )
        connection.set_access_token("temporary-token")
        connection.mark_connected()
        connection.save()

        connection.mark_disconnected()
        connection.save()

        connection.refresh_from_db()
        self.assertEqual(connection.status, InstagramConnectionStatus.DISCONNECTED)
        self.assertEqual(connection.encrypted_access_token, "")
        self.assertIsNotNone(connection.disconnected_at)

    def test_same_instagram_account_cannot_bind_to_two_contexts(self):
        InstagramAccountConnection.objects.create(
            salon=self.salon_a,
            instagram_account_id="ig-unique-account",
        )
        with self.assertRaises(ValidationError):
            InstagramAccountConnection.objects.create(
                salon=self.salon_b,
                instagram_account_id="ig-unique-account",
            )

    def test_only_one_salon_level_connection_per_salon(self):
        InstagramAccountConnection.objects.create(
            salon=self.salon_a,
            instagram_account_id="ig-first-salon",
        )
        with self.assertRaises(ValidationError):
            InstagramAccountConnection.objects.create(
                salon=self.salon_a,
                instagram_account_id="ig-second-salon",
            )

    def test_runtime_context_turns_invalid_if_membership_ends(self):
        connection = InstagramAccountConnection(
            salon=self.salon_a,
            stylist=self.stylist,
            instagram_account_id="ig-runtime-context",
        )
        connection.mark_connected()
        connection.save()
        self.assertTrue(connection.is_context_active())

        membership = SalonMembership.objects.get(
            salon=self.salon_a,
            stylist=self.stylist,
        )
        membership.status = SalonMembershipStatus.ENDED
        membership.save(update_fields=["status"])

        self.assertFalse(connection.is_context_active())
