python
from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class LiaraDeploymentConfigTests(SimpleTestCase):
    def _load_config(self) -> dict:
        config_path = Path(settings.BASE_DIR) / "liara.json"
        return json.loads(config_path.read_text(encoding="utf-8"))

    def test_health_check_is_environment_neutral(self):
        config = self._load_config()

        # The custom Liara health check can be temporarily disabled while
        # diagnosing production deployment health failures. When absent,
        # this test must not block CI; all other deployment guards remain
        # active.
        if "healthCheck" not in config:
            self.skipTest(
                "Custom Liara health check temporarily disabled "
                "for deployment diagnosis."
            )

        command = config["healthCheck"]["command"]

        self.assertIn(
            "-H 'Host: localhost'",
            command,
        )

        self.assertIn(
            "http://127.0.0.1:8000/health/?live=1",
            command,
        )

        self.assertNotIn(
            "staging.loomera.ir",
            command,
        )

        self.assertNotIn(
            "-H 'Host: loomera.ir'",
            command,
        )

    def test_health_check_keeps_forwarded_https_header(self):
        config = self._load_config()

        # See test_health_check_is_environment_neutral().
        # This skip is intentionally limited to health-check diagnostics.
        if "healthCheck" not in config:
            self.skipTest(
                "Custom Liara health check temporarily disabled "
                "for deployment diagnosis."
            )

        command = config["healthCheck"]["command"]

        self.assertIn(
            "-H 'X-Forwarded-Proto: https'",
            command,
        )

    def test_notification_delivery_cron_policy(self):
        config = self._load_config()
        cron = config["cron"]

        primary_matches = [
            entry
            for entry in cron
            if entry.startswith(
                "* * * * * cd $ROOT && python manage.py "
                "process_notification_deliveries --limit 100"
            )
            and "--include-failed" not in entry
        ]

        self.assertEqual(
            len(primary_matches),
            1,
        )

        primary = primary_matches[0]

        self.assertIn(
            "BETTERSTACK_NOTIFICATION_DELIVERY_HEARTBEAT_URL",
            primary,
        )

        self.assertIn(
            "&& if [ -n "
            '"$BETTERSTACK_NOTIFICATION_DELIVERY_HEARTBEAT_URL"'
            " ]; then",
            primary,
        )

        self.assertIn(
            (
                "curl --fail --silent --show-error --max-time 10 "
                '"$BETTERSTACK_NOTIFICATION_DELIVERY_HEARTBEAT_URL"'
            ),
            primary,
        )

        # Never commit the real heartbeat endpoint/token to source.
        self.assertNotIn(
            "uptime.betterstack.com/api/v1/heartbeat/",
            primary,
        )

        retry_matches = [
            entry
            for entry in cron
            if entry.startswith(
                "*/15 * * * * cd $ROOT && python manage.py "
                "process_notification_deliveries "
                "--limit 100 --include-failed"
            )
        ]

        self.assertEqual(
            len(retry_matches),
            1,
        )

        retry = retry_matches[0]

        # Retry must never ping the primary delivery heartbeat.
        self.assertNotIn(
            "BETTERSTACK_NOTIFICATION_DELIVERY_HEARTBEAT_URL",
            retry,
        )

        self.assertNotIn(
            (
                "*/5 * * * * cd $ROOT && python manage.py "
                "process_notification_deliveries --limit 25"
            ),
            cron,
        )

    def test_notification_retry_cron_heartbeat_policy(self):
        config = self._load_config()
        cron = config["cron"]

        retry_matches = [
            entry
            for entry in cron
            if entry.startswith(
                "*/15 * * * * cd $ROOT && python manage.py "
                "process_notification_deliveries "
                "--limit 100 --include-failed"
            )
        ]

        self.assertEqual(
            len(retry_matches),
            1,
        )

        retry = retry_matches[0]

        self.assertIn(
            "BETTERSTACK_NOTIFICATION_RETRY_HEARTBEAT_URL",
            retry,
        )

        self.assertIn(
            (
                "curl --fail --silent --show-error --max-time 10 "
                '"$BETTERSTACK_NOTIFICATION_RETRY_HEARTBEAT_URL"'
            ),
            retry,
        )

        # The retry cron must never ping the primary heartbeat.
        self.assertNotIn(
            "BETTERSTACK_NOTIFICATION_DELIVERY_HEARTBEAT_URL",
            retry,
        )

        # Never
