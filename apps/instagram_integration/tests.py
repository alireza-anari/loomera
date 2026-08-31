from django.test import SimpleTestCase

from .checks import check_instagram_configuration


VALID = {
    "INSTAGRAM_ENABLED": True,
    "INSTAGRAM_MESSAGING_ENABLED": True,
    "INSTAGRAM_APP_ID": "123456789",
    "INSTAGRAM_APP_SECRET": "test-secret-never-real",
    "INSTAGRAM_REDIRECT_URI": "https://staging.example.test/instagram/oauth/callback/",
    "INSTAGRAM_WEBHOOK_VERIFY_TOKEN": "test-verify-token",
    "INSTAGRAM_TOKEN_ENCRYPTION_KEY": "test-key-not-used-by-milestone-1",
    "INSTAGRAM_LOGIN_SCOPES": [
        "instagram_business_basic",
        "instagram_business_manage_messages",
    ],
    "INSTAGRAM_REQUEST_TIMEOUT": 10,
    "INSTAGRAM_WEBHOOK_MAX_BYTES": 256 * 1024,
    "INSTAGRAM_OAUTH_STATE_TTL_SECONDS": 600,
}


class InstagramConfigurationCheckTests(SimpleTestCase):
    def _ids(self):
        return [error.id for error in check_instagram_configuration()]

    def test_disabled_requires_no_instagram_secrets(self):
        with self.settings(
            INSTAGRAM_ENABLED=False,
            INSTAGRAM_MESSAGING_ENABLED=False,
            INSTAGRAM_APP_ID="",
            INSTAGRAM_APP_SECRET="",
            INSTAGRAM_REDIRECT_URI="",
            INSTAGRAM_WEBHOOK_VERIFY_TOKEN="",
            INSTAGRAM_TOKEN_ENCRYPTION_KEY="",
        ):
            self.assertEqual(check_instagram_configuration(), [])

    def test_messaging_cannot_be_enabled_without_master_flag(self):
        with self.settings(
            INSTAGRAM_ENABLED=False,
            INSTAGRAM_MESSAGING_ENABLED=True,
        ):
            self.assertIn("instagram.E001", self._ids())

    def test_enabled_requires_release_configuration(self):
        with self.settings(
            INSTAGRAM_ENABLED=True,
            INSTAGRAM_MESSAGING_ENABLED=True,
            INSTAGRAM_APP_ID="",
            INSTAGRAM_APP_SECRET="",
            INSTAGRAM_REDIRECT_URI="",
            INSTAGRAM_WEBHOOK_VERIFY_TOKEN="",
            INSTAGRAM_TOKEN_ENCRYPTION_KEY="",
            INSTAGRAM_LOGIN_SCOPES=[
                "instagram_business_basic",
                "instagram_business_manage_messages",
            ],
            INSTAGRAM_REQUEST_TIMEOUT=10,
            INSTAGRAM_WEBHOOK_MAX_BYTES=256 * 1024,
            INSTAGRAM_OAUTH_STATE_TTL_SECONDS=600,
        ):
            self.assertGreaterEqual(self._ids().count("instagram.E002"), 5)

    def test_valid_release_configuration_passes(self):
        with self.settings(**VALID):
            self.assertEqual(check_instagram_configuration(), [])

    def test_deprecated_permission_names_are_rejected(self):
        config = dict(VALID)
        config["INSTAGRAM_LOGIN_SCOPES"] = [
            "instagram_business_basic",
            "instagram_business_manage_messages",
            "business_manage_messages",
        ]
        with self.settings(**config):
            self.assertIn("instagram.E004", self._ids())

    def test_messaging_scope_is_required_when_dm_enabled(self):
        config = dict(VALID)
        config["INSTAGRAM_LOGIN_SCOPES"] = ["instagram_business_basic"]
        with self.settings(**config):
            self.assertIn("instagram.E006", self._ids())

    def test_http_redirect_is_rejected_outside_debug_localhost(self):
        config = dict(VALID)
        config["DEBUG"] = False
        config["INSTAGRAM_REDIRECT_URI"] = (
            "http://staging.example.test/instagram/oauth/callback/"
        )
        with self.settings(**config):
            self.assertIn("instagram.E003", self._ids())

    def test_localhost_http_redirect_is_allowed_only_in_debug(self):
        config = dict(VALID)
        config["DEBUG"] = True
        config["INSTAGRAM_REDIRECT_URI"] = (
            "http://127.0.0.1:8000/instagram/oauth/callback/"
        )
        with self.settings(**config):
            self.assertEqual(check_instagram_configuration(), [])

    def test_auto_reply_requires_real_celery_worker_mode(self):
        config = dict(VALID)
        config.update(
            INSTAGRAM_SEND_ENABLED=True,
            INSTAGRAM_AUTO_REPLY_ENABLED=True,
            LOOMERA_ENABLE_CELERY=False,
            CELERY_TASK_ALWAYS_EAGER=True,
        )
        with self.settings(**config):
            self.assertIn("instagram.E012", self._ids())

    def test_auto_reply_requires_send_flag(self):
        config = dict(VALID)
        config.update(
            INSTAGRAM_SEND_ENABLED=False,
            INSTAGRAM_AUTO_REPLY_ENABLED=True,
        )
        with self.settings(**config):
            self.assertIn("instagram.E011", self._ids())

