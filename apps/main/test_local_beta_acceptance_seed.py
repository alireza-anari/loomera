from __future__ import annotations

from io import StringIO
from tempfile import TemporaryDirectory

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.dashboards.beta_readiness import (
    serialize_beta_salon_readiness,
    with_beta_readiness_annotations,
)
from apps.main.management.commands.seed_local_demo_data import SEED_TAG
from apps.payments.models import Payment
from apps.salons.models import Salon
from apps.orders.models import Order
from apps.payments.models import LedgerEntry, StaffEarning
from apps.payments.finance import finalize_order_financials
from apps.payments.models import LedgerEntry, StaffEarning
from apps.dashboards.views import (
    _get_required_onboarding_view_name,
)


class LocalBetaAcceptanceSeedTests(TestCase):
    def test_beta_acceptance_profile_requires_reset(self):
        with self.assertRaises(CommandError):
            call_command(
                "seed_local_demo_data",
                beta_acceptance=True,
                stdout=StringIO(),
            )

    def test_beta_acceptance_creates_five_ready_salons(self):
        with TemporaryDirectory() as media_root:
            with self.settings(
                DEBUG=True,
                MEDIA_ROOT=media_root,
                PASSWORD_HASHERS=[
                    "django.contrib.auth.hashers.MD5PasswordHasher",
                ],
            ):
                call_command(
                    "seed_local_demo_data",
                    reset=True,
                    beta_acceptance=True,
                    days=7,
                    stdout=StringIO(),
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

                    self.assertIsNotNone(salon.location)
                    self.assertTrue(salon.gallery_images.exists())
                    self.assertTrue(readiness["has_bookable_path"])
                    self.assertTrue(readiness["beta_ready"])
                    self.assertEqual(
                        readiness["critical_missing_keys"],
                        [],
                    )
                    self.assertIsNotNone(salon.neighborhood_id)
                    self.assertGreaterEqual(
                        len((salon.description or "").strip()),
                        200,
                    )
                    self.assertTrue(
                        salon.supplementary_info.filter(is_active=True).exists()
                    )

                    self.assertIsNone(
                        _get_required_onboarding_view_name(salon.salon_manager.user)
                    )

    def test_beta_acceptance_does_not_create_pending_online_payment(self):
        with TemporaryDirectory() as media_root:
            with self.settings(
                DEBUG=True,
                MEDIA_ROOT=media_root,
                PASSWORD_HASHERS=[
                    "django.contrib.auth.hashers.MD5PasswordHasher",
                ],
            ):
                call_command(
                    "seed_local_demo_data",
                    reset=True,
                    beta_acceptance=True,
                    days=7,
                    stdout=StringIO(),
                )

                pending_seed_payments = Payment.objects.filter(
                    state=Payment.State.PENDING,
                    meta__seed_tag=SEED_TAG,
                )

                self.assertFalse(pending_seed_payments.exists())

    def test_beta_acceptance_profile_is_repeatable(self):
        with TemporaryDirectory() as media_root:
            with self.settings(
                DEBUG=True,
                MEDIA_ROOT=media_root,
                PASSWORD_HASHERS=[
                    "django.contrib.auth.hashers.MD5PasswordHasher",
                ],
            ):
                for _iteration in range(2):
                    call_command(
                        "seed_local_demo_data",
                        reset=True,
                        beta_acceptance=True,
                        days=7,
                        stdout=StringIO(),
                    )

                self.assertEqual(
                    Salon.objects.filter(slug__startswith="local-seed-salon-").count(),
                    5,
                )

    def test_reset_removes_previous_seed_financial_artifacts(self):
        with TemporaryDirectory() as media_root:
            with self.settings(
                DEBUG=True,
                MEDIA_ROOT=media_root,
                PASSWORD_HASHERS=[
                    "django.contrib.auth.hashers.MD5PasswordHasher",
                ],
            ):
                # First create the regular demo dataset.
                call_command(
                    "seed_local_demo_data",
                    reset=True,
                    days=7,
                    stdout=StringIO(),
                )

                completed_order = Order.objects.get(
                    description=(f"{SEED_TAG}:order:completed-manual-payment")
                )

                # The seed command marks this appointment as completed, but
                # financial ledger rows are created only when the finance
                # finalization boundary is executed explicitly.
                snapshots = finalize_order_financials(
                    completed_order,
                    require_all_completed=True,
                )

                self.assertTrue(snapshots)

                previous_order_id = completed_order.pk
                previous_ledger_ids = list(
                    LedgerEntry.objects.filter(order_id=previous_order_id).values_list(
                        "pk", flat=True
                    )
                )
                previous_earning_ids = list(
                    StaffEarning.objects.filter(
                        order_detail__order_id=previous_order_id
                    ).values_list("pk", flat=True)
                )

                # Confirm that the test actually reproduces the protected
                # financial dependency which previously broke --reset.
                self.assertTrue(previous_ledger_ids)
                self.assertTrue(previous_earning_ids)

                # This previously raised ProtectedError.
                call_command(
                    "seed_local_demo_data",
                    reset=True,
                    beta_acceptance=True,
                    days=7,
                    stdout=StringIO(),
                )

                self.assertFalse(Order.objects.filter(pk=previous_order_id).exists())
                self.assertFalse(
                    LedgerEntry.objects.filter(pk__in=previous_ledger_ids).exists()
                )
                self.assertFalse(
                    StaffEarning.objects.filter(pk__in=previous_earning_ids).exists()
                )

                self.assertEqual(
                    Salon.objects.filter(slug__startswith="local-seed-salon-").count(),
                    5,
                )
