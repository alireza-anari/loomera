from datetime import timedelta
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import CustomUser, SalonManager
from apps.salons.models import Salon

from .models import InstagramAccountConnection


FERNET_TEST_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="

READY_SETTINGS = {
    "INSTAGRAM_ENABLED": True,
    "INSTAGRAM_MESSAGING_ENABLED": True,
    "INSTAGRAM_SEND_ENABLED": True,
    "INSTAGRAM_AUTO_REPLY_ENABLED": True,
    "INSTAGRAM_APP_ID": "123456",
    "INSTAGRAM_APP_SECRET": "secret",
    "INSTAGRAM_REDIRECT_URI": "https://staging.example.test/instagram/oauth/callback/",
    "INSTAGRAM_WEBHOOK_VERIFY_TOKEN": "verify",
    "INSTAGRAM_TOKEN_ENCRYPTION_KEY": FERNET_TEST_KEY,
    "INSTAGRAM_LOGIN_SCOPES": [
        "instagram_business_basic",
        "instagram_business_manage_messages",
    ],
    "INSTAGRAM_REQUEST_TIMEOUT": 10,
    "INSTAGRAM_WEBHOOK_MAX_BYTES": 262144,
    "INSTAGRAM_OAUTH_STATE_TTL_SECONDS": 600,
    "INSTAGRAM_GRAPH_BASE_URL": "https://graph.instagram.com",
    "INSTAGRAM_GRAPH_API_VERSION": "v24.0",
    "LOOMERA_ENABLE_CELERY": True,
    "CELERY_TASK_ALWAYS_EAGER": False,
    "CELERY_BROKER_URL": "redis://redis.example.test:6379/0",
}


class InstagramReadinessCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = CustomUser.objects.create_user(
            mobile_number="09126666001",
            name="Ready",
            family="Manager",
            password="test-password",
        )
        user.is_active = True
        user.save(update_fields=["is_active"])

        manager = SalonManager.objects.create(
            user=user,
            is_active=True,
        )
        cls.salon = Salon.objects.create(
            salon_name="Ready Salon",
            salon_manager=manager,
            is_active=True,
        )

    def _connection(self):
        connection = InstagramAccountConnection(
            salon=self.salon,
            instagram_account_id="ig-ready-123",
            username="ready_salon",
            granted_scopes=[
                "instagram_business_basic",
                "instagram_business_manage_messages",
            ],
            token_expires_at=timezone.now() + timedelta(days=30),
        )
        connection.set_access_token("ready-secret-token")
        connection.mark_connected()
        connection.save()
        return connection

    @override_settings(
        INSTAGRAM_ENABLED=False,
        INSTAGRAM_MESSAGING_ENABLED=False,
        INSTAGRAM_SEND_ENABLED=False,
        INSTAGRAM_AUTO_REPLY_ENABLED=False,
    )
    def test_non_strict_offline_check_is_safe(self):
        stdout = StringIO()

        call_command("instagram_qa_check", stdout=stdout)

        self.assertIn("Instagram master flag is OFF", stdout.getvalue())

    @override_settings(**READY_SETTINGS)
    def test_strict_requires_connected_account(self):
        with self.assertRaises(CommandError):
            call_command(
                "instagram_qa_check",
                "--strict",
                stdout=StringIO(),
                stderr=StringIO(),
            )

    @override_settings(**READY_SETTINGS)
    def test_strict_passes_with_valid_connected_account(self):
        self._connection()
        stdout = StringIO()

        call_command(
            "instagram_qa_check",
            "--strict",
            stdout=stdout,
        )

        self.assertIn(
            "INSTAGRAM READY FOR LIVE SMOKE",
            stdout.getvalue(),
        )

    @override_settings(**READY_SETTINGS)
    def test_expired_token_blocks_strict_readiness(self):
        connection = self._connection()
        connection.token_expires_at = timezone.now() - timedelta(minutes=1)
        connection.save(update_fields=["token_expires_at"])

        with self.assertRaises(CommandError):
            call_command(
                "instagram_qa_check",
                "--strict",
                stdout=StringIO(),
                stderr=StringIO(),
            )

    @override_settings(**READY_SETTINGS)
    @patch(
        "apps.instagram_integration.management.commands."
        "instagram_qa_check.requests.get"
    )
    def test_live_check_verifies_same_meta_account(self, get):
        connection = self._connection()

        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "id": "ig-ready-123",
            "username": "ready_salon",
        }
        get.return_value = response

        stdout = StringIO()
        call_command(
            "instagram_qa_check",
            "--strict",
            "--live",
            "--connection-id",
            str(connection.pk),
            stdout=stdout,
        )

        args, kwargs = get.call_args
        self.assertEqual(
            args[0],
            "https://graph.instagram.com/v24.0/me",
        )
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer ready-secret-token",
        )
        self.assertIn("verified id=ig-ready-123", stdout.getvalue())

    @override_settings(**READY_SETTINGS)
    @patch(
        "apps.instagram_integration.management.commands."
        "instagram_qa_check.requests.get"
    )
    def test_live_check_rejects_identity_mismatch(self, get):
        connection = self._connection()

        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "id": "different-account",
            "username": "wrong",
        }
        get.return_value = response

        with self.assertRaises(CommandError):
            call_command(
                "instagram_qa_check",
                "--strict",
                "--live",
                "--connection-id",
                str(connection.pk),
                stdout=StringIO(),
                stderr=StringIO(),
            )
