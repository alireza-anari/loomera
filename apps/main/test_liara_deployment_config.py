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
