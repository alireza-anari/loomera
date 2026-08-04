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
        command = config["healthCheck"]["command"]

        self.assertIn(
            "-H 'Host: localhost'",
            command,
        )
        self.assertIn(
            "http://localhost:8000/health/?live=1",
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

        # Never commit a real Better Stack heartbeat URL.
        self.assertNotIn(
            "uptime.betterstack.com/api/v1/heartbeat/",
            retry,
        )

    def test_appointment_notifications_cron_heartbeat_policy(self):
        config = self._load_config()
        cron = config["cron"]

        matches = [
            entry
            for entry in cron
            if entry.startswith(
                "*/5 * * * * cd $ROOT && python manage.py "
                "dispatch_appointment_notifications --limit 25"
            )
        ]

        self.assertEqual(
            len(matches),
            1,
        )

        command = matches[0]

        self.assertIn(
            "BETTERSTACK_APPOINTMENT_NOTIFICATIONS_HEARTBEAT_URL",
            command,
        )

        self.assertIn(
            (
                "curl --fail --silent --show-error --max-time 10 "
                '"$BETTERSTACK_APPOINTMENT_NOTIFICATIONS_HEARTBEAT_URL"'
            ),
            command,
        )

        # This cron must never ping notification delivery/retry heartbeats.
        self.assertNotIn(
            "BETTERSTACK_NOTIFICATION_DELIVERY_HEARTBEAT_URL",
            command,
        )

        self.assertNotIn(
            "BETTERSTACK_NOTIFICATION_RETRY_HEARTBEAT_URL",
            command,
        )

        # Never commit the real Better Stack heartbeat URL.
        self.assertNotIn(
            "uptime.betterstack.com/api/v1/heartbeat/",
            command,
        )

    def test_no_show_confirmation_cron_heartbeat_policy(self):
        config = self._load_config()
        cron = config["cron"]

        matches = [
            entry
            for entry in cron
            if entry.startswith(
                "*/5 * * * * cd $ROOT && python manage.py "
                "confirm_no_show_after_window --limit 25"
            )
        ]

        self.assertEqual(
            len(matches),
            1,
        )

        command = matches[0]

        self.assertIn(
            "BETTERSTACK_NO_SHOW_CONFIRMATION_HEARTBEAT_URL",
            command,
        )

        self.assertIn(
            (
                "curl --fail --silent --show-error --max-time 10 "
                '"$BETTERSTACK_NO_SHOW_CONFIRMATION_HEARTBEAT_URL"'
            ),
            command,
        )

        # This cron must not ping another operational heartbeat.
        self.assertNotIn(
            "BETTERSTACK_NOTIFICATION_DELIVERY_HEARTBEAT_URL",
            command,
        )

        self.assertNotIn(
            "BETTERSTACK_NOTIFICATION_RETRY_HEARTBEAT_URL",
            command,
        )

        self.assertNotIn(
            "BETTERSTACK_APPOINTMENT_NOTIFICATIONS_HEARTBEAT_URL",
            command,
        )

        # Never commit the real Better Stack heartbeat endpoint/token.
        self.assertNotIn(
            "uptime.betterstack.com/api/v1/heartbeat/",
            command,
        )

    def test_ci_workflow_checks_staging_and_main(self):
        workflow_path = Path(settings.BASE_DIR) / ".github" / "workflows" / "ci.yml"

        content = workflow_path.read_text(encoding="utf-8")

        self.assertIn(
            "pull_request:",
            content,
        )

        self.assertIn(
            "- staging",
            content,
        )

        self.assertIn(
            "- main",
            content,
        )

        self.assertIn(
            "python manage.py check",
            content,
        )

        self.assertIn(
            "makemigrations --check --dry-run",
            content,
        )

        self.assertIn(
            "DATABASE_URL: sqlite:///ci.sqlite3",
            content,
        )

        self.assertNotIn(
            "liara deploy",
            content,
        )

    def test_production_workflow_is_manual_and_guarded(self):
        workflow_path = (
            Path(settings.BASE_DIR) / ".github" / "workflows" / "liara-production.yml"
        )

        content = workflow_path.read_text(encoding="utf-8")

        self.assertIn(
            "workflow_dispatch:",
            content,
        )

        self.assertIn(
            "github.ref == 'refs/heads/main'",
            content,
        )

        self.assertIn(
            "inputs.confirm == 'DEPLOY'",
            content,
        )

        self.assertIn(
            "environment: production",
            content,
        )

        self.assertIn(
            "secrets.LIARA_API_TOKEN",
            content,
        )

        self.assertIn(
            "vars.LIARA_APP_NAME",
            content,
        )

        self.assertIn(
            'LIARA_APP_NAME" = "loomera-staging"',
            content,
        )

        self.assertIn(
            '--app="$LIARA_APP_NAME"',
            content,
        )

        self.assertNotIn(
            "\n  push:",
            content,
        )

    def test_staging_workflow_uses_staging_environment(self):
        workflow_path = (
            Path(settings.BASE_DIR) / ".github" / "workflows" / "liara-staging.yml"
        )

        content = workflow_path.read_text(encoding="utf-8")

        self.assertIn(
            "workflow_dispatch:",
            content,
        )

        self.assertIn(
            "github.ref == 'refs/heads/staging'",
            content,
        )

        self.assertIn(
            "environment: staging",
            content,
        )

        self.assertIn(
            "secrets.LIARA_API_TOKEN",
            content,
        )

        self.assertIn(
            "vars.LIARA_APP_NAME",
            content,
        )

        self.assertIn(
            'LIARA_APP_NAME" != "loomera-staging"',
            content,
        )

        self.assertIn(
            '--app="$LIARA_APP_NAME"',
            content,
        )

        self.assertNotIn(
            '--app="loomera-staging"',
            content,
        )

        self.assertNotIn(
            "\n  push:",
            content,
        )
