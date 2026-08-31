import hashlib
import hmac
import json
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser, SalonManager
from apps.salons.models import Salon

from .models import InstagramAccountConnection, InstagramInboundMessage
from .tasks import process_instagram_inbound_message


FERNET_TEST_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="

PIPELINE_SETTINGS = {
    "INSTAGRAM_ENABLED": True,
    "INSTAGRAM_MESSAGING_ENABLED": True,
    "INSTAGRAM_SEND_ENABLED": True,
    "INSTAGRAM_AUTO_REPLY_ENABLED": True,
    "INSTAGRAM_APP_SECRET": "pipeline-secret",
    "INSTAGRAM_WEBHOOK_VERIFY_TOKEN": "verify-pipeline",
    "INSTAGRAM_TOKEN_ENCRYPTION_KEY": FERNET_TEST_KEY,
    "LOOMERA_ENABLE_CELERY": True,
    "CELERY_TASK_ALWAYS_EAGER": False,
}


@override_settings(**PIPELINE_SETTINGS)
class InstagramWebhookPipelineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = CustomUser.objects.create_user(
            mobile_number="09125555001",
            name="Pipeline",
            family="Manager",
            password="test-password",
        )
        user.is_active = True
        user.save(update_fields=["is_active"])

        cls.manager = SalonManager.objects.create(
            user=user,
            is_active=True,
        )
        cls.salon = Salon.objects.create(
            salon_name="Pipeline Salon",
            salon_manager=cls.manager,
            is_active=True,
        )
        cls.connection = InstagramAccountConnection(
            salon=cls.salon,
            instagram_account_id="ig-pipeline-business",
            username="pipeline_salon",
            granted_scopes=[
                "instagram_business_basic",
                "instagram_business_manage_messages",
            ],
        )
        cls.connection.set_access_token("pipeline-token")
        cls.connection.mark_connected()
        cls.connection.save()

    def _url(self):
        return reverse("instagram_integration:webhook")

    def _payload(self, mid="pipeline-mid-1"):
        return {
            "object": "instagram",
            "entry": [
                {
                    "id": "ig-pipeline-business",
                    "messaging": [
                        {
                            "sender": {"id": "customer-pipeline-1"},
                            "recipient": {"id": "ig-pipeline-business"},
                            "timestamp": 1788192000123,
                            "message": {
                                "mid": mid,
                                "text": "قیمت خدمات چقدره؟",
                            },
                        }
                    ],
                }
            ],
        }

    def _post(self, payload):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        digest = hmac.new(
            b"pipeline-secret",
            body,
            hashlib.sha256,
        ).hexdigest()

        return self.client.post(
            self._url(),
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256="sha256=" + digest,
        )

    @patch(
        "apps.instagram_integration.tasks."
        "process_instagram_inbound_message.delay"
    )
    def test_new_dm_is_enqueued_once_after_commit(self, delay):
        with self.captureOnCommitCallbacks(execute=True):
            response = self._post(self._payload("pipeline-enqueue-mid"))

        self.assertEqual(response.status_code, 200)
        inbound = InstagramInboundMessage.objects.get(
            provider_message_id="pipeline-enqueue-mid"
        )
        delay.assert_called_once_with(inbound.pk)

    @patch(
        "apps.instagram_integration.tasks."
        "process_instagram_inbound_message.delay"
    )
    def test_duplicate_webhook_does_not_enqueue_second_task(self, delay):
        payload = self._payload("pipeline-duplicate-mid")

        with self.captureOnCommitCallbacks(execute=True):
            first = self._post(payload)
        with self.captureOnCommitCallbacks(execute=True):
            second = self._post(payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(delay.call_count, 1)

    @override_settings(INSTAGRAM_AUTO_REPLY_ENABLED=False)
    @patch(
        "apps.instagram_integration.tasks."
        "process_instagram_inbound_message.delay"
    )
    def test_auto_reply_off_persists_but_does_not_enqueue(self, delay):
        with self.captureOnCommitCallbacks(execute=True):
            response = self._post(self._payload("pipeline-disabled-mid"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            InstagramInboundMessage.objects.filter(
                provider_message_id="pipeline-disabled-mid"
            ).exists()
        )
        delay.assert_not_called()

    @patch(
        "apps.instagram_integration.tasks."
        "process_instagram_inbound_message.delay"
    )
    def test_invalid_signature_never_enqueues(self, delay):
        body = json.dumps(
            self._payload("pipeline-invalid-signature"),
            separators=(",", ":"),
        ).encode("utf-8")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self._url(),
                data=body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256="sha256=bad",
            )

        self.assertEqual(response.status_code, 403)
        delay.assert_not_called()


@override_settings(**PIPELINE_SETTINGS)
class InstagramCeleryTaskTests(TestCase):
    @patch(
        "apps.instagram_integration.tasks."
        "process_and_dispatch_lumi_reply"
    )
    def test_task_runs_full_lumi_send_orchestration(self, orchestrator):
        user = CustomUser.objects.create_user(
            mobile_number="09125555002",
            name="Task",
            family="Manager",
            password="test-password",
        )
        manager = SalonManager.objects.create(
            user=user,
            is_active=True,
        )
        salon = Salon.objects.create(
            salon_name="Task Salon",
            salon_manager=manager,
            is_active=True,
        )
        connection = InstagramAccountConnection(
            salon=salon,
            instagram_account_id="ig-task-business",
        )
        connection.mark_connected()
        connection.save()

        inbound = InstagramInboundMessage.objects.create(
            connection=connection,
            provider_message_id="task-mid",
            sender_igsid="task-customer",
            recipient_instagram_account_id="ig-task-business",
            message_text="سلام",
        )

        result = Mock()
        result.status = "sent"
        orchestrator.return_value = result

        output = process_instagram_inbound_message.run(inbound.pk)

        orchestrator.assert_called_once_with(inbound.pk)
        self.assertEqual(output, "sent")

    @patch(
        "apps.instagram_integration.tasks."
        "process_and_dispatch_lumi_reply"
    )
    def test_missing_inbound_task_is_safe_noop(self, orchestrator):
        output = process_instagram_inbound_message.run(99999999)

        orchestrator.assert_not_called()
        self.assertEqual(output, "missing")
