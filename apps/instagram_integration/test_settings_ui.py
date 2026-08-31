from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser, SalonManager, Stylist
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus

from .models import InstagramAccountConnection


FERNET_TEST_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


@override_settings(
    INSTAGRAM_TOKEN_ENCRYPTION_KEY=FERNET_TEST_KEY,
    INSTAGRAM_ENABLED=True,
    INSTAGRAM_MESSAGING_ENABLED=True,
)
class InstagramSettingsUiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        manager_user = CustomUser.objects.create_user(
            mobile_number="09127777001",
            name="UI",
            family="Manager",
            password="test-password",
        )
        manager_user.is_active = True
        manager_user.save(update_fields=["is_active"])
        cls.manager_user = manager_user

        cls.manager = SalonManager.objects.create(
            user=manager_user,
            is_active=True,
        )
        cls.salon = Salon.objects.create(
            salon_name="UI Salon",
            salon_manager=cls.manager,
            is_active=True,
            address="تهران",
        )

        stylist_user = CustomUser.objects.create_user(
            mobile_number="09127777002",
            name="UI",
            family="Stylist",
            password="test-password",
        )
        stylist_user.is_active = True
        stylist_user.save(update_fields=["is_active"])
        cls.stylist_user = stylist_user

        cls.stylist = Stylist.objects.create(
            user=stylist_user,
            is_active=True,
            expert="hair",
        )
        cls.salon.stylists.add(cls.stylist)
        SalonMembership.objects.create(
            salon=cls.salon,
            stylist=cls.stylist,
            status=SalonMembershipStatus.ACTIVE,
        )

    def _settings_url(self, kind):
        return reverse(
            "instagram_integration:connection_settings",
            kwargs={
                "context_kind": kind,
                "salon_id": self.salon.pk,
            },
        )

    def test_manager_can_open_salon_instagram_settings(self):
        self.client.force_login(self.manager_user)
        response = self.client.get(self._settings_url("salon"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Instagram و Lumi")
        self.assertContains(response, "UI Salon")
        self.assertContains(response, "اتصال Instagram")

    def test_stylist_can_open_stylist_instagram_settings(self):
        self.client.force_login(self.stylist_user)
        response = self.client.get(self._settings_url("stylist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Instagram و Lumi")
        self.assertContains(response, "متخصص در UI Salon")

    def test_manager_settings_hub_contains_instagram_entry(self):
        self.client.force_login(self.manager_user)
        response = self.client.get(reverse("dashboards:workspace_settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Instagram و Lumi")
        self.assertContains(response, self._settings_url("salon"))

    def test_stylist_settings_hub_contains_instagram_entry(self):
        self.client.force_login(self.stylist_user)
        response = self.client.get(reverse("dashboards:stylist_settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Instagram و Lumi")
        self.assertContains(response, self._settings_url("stylist"))

    def test_connected_account_status_is_visible_without_token_exposure(self):
        connection = InstagramAccountConnection(
            salon=self.salon,
            instagram_account_id="ig-ui-123",
            username="ui_salon",
            granted_scopes=[
                "instagram_business_basic",
                "instagram_business_manage_messages",
            ],
        )
        connection.set_access_token("never-render-this-token")
        connection.mark_connected()
        connection.webhook_subscribed_at = timezone.now()
        connection.save()

        self.client.force_login(self.manager_user)
        response = self.client.get(self._settings_url("salon"))
        self.assertContains(response, "@ui_salon")
        self.assertContains(response, "متصل و آماده دریافت پیام")
        self.assertNotContains(response, "never-render-this-token")

    @override_settings(
        INSTAGRAM_ENABLED=False,
        INSTAGRAM_MESSAGING_ENABLED=False,
    )
    def test_disabled_environment_shows_safe_inactive_state(self):
        self.client.force_login(self.manager_user)
        response = self.client.get(self._settings_url("salon"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "اتصال Instagram هنوز در این محیط فعال نشده است",
        )
