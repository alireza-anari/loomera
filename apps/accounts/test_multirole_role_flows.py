"""Safe attachment of additional roles to an authenticated, existing account."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser, Customer, SalonManager, Stylist
from apps.accounts.services.role_intents import ROLE_INTENT_KEY
from apps.salons.models import SalonMembership
from tests_stage1_helpers import Stage1DomainFactoryMixin


class MultiroleRoleFlowTests(Stage1DomainFactoryMixin, TestCase):
    def test_customer_adds_stylist_without_changing_identity_or_membership(self):
        customer = self.make_customer()
        user = customer.user
        original_password, user_id = user.password, user.pk
        self.client.force_login(user)
        url = reverse("accounts:add_role", kwargs={"kind": "stylist"})
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {"expert": "رنگ مو"})
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.pk, user_id)
        self.assertEqual(user.password, original_password)
        self.assertTrue(user.is_active)
        self.assertEqual(Customer.objects.filter(user=user).count(), 1)
        stylist = Stylist.objects.get(user=user)
        self.assertEqual(stylist.expert, "رنگ مو")
        self.assertFalse(SalonMembership.objects.filter(stylist=stylist).exists())

    def test_manager_can_attach_stylist_without_new_salon_membership(self):
        user = self.make_user()
        manager = SalonManager.objects.create(user=user)
        salon = self.make_salon(manager=manager)
        self.client.force_login(user)
        self.client.post(reverse("accounts:add_role", kwargs={"kind": "stylist"}), {"expert": "ماساژ"})
        self.assertEqual(SalonManager.objects.filter(user=user).count(), 1)
        self.assertEqual(Stylist.objects.filter(user=user).count(), 1)
        self.assertFalse(SalonMembership.objects.filter(salon=salon).exists())

    def test_existing_stylist_attaches_manager_without_overwriting_stylist(self):
        user = self.make_user()
        stylist = Stylist.objects.create(user=user, expert="Original")
        self.client.force_login(user)
        url = reverse("accounts:add_role", kwargs={"kind": "manager"})
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertTrue(SalonManager.objects.filter(user=user).exists())
        stylist.refresh_from_db()
        self.assertEqual(stylist.expert, "Original")

    def test_duplicate_attachment_is_idempotent(self):
        user = self.make_user()
        self.client.force_login(user)
        url = reverse("accounts:add_role", kwargs={"kind": "stylist"})
        self.client.post(url, {"expert": "First"})
        self.client.post(url, {"expert": "Second"})
        self.assertEqual(Stylist.objects.filter(user=user).count(), 1)
        self.assertEqual(Stylist.objects.get(user=user).expert, "First")

    def test_existing_mobile_signup_never_modifies_existing_user(self):
        manager = self.make_salon_manager()
        user = manager.user
        original = (user.pk, user.password, user.is_active, user.name)
        response = self.client.post(reverse("accounts:stylist_signup"), {
            "mobile_number": user.mobile_number,
            "name": "Attacker", "family": "Changed", "expert": "New",
            "password1": "AttackerSecret123!", "password2": "AttackerSecret123!",
            "agree_to_terms": "on",
        })
        self.assertRedirects(response, reverse("accounts:login"), fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertEqual((user.pk, user.password, user.is_active, user.name), original)
        self.assertEqual(CustomUser.objects.filter(mobile_number=user.mobile_number).count(), 1)
        self.assertFalse(Stylist.objects.filter(user=user).exists())
        self.assertEqual(self.client.session[ROLE_INTENT_KEY]["mobile"], user.mobile_number)

    def test_signup_intent_rejects_different_logged_in_account(self):
        target = self.make_user()
        other = self.make_user()
        session = self.client.session
        session[ROLE_INTENT_KEY] = {"mobile": target.mobile_number, "kind": "stylist", "expires_at": 9999999999}
        session.save()
        self.client.post(reverse("accounts:login"), {
            "mobile_number": other.mobile_number, "password": "pass12345",
        })
        self.assertNotIn(ROLE_INTENT_KEY, self.client.session)
        self.assertFalse(Stylist.objects.filter(user=target).exists())
        self.assertFalse(Stylist.objects.filter(user=other).exists())

    def test_invalid_kind_and_unauthenticated_attachment_are_denied(self):
        url = reverse("accounts:add_role", kwargs={"kind": "stylist"})
        self.assertEqual(self.client.post(url, {"expert": "Not authenticated"}).status_code, 302)
        self.assertFalse(Stylist.objects.exists())
        user = self.make_user()
        self.client.force_login(user)
        invalid = reverse("accounts:add_role", kwargs={"kind": "admin"})
        self.assertEqual(self.client.post(invalid).status_code, 404)
        self.assertFalse(Stylist.objects.filter(user=user).exists())
