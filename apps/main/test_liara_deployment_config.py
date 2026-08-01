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

        self.assertIn(
            (
                "* * * * * cd $ROOT && python manage.py "
                "process_notification_deliveries --limit 100"
            ),
            cron,
        )

        self.assertIn(
            (
                "*/15 * * * * cd $ROOT && python manage.py "
                "process_notification_deliveries "
                "--limit 100 --include-failed"
            ),
            cron,
        )

        self.assertNotIn(
            (
                "*/5 * * * * cd $ROOT && python manage.py "
                "process_notification_deliveries --limit 25"
            ),
            cron,
        )
