from __future__ import annotations

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from apps.salons.models import Salon

LOCAL_BETA_ACCEPTANCE_SALON_SLUGS = (
    "local-seed-salon-1",
    "local-seed-salon-2",
    "local-seed-salon-3",
    "local-seed-salon-4",
    "local-seed-salon-5",
)


class Command(BaseCommand):
    help = (
        "Run the final non-destructive Local Beta Acceptance "
        "check for Loomera's five synthetic salons."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--keepdb",
            action="store_true",
            help=(
                "Preserve the Django test database while running " "release readiness."
            ),
        )
        parser.add_argument(
            "--failfast",
            action="store_true",
            help=("Stop release readiness after the first failed " "stage or test."),
        )
        parser.add_argument(
            "--verbosity-inner",
            type=int,
            choices=(0, 1, 2, 3),
            default=1,
            help=("Verbosity passed to nested readiness commands " "and test runners."),
        )

    def _validate_local_runtime_policy(self):
        problems = []

        if not settings.DEBUG:
            problems.append("DEBUG must be True.")

        if getattr(
            settings,
            "ONLINE_PAYMENT_ENABLED",
            False,
        ):
            problems.append("ONLINE_PAYMENT_ENABLED must be False.")

        if getattr(
            settings,
            "MESSAGING_OUTBOUND_ENABLED",
            False,
        ):
            problems.append("MESSAGING_OUTBOUND_ENABLED must be False.")

        expected_email_backend = "django.core.mail.backends." "dummy.EmailBackend"

        if settings.EMAIL_BACKEND != expected_email_backend:
            problems.append("EMAIL_BACKEND must use Django's dummy backend.")

        if problems:
            raise CommandError(
                "Unsafe Local Beta Acceptance runtime policy: " + " ".join(problems)
            )

    def _get_active_seed_slugs(self):
        return tuple(
            Salon.objects.filter(
                slug__in=(LOCAL_BETA_ACCEPTANCE_SALON_SLUGS),
                is_active=True,
            )
            .order_by("slug")
            .values_list(
                "slug",
                flat=True,
            )
        )

    def _validate_five_seed_salons_exist(self):
        actual_slugs = self._get_active_seed_slugs()
        expected_slugs = tuple(sorted(LOCAL_BETA_ACCEPTANCE_SALON_SLUGS))

        if actual_slugs == expected_slugs:
            return

        missing_slugs = sorted(set(expected_slugs) - set(actual_slugs))
        unexpected_slugs = sorted(set(actual_slugs) - set(expected_slugs))

        details = []

        if missing_slugs:
            details.append("missing=" + ",".join(missing_slugs))

        if unexpected_slugs:
            details.append("unexpected=" + ",".join(unexpected_slugs))

        raise CommandError(
            "The deterministic five-salon acceptance dataset "
            "is not ready" + (": " + " ".join(details) if details else ".")
        )

    def _run_five_salon_readiness(
        self,
        *,
        verbosity_inner,
    ):
        call_command(
            "beta_salon_readiness_check",
            slugs=list(LOCAL_BETA_ACCEPTANCE_SALON_SLUGS),
            active_only=True,
            strict=True,
            verbosity=verbosity_inner,
            stdout=self.stdout,
            stderr=self.stderr,
        )

    def _run_release_readiness(
        self,
        *,
        keepdb,
        failfast,
        verbosity_inner,
    ):
        call_command(
            "release_readiness_check",
            keepdb=keepdb,
            failfast=failfast,
            verbosity_inner=verbosity_inner,
            stdout=self.stdout,
            stderr=self.stderr,
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.HTTP_INFO("Loomera Local Beta Acceptance started.")
        )

        self.stdout.write(self.style.HTTP_INFO("[RUN ] local-runtime-policy"))
        self._validate_local_runtime_policy()
        self.stdout.write(self.style.SUCCESS("[PASS] local-runtime-policy"))

        self.stdout.write(self.style.HTTP_INFO("[RUN ] five-salon-dataset"))
        self._validate_five_seed_salons_exist()
        self.stdout.write(self.style.SUCCESS("[PASS] five-salon-dataset"))

        self.stdout.write(self.style.HTTP_INFO("[RUN ] five-salon-readiness"))
        self._run_five_salon_readiness(
            verbosity_inner=(options["verbosity_inner"]),
        )
        self.stdout.write(self.style.SUCCESS("[PASS] five-salon-readiness"))

        self.stdout.write(self.style.HTTP_INFO("[RUN ] release-readiness"))
        self._run_release_readiness(
            keepdb=options["keepdb"],
            failfast=options["failfast"],
            verbosity_inner=(options["verbosity_inner"]),
        )
        self.stdout.write(self.style.SUCCESS("[PASS] release-readiness"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Summary: 4 passed, 0 failed, 0 skipped."))
        self.stdout.write(self.style.SUCCESS("Loomera Local Beta Acceptance: PASSED"))
