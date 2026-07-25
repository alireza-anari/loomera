from __future__ import annotations

import os

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.core.management.base import CommandError

from apps.accounts.models import CustomUser
from apps.salons.models import Salon
from apps.main.management.commands.seed_local_demo_data import (
    Command as LocalSeedCommand,
    DEFAULT_PASSWORD,
    MOBILE_PREFIX,
    SEED_TAG,
)

STAGING_SEED_PASSWORD_ENV = "LOOMERA_STAGING_SEED_PASSWORD"
EXPECTED_EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"


class Command(LocalSeedCommand):
    help = (
        "Create the deterministic five-salon synthetic acceptance dataset "
        "on the Loomera staging environment."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help=(
                "Remove only previously created synthetic seed data before "
                "building the staging acceptance dataset."
            ),
        )
        parser.add_argument(
            "--confirm-staging",
            action="store_true",
            help=(
                "Explicitly confirm that this command is being run against "
                "the isolated Loomera staging environment."
            ),
        )
        parser.add_argument(
            "--days",
            type=int,
            default=14,
            help="Number of upcoming schedule days. Default: 14.",
        )

    def handle(self, *args, **options):
        self._validate_staging_runtime(options)

        seed_password = os.environ.get(
            STAGING_SEED_PASSWORD_ENV,
            "",
        ).strip()

        self._validate_seed_password(seed_password)
        self.seed_password = seed_password

        days_count = max(
            3,
            min(int(options.get("days") or 14), 45),
        )

        with transaction.atomic():
            self._reset_seed_data()

            group = self._create_service_group()
            services = self._create_services(group)
            managers = self._create_managers(5)
            stylists = self._create_stylists()
            customers = self._create_customers()

            salons = self._create_salons(
                managers,
                services,
                beta_acceptance=True,
            )

            self._attach_team_members(
                salons,
                stylists,
                services,
            )
            self._create_opening_hours(salons)
            self._create_gallery(salons)
            self._create_beta_acceptance_supplementary_info(salons)

            self._create_schedules(
                salons,
                stylists,
                services,
                days_count,
            )
            self._create_staff_time_off(
                salons,
                stylists,
            )
            self._create_wallets(customers)

            orders_created = self._create_orders(
                salons,
                stylists,
                services,
                customers,
                include_unresolved_online=False,
            )

        self.stdout.write(
            self.style.SUCCESS("Loomera staging acceptance dataset is ready.")
        )
        self.stdout.write(f"Seed tag: {SEED_TAG}")
        self.stdout.write("Profile: staging-acceptance")
        self.stdout.write(f"Salons: {len(salons)}")
        self.stdout.write(f"Services: {len(services)}")
        self.stdout.write(f"Orders created/skipped: {orders_created}")
        self.stdout.write(
            "Seed password source: " f"{STAGING_SEED_PASSWORD_ENV} (value hidden)"
        )

    def _validate_staging_runtime(self, options):
        environment = (
            str(
                getattr(
                    settings,
                    "LOOMERA_ENVIRONMENT",
                    "local",
                )
                or "local"
            )
            .strip()
            .lower()
        )

        if environment != "staging":
            raise CommandError(
                "This command is restricted to " "LOOMERA_ENVIRONMENT=staging."
            )

        if settings.DEBUG:
            raise CommandError("Staging acceptance seeding requires DEBUG=False.")

        if not options.get("confirm_staging"):
            raise CommandError(
                "Pass --confirm-staging to confirm the isolated " "staging target."
            )

        if not options.get("reset"):
            raise CommandError(
                "Staging acceptance seeding requires --reset so the "
                "dataset remains deterministic."
            )

        unsafe_settings = []

        if getattr(settings, "ONLINE_PAYMENT_ENABLED", False):
            unsafe_settings.append("ONLINE_PAYMENT_ENABLED")

        if getattr(settings, "MESSAGING_OUTBOUND_ENABLED", False):
            unsafe_settings.append("MESSAGING_OUTBOUND_ENABLED")

        if getattr(settings, "SMS_OTP_ENABLED", False):
            unsafe_settings.append("SMS_OTP_ENABLED")

        if (
            str(getattr(settings, "PAYMENT_MODE", "mock") or "mock").strip().lower()
            != "mock"
        ):
            unsafe_settings.append("PAYMENT_MODE")

        if (
            str(getattr(settings, "EMAIL_BACKEND", "") or "").strip()
            != EXPECTED_EMAIL_BACKEND
        ):
            unsafe_settings.append("EMAIL_BACKEND")

        if not getattr(
            settings,
            "LOOMERA_REQUIRE_OBJECT_STORAGE",
            False,
        ):
            unsafe_settings.append("LOOMERA_REQUIRE_OBJECT_STORAGE")

        if unsafe_settings:
            raise CommandError(
                "Unsafe staging configuration: " + ", ".join(sorted(unsafe_settings))
            )

        real_salons = Salon.objects.exclude(slug__startswith="local-seed-salon-")

        if real_salons.exists():
            raise CommandError(
                "Non-seed salons already exist. Staging acceptance "
                "seeding is blocked to protect existing data."
            )

        privileged_seed_users = CustomUser.objects.filter(
            mobile_number__startswith=MOBILE_PREFIX
        ).filter(Q(is_superuser=True) | Q(is_admin=True))

        if privileged_seed_users.exists():
            raise CommandError(
                "A privileged account uses the reserved seed mobile "
                "namespace. Seeding was blocked."
            )

    def _validate_seed_password(self, password):
        if not password:
            raise CommandError(f"{STAGING_SEED_PASSWORD_ENV} is not configured.")

        if len(password) < 16:
            raise CommandError(
                f"{STAGING_SEED_PASSWORD_ENV} must contain at least " "16 characters."
            )

        if password == DEFAULT_PASSWORD:
            raise CommandError(
                "The Local Seed default password cannot be used on staging."
            )
