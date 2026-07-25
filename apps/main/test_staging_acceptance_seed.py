from __future__ import annotations

import os
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.accounts.models import CustomUser
from apps.dashboards.beta_readiness import (
    serialize_beta_salon_readiness,
    with_beta_readiness_annotations,
)
from apps.main.management.commands.seed_staging_acceptance_data import (
    STAGING_SEED_PASSWORD_ENV,
)
from apps.payments.models import Payment
from apps.salons.models import Salon

TEST_SEED_PASSWORD = "Staging-Seed-Test-2026!"


class StagingAcceptanceSeedTests(TestCase):
    def _safe_staging_settings(self, media_root):
        return self.settings(
            DEBUG=False,
            LOOMERA_ENVIRONMENT="staging",
            ONLINE_PAYMENT_ENABLED=False,
            MESSAGING_OUTBOUND_ENABLED=False,
            SMS_OTP_ENABLED=False,
            PAYMENT_MODE="mock",
            EMAIL_BACKEND=("django.core.mail.backends.dummy.EmailBackend"),
            LOOMERA_REQUIRE_OBJECT_STORAGE=True,
            MEDIA_ROOT=media_root,
            PASSWORD_HASHERS=[
                "django.contrib.auth.hashers.MD5PasswordHasher",
            ],
            STORAGES={
                "default": {
                    "BACKEND": ("django.core.files.storage.FileSystemStorage"),
                },
                "staticfiles": {
                    "BACKEND": (
                        "django.contrib.staticfiles.storage." "StaticFilesStorage"
                    ),
                },
            },
        )

    def test_command_is_blocked_outside_staging(self):
        with self.settings(
            DEBUG=False,
            LOOMERA_ENVIRONMENT="production",
        ):
            with patch.dict(
                os.environ,
                {
                    STAGING_SEED_PASSWORD_ENV: TEST_SEED_PASSWORD,
                },
            ):
                with self.assertRaises(CommandError):
                    call_command(
                        "seed_staging_acceptance_data",
                        reset=True,
                        confirm_staging=True,
                        stdout=StringIO(),
                    )

    def test_command_requires_explicit_confirmation(self):
        with TemporaryDirectory() as media_root:
            with self._safe_staging_settings(media_root):
                with patch.dict(
                    os.environ,
                    {
                        STAGING_SEED_PASSWORD_ENV: TEST_SEED_PASSWORD,
                    },
                ):
                    with self.assertRaises(CommandError):
                        call_command(
                            "seed_staging_acceptance_data",
                            reset=True,
                            stdout=StringIO(),
                        )

    def test_command_preserves_admin_and_creates_five_ready_salons(
        self,
    ):
        with TemporaryDirectory() as media_root:
            with self._safe_staging_settings(media_root):
                admin = CustomUser.objects.create_superuser(
                    mobile_number="09120000001",
                    email="admin@example.test",
                    name="مدیر",
                    family="استیجینگ",
                    password="Admin-Test-Only-2026!",
                )

                output = StringIO()

                with patch.dict(
                    os.environ,
                    {
                        STAGING_SEED_PASSWORD_ENV: TEST_SEED_PASSWORD,
                    },
                ):
                    call_command(
                        "seed_staging_acceptance_data",
                        reset=True,
                        confirm_staging=True,
                        days=7,
                        stdout=output,
                    )

                self.assertTrue(
                    CustomUser.objects.filter(
                        pk=admin.pk,
                        is_superuser=True,
                    ).exists()
                )

                salons = list(
                    with_beta_readiness_annotations(
                        Salon.objects.filter(
                            slug__startswith="local-seed-salon-"
                        ).order_by("pk")
                    )
                )

                self.assertEqual(len(salons), 5)

                for salon in salons:
                    readiness = serialize_beta_salon_readiness(salon)
                    self.assertTrue(readiness["has_bookable_path"])
                    self.assertTrue(readiness["beta_ready"])

                self.assertFalse(
                    Payment.objects.filter(
                        state=Payment.State.PENDING,
                    ).exists()
                )

                self.assertNotIn(
                    TEST_SEED_PASSWORD,
                    output.getvalue(),
                )
