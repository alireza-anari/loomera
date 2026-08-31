import hashlib
import hmac
import json

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser, SalonManager, Stylist
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus

from .models import (
    InstagramAccountConnection,
    InstagramInboundMessage,
)


FERNET_TEST_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="

WEBHOOK_SETTINGS = {
    "INSTAGRAM_ENABLED": True,
    "INSTAGRAM_MESSAGING_ENABLED": True,
    "INSTAGRAM_APP_ID": "123456789",
    "INSTAGRAM_APP_SECRET": "webhook-secret",
    "INSTAGRAM_REDIRECT_URI": "https://staging.example.test/instagram/oauth/callback/",
    "INSTAGRAM_WEBHOOK_VERIFY_TOKEN": "verify-me",
    "INSTAGRAM_TOKEN_ENCRYPTION_KEY": FERNET_TEST_KEY,
    "INSTAGRAM_LOGIN_SCOPES": [
        "instagram_business_basic",
        "instagram_business_manage_messages",
    ],
    "INSTAGRAM_REQUEST_TIMEOUT": 10,
    "INSTAGRAM_WEBHOOK_MAX_BYTES": 256 * 1024,
}


@override_settings(**WEBHOOK_SETTINGS)
class InstagramWebhookTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        manager_user = CustomUser.objects.create_user(
            mobile_number="09122222001",
            name="Webhook",
            family="Manager",
            password="test-password",
        )
        cls.manager = SalonManager.objects.create(
            user=manager_user,
            is_active=True,
        )
        cls.salon = Salon.objects.create(
            salon_name="Webhook Salon",
            salon_manager=cls.manager,
            is_active=True,
        )

        cls.salon_connection = InstagramAccountConnection(
            salon=cls.salon,
            instagram_account_id="ig-salon-webhook",
            username="salon_webhook",
        )
        cls.salon_connection.mark_connected()
        cls.salon_connection.save()

        stylist_user = CustomUser.objects.create_user(
            mobile_number="09122222002",
            name="Webhook",
            family="Stylist",
            password="test-password",
        )
        cls.stylist = Stylist.objects.create(
            user=stylist_user,
            is_active=True,
            expert="hair",
        )
        cls.membership = SalonMembership.objects.create(
            salon=cls.salon,
            stylist=cls.stylist,
            status=SalonMembershipStatus.ACTIVE,
        )

        cls.stylist_connection = InstagramAccountConnection(
            salon=cls.salon,
            stylist=cls.stylist,
            instagram_account_id="ig-stylist-webhook",
            username="stylist_webhook",
        )
        cls.stylist_connection.mark_connected()
        cls.stylist_connection.save()

    def _url(self):
        return reverse("instagram_integration:webhook")

    def _signature(self, body):
        digest = hmac.new(
            b"webhook-secret",
            body,
            hashlib.sha256,
        ).hexdigest()
        return "sha256=" + digest

    def _payload(
        self,
        *,
        recipient="ig-salon-webhook",
        mid="mid-1",
        text="Hello",
        sender="customer-1",
        extra_message=None,
    ):
        message = {
            "mid": mid,
            "text": text,
        }
        if extra_message:
            message.update(extra_message)

        return {
            "object": "instagram",
            "entry": [
                {
                    "id": recipient,
                    "time": 1788192000000,
                    "messaging": [
                        {
                            "sender": {"id": sender},
                            "recipient": {"id": recipient},
                            "timestamp": 1788192000123,
                            "message": message,
                        }
                    ],
                }
            ],
        }

    def _post(self, payload, *, signature=True):
        body = json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {}
        if signature:
            headers["HTTP_X_HUB_SIGNATURE_256"] = self._signature(body)

        return self.client.post(
            self._url(),
            data=body,
            content_type="application/json",
            **headers,
        )

    def test_get_verification_returns_challenge(self):
        response = self.client.get(
            self._url(),
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "verify-me",
                "hub.challenge": "CHALLENGE_OK",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"CHALLENGE_OK")

    def test_get_verification_rejects_wrong_token(self):
        response = self.client.get(
            self._url(),
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong",
                "hub.challenge": "NO",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_invalid_signature_is_rejected(self):
        response = self._post(self._payload(), signature=False)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(InstagramInboundMessage.objects.count(), 0)

    def test_valid_customer_message_routes_to_salon_connection(self):
        response = self._post(self._payload())
        self.assertEqual(response.status_code, 200)

        inbound = InstagramInboundMessage.objects.get(
            provider_message_id="mid-1"
        )
        self.assertEqual(inbound.connection, self.salon_connection)
        self.assertEqual(inbound.connection.salon, self.salon)
        self.assertIsNone(inbound.connection.stylist)
        self.assertEqual(inbound.sender_igsid, "customer-1")
        self.assertEqual(inbound.message_text, "Hello")

    def test_valid_customer_message_routes_to_stylist_context(self):
        response = self._post(
            self._payload(
                recipient="ig-stylist-webhook",
                mid="mid-stylist",
                sender="customer-stylist",
                text="first free time?",
            )
        )
        self.assertEqual(response.status_code, 200)

        inbound = InstagramInboundMessage.objects.get(
            provider_message_id="mid-stylist"
        )
        self.assertEqual(inbound.connection, self.stylist_connection)
        self.assertEqual(inbound.connection.salon, self.salon)
        self.assertEqual(inbound.connection.stylist, self.stylist)

    def test_duplicate_message_id_is_persisted_once(self):
        payload = self._payload(mid="mid-duplicate")

        first = self._post(payload)
        second = self._post(payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            InstagramInboundMessage.objects.filter(
                provider_message_id="mid-duplicate"
            ).count(),
            1,
        )

    def test_unknown_recipient_is_acknowledged_but_not_persisted(self):
        response = self._post(
            self._payload(
                recipient="unknown-account",
                mid="mid-unknown",
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            InstagramInboundMessage.objects.filter(
                provider_message_id="mid-unknown"
            ).exists()
        )

    def test_echo_message_is_ignored(self):
        response = self._post(
            self._payload(
                mid="mid-echo",
                extra_message={"is_echo": True},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            InstagramInboundMessage.objects.filter(
                provider_message_id="mid-echo"
            ).exists()
        )

    def test_inactive_stylist_membership_stops_routing(self):
        self.membership.status = SalonMembershipStatus.ENDED
        self.membership.save(update_fields=["status"])

        response = self._post(
            self._payload(
                recipient="ig-stylist-webhook",
                mid="mid-ended-membership",
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            InstagramInboundMessage.objects.filter(
                provider_message_id="mid-ended-membership"
            ).exists()
        )

    @override_settings(
        INSTAGRAM_ENABLED=False,
        INSTAGRAM_MESSAGING_ENABLED=False,
    )
    def test_disabled_mode_acknowledges_without_side_effect(self):
        response = self._post(
            self._payload(mid="mid-disabled"),
            signature=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            InstagramInboundMessage.objects.filter(
                provider_message_id="mid-disabled"
            ).exists()
        )

    def test_entry_and_recipient_account_mismatch_is_ignored(self):
        payload = self._payload(mid="mid-mismatch")
        payload["entry"][0]["id"] = "different-business-id"

        response = self._post(payload)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            InstagramInboundMessage.objects.filter(
                provider_message_id="mid-mismatch"
            ).exists()
        )
