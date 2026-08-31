from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser, SalonManager, Stylist
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus

from .models import InstagramAccountConnection, InstagramConnectionStatus
from .oauth import InstagramOAuthResult, exchange_code_for_connection
from .subscriptions import InstagramWebhookSubscriptionError


FERNET_TEST_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="

BASE_SETTINGS = {
    "INSTAGRAM_ENABLED": True,
    "INSTAGRAM_MESSAGING_ENABLED": True,
    "INSTAGRAM_APP_ID": "123456789",
    "INSTAGRAM_APP_SECRET": "test-secret",
    "INSTAGRAM_REDIRECT_URI": "https://staging.example.test/instagram/oauth/callback/",
    "INSTAGRAM_WEBHOOK_VERIFY_TOKEN": "test-verify",
    "INSTAGRAM_TOKEN_ENCRYPTION_KEY": FERNET_TEST_KEY,
    "INSTAGRAM_LOGIN_SCOPES": [
        "instagram_business_basic",
        "instagram_business_manage_messages",
    ],
    "INSTAGRAM_REQUEST_TIMEOUT": 10,
    "INSTAGRAM_OAUTH_STATE_TTL_SECONDS": 600,
    "INSTAGRAM_OAUTH_AUTHORIZE_URL": "https://www.instagram.com/oauth/authorize",
    "INSTAGRAM_OAUTH_TOKEN_URL": "https://api.instagram.com/oauth/access_token",
    "INSTAGRAM_GRAPH_BASE_URL": "https://graph.instagram.com",
}


@override_settings(**BASE_SETTINGS)
class InstagramOAuthViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = CustomUser.objects.create_user(
            mobile_number="09121111101",
            name="Manager",
            family="OAuth",
            password="test-password",
        )
        cls.manager_user.is_active = True
        cls.manager_user.save(update_fields=["is_active"])
        cls.manager = SalonManager.objects.create(
            user=cls.manager_user,
            is_active=True,
        )
        cls.salon_a = Salon.objects.create(
            salon_name="OAuth Salon A",
            salon_manager=cls.manager,
            is_active=True,
        )
        cls.salon_b = Salon.objects.create(
            salon_name="OAuth Salon B",
            salon_manager=cls.manager,
            is_active=True,
        )

        other_user = CustomUser.objects.create_user(
            mobile_number="09121111102",
            name="Other",
            family="Manager",
            password="test-password",
        )
        other_user.is_active = True
        other_user.save(update_fields=["is_active"])
        cls.other_manager = SalonManager.objects.create(
            user=other_user,
            is_active=True,
        )
        cls.other_salon = Salon.objects.create(
            salon_name="Other Salon",
            salon_manager=cls.other_manager,
            is_active=True,
        )

        cls.stylist_user = CustomUser.objects.create_user(
            mobile_number="09121111103",
            name="Stylist",
            family="OAuth",
            password="test-password",
        )
        cls.stylist_user.is_active = True
        cls.stylist_user.save(update_fields=["is_active"])
        cls.stylist = Stylist.objects.create(
            user=cls.stylist_user,
            is_active=True,
            expert="hair",
        )
        SalonMembership.objects.create(
            salon=cls.salon_a,
            stylist=cls.stylist,
            status=SalonMembershipStatus.ACTIVE,
        )

    def _start(self, user, kind, salon):
        self.client.force_login(user)
        return self.client.get(
            reverse(
                "instagram_integration:oauth_start",
                kwargs={"context_kind": kind, "salon_id": salon.pk},
            )
        )

    def _state(self, response):
        self.assertEqual(response.status_code, 302)
        return parse_qs(urlparse(response["Location"]).query)["state"][0]

    def test_manager_can_start_for_owned_salon(self):
        response = self._start(self.manager_user, "salon", self.salon_a)
        self.assertEqual(response.status_code, 302)
        params = parse_qs(urlparse(response["Location"]).query)
        self.assertEqual(params["client_id"], ["123456789"])
        self.assertIn(
            "instagram_business_manage_messages",
            params["scope"][0],
        )

    def test_inactive_manager_role_cannot_start_oauth(self):
        self.manager.is_active = False
        self.manager.save(update_fields=["is_active"])

        response = self._start(
            self.manager_user,
            "salon",
            self.salon_a,
        )
        self.assertEqual(response.status_code, 403)

        self.manager.is_active = True
        self.manager.save(update_fields=["is_active"])

    def test_manager_cannot_start_for_other_manager_salon(self):
        response = self._start(
            self.manager_user,
            "salon",
            self.other_salon,
        )
        self.assertEqual(response.status_code, 404)

    def test_stylist_only_active_membership_salon(self):
        response = self._start(
            self.stylist_user,
            "stylist",
            self.salon_a,
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.get(
            reverse(
                "instagram_integration:oauth_start",
                kwargs={
                    "context_kind": "stylist",
                    "salon_id": self.salon_b.pk,
                },
            )
        )
        self.assertEqual(response.status_code, 404)

    @override_settings(INSTAGRAM_ENABLED=False)
    def test_disabled_flag_denies_oauth_start(self):
        response = self._start(
            self.manager_user,
            "salon",
            self.salon_a,
        )
        self.assertEqual(response.status_code, 403)

    def test_tampered_state_never_calls_provider(self):
        response = self._start(
            self.manager_user,
            "salon",
            self.salon_a,
        )
        state = self._state(response)

        with patch(
            "apps.instagram_integration.views.exchange_code_for_connection"
        ) as provider:
            callback = self.client.get(
                reverse("instagram_integration:oauth_callback"),
                {"state": state + "x", "code": "abc"},
            )

        self.assertEqual(callback.status_code, 302)
        provider.assert_not_called()

    def test_state_is_single_use(self):
        response = self._start(
            self.manager_user,
            "salon",
            self.salon_a,
        )
        state = self._state(response)

        result = InstagramOAuthResult(
            account_id="ig-replay",
            username="replay",
            access_token="secret",
            expires_in=3600,
            scopes=(
                "instagram_business_basic",
                "instagram_business_manage_messages",
            ),
        )

        with patch(
            "apps.instagram_integration.views.exchange_code_for_connection",
            return_value=result,
        ) as provider:
            first = self.client.get(
                reverse("instagram_integration:oauth_callback"),
                {"state": state, "code": "first"},
            )
            second = self.client.get(
                reverse("instagram_integration:oauth_callback"),
                {"state": state, "code": "second"},
            )

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(provider.call_count, 1)

    @patch(
        "apps.instagram_integration.views.subscribe_professional_account"
    )
    def test_salon_callback_persists_encrypted_token(self, subscribe):
        response = self._start(
            self.manager_user,
            "salon",
            self.salon_a,
        )
        state = self._state(response)

        result = InstagramOAuthResult(
            account_id="ig-salon",
            username="salon",
            access_token="plaintext-must-not-remain",
            expires_in=3600,
            scopes=(
                "instagram_business_basic",
                "instagram_business_manage_messages",
            ),
        )

        with patch(
            "apps.instagram_integration.views.exchange_code_for_connection",
            return_value=result,
        ):
            callback = self.client.get(
                reverse("instagram_integration:oauth_callback"),
                {"state": state, "code": "good"},
            )

        self.assertEqual(callback.status_code, 302)
        connection = InstagramAccountConnection.objects.get(
            instagram_account_id="ig-salon"
        )
        self.assertEqual(connection.salon, self.salon_a)
        self.assertIsNone(connection.stylist)
        self.assertEqual(
            connection.status,
            InstagramConnectionStatus.CONNECTED,
        )
        self.assertNotEqual(
            connection.encrypted_access_token,
            "plaintext-must-not-remain",
        )
        self.assertEqual(
            connection.get_access_token(),
            "plaintext-must-not-remain",
        )

    @patch(
        "apps.instagram_integration.views.subscribe_professional_account"
    )
    def test_stylist_callback_keeps_stylist_and_salon_context(self, subscribe):
        response = self._start(
            self.stylist_user,
            "stylist",
            self.salon_a,
        )
        state = self._state(response)

        result = InstagramOAuthResult(
            account_id="ig-stylist",
            username="stylist",
            access_token="stylist-secret",
            expires_in=3600,
            scopes=(
                "instagram_business_basic",
                "instagram_business_manage_messages",
            ),
        )

        with patch(
            "apps.instagram_integration.views.exchange_code_for_connection",
            return_value=result,
        ):
            self.client.get(
                reverse("instagram_integration:oauth_callback"),
                {"state": state, "code": "good"},
            )

        connection = InstagramAccountConnection.objects.get(
            instagram_account_id="ig-stylist"
        )
        self.assertEqual(connection.salon, self.salon_a)
        self.assertEqual(connection.stylist, self.stylist)

    def test_same_instagram_account_cannot_move_to_other_context(self):
        InstagramAccountConnection.objects.create(
            salon=self.salon_a,
            instagram_account_id="ig-shared",
        )

        response = self._start(
            self.manager_user,
            "salon",
            self.salon_b,
        )
        state = self._state(response)

        result = InstagramOAuthResult(
            account_id="ig-shared",
            username="shared",
            access_token="secret-two",
            expires_in=3600,
            scopes=(
                "instagram_business_basic",
                "instagram_business_manage_messages",
            ),
        )

        with patch(
            "apps.instagram_integration.views.exchange_code_for_connection",
            return_value=result,
        ):
            self.client.get(
                reverse("instagram_integration:oauth_callback"),
                {"state": state, "code": "good"},
            )

        original = InstagramAccountConnection.objects.get(
            instagram_account_id="ig-shared"
        )
        self.assertEqual(original.salon, self.salon_a)

    def test_disconnect_clears_token_even_when_feature_off(self):
        connection = InstagramAccountConnection(
            salon=self.salon_a,
            instagram_account_id="ig-disconnect",
        )
        connection.set_access_token("disconnect-me")
        connection.mark_connected()
        connection.save()

        self.client.force_login(self.manager_user)
        with self.settings(
            INSTAGRAM_ENABLED=False,
            INSTAGRAM_MESSAGING_ENABLED=False,
        ):
            response = self.client.post(
                reverse(
                    "instagram_integration:disconnect",
                    kwargs={
                        "context_kind": "salon",
                        "salon_id": self.salon_a.pk,
                    },
                )
            )

        self.assertEqual(response.status_code, 302)
        connection.refresh_from_db()
        self.assertEqual(
            connection.status,
            InstagramConnectionStatus.DISCONNECTED,
        )
        self.assertEqual(connection.encrypted_access_token, "")



    @patch(
        "apps.instagram_integration.views.subscribe_professional_account"
    )
    @patch(
        "apps.instagram_integration.views.exchange_code_for_connection"
    )
    def test_oauth_subscribes_connected_account_to_messages(
        self,
        exchange,
        subscribe,
    ):
        response = self._start(
            self.manager_user,
            "salon",
            self.salon_a,
        )
        state = self._state(response)

        exchange.return_value = InstagramOAuthResult(
            account_id="ig-subscribe-test",
            username="subscribe_test",
            access_token="subscription-secret",
            expires_in=3600,
            scopes=(
                "instagram_business_basic",
                "instagram_business_manage_messages",
            ),
        )

        callback = self.client.get(
            reverse("instagram_integration:oauth_callback"),
            {"state": state, "code": "good"},
        )

        self.assertEqual(callback.status_code, 302)
        subscribe.assert_called_once_with(
            account_id="ig-subscribe-test",
            access_token="subscription-secret",
        )
        connection = InstagramAccountConnection.objects.get(
            instagram_account_id="ig-subscribe-test"
        )
        self.assertIsNotNone(connection.webhook_subscribed_at)

    @patch(
        "apps.instagram_integration.views.subscribe_professional_account"
    )
    @patch(
        "apps.instagram_integration.views.exchange_code_for_connection"
    )
    def test_subscription_failure_prevents_half_connected_account(
        self,
        exchange,
        subscribe,
    ):
        response = self._start(
            self.manager_user,
            "salon",
            self.salon_a,
        )
        state = self._state(response)

        exchange.return_value = InstagramOAuthResult(
            account_id="ig-subscribe-fail",
            username="subscribe_fail",
            access_token="subscription-secret",
            expires_in=3600,
            scopes=(
                "instagram_business_basic",
                "instagram_business_manage_messages",
            ),
        )
        subscribe.side_effect = InstagramWebhookSubscriptionError(
            "subscription failed"
        )

        callback = self.client.get(
            reverse("instagram_integration:oauth_callback"),
            {"state": state, "code": "good"},
        )

        self.assertEqual(callback.status_code, 302)
        self.assertFalse(
            InstagramAccountConnection.objects.filter(
                instagram_account_id="ig-subscribe-fail"
            ).exists()
        )


@override_settings(**BASE_SETTINGS)
class InstagramProviderClientTests(TestCase):
    @patch("apps.instagram_integration.oauth.requests.get")
    @patch("apps.instagram_integration.oauth.requests.post")
    def test_exchange_gets_long_token_and_profile(
        self,
        mock_post,
        mock_get,
    ):
        short_response = Mock()
        short_response.ok = True
        short_response.json.return_value = {
            "access_token": "short-secret",
        }
        mock_post.return_value = short_response

        long_response = Mock()
        long_response.ok = True
        long_response.json.return_value = {
            "access_token": "long-secret",
            "expires_in": 5184000,
        }

        profile_response = Mock()
        profile_response.ok = True
        profile_response.json.return_value = {
            "id": "ig-123",
            "username": "loomera_test",
        }
        mock_get.side_effect = [
            long_response,
            profile_response,
        ]

        result = exchange_code_for_connection(code="auth-code")

        self.assertEqual(result.account_id, "ig-123")
        self.assertEqual(result.username, "loomera_test")
        self.assertEqual(result.access_token, "long-secret")
        self.assertEqual(result.expires_in, 5184000)

        profile_call = mock_get.call_args_list[1]
        self.assertEqual(
            profile_call.kwargs["headers"]["Authorization"],
            "Bearer long-secret",
        )
