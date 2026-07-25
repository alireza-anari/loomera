from __future__ import annotations

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.test.runner import DiscoverRunner

from apps.main.regression_suites import (
    REGRESSION_SUITES,
    get_regression_suite,
)
from django.test import override_settings


class Command(BaseCommand):
    help = (
        "Run one curated Loomera regression suite through " "Django's DiscoverRunner."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "suite",
            nargs="?",
            choices=tuple(REGRESSION_SUITES),
            help=(
                "Suite to run: security, payments, booking, "
                "messaging, or release-check."
            ),
        )
        parser.add_argument(
            "--list",
            action="store_true",
            dest="list_suites",
            help="List suite names and their test labels.",
        )
        parser.add_argument(
            "--keepdb",
            action="store_true",
            help="Preserve the test database between runs.",
        )
        parser.add_argument(
            "--failfast",
            action="store_true",
            help="Stop after the first test failure or error.",
        )
        parser.add_argument(
            "--verbosity-inner",
            type=int,
            choices=(0, 1, 2, 3),
            default=1,
            help="Verbosity passed to Django's test runner.",
        )

    def _list_suites(self):
        self.stdout.write("Loomera regression suites:")

        for name, labels in REGRESSION_SUITES.items():
            self.stdout.write(f"- {name}: {len(labels)} module(s)")

            for label in labels:
                self.stdout.write(f"    {label}")

    def handle(self, *args, **options):
        if options["list_suites"]:
            self._list_suites()
            return

        suite_name = options["suite"]

        if not suite_name:
            raise CommandError("Choose a suite or use --list.")

        labels = get_regression_suite(suite_name)

        self.stdout.write(
            self.style.HTTP_INFO(
                f"Running Loomera regression suite "
                f"{suite_name!r} with {len(labels)} "
                "test module(s)."
            )
        )

        runner = DiscoverRunner(
            verbosity=options["verbosity_inner"],
            interactive=False,
            keepdb=options["keepdb"],
            failfast=options["failfast"],
        )
        with override_settings(SECURE_SSL_REDIRECT=False):
            failures = runner.run_tests(labels)

        if failures:
            self.stderr.write(
                self.style.ERROR(
                    f"Regression suite {suite_name!r} "
                    f"failed with {failures} failure(s)."
                )
            )
            raise SystemExit(1)

        self.stdout.write(
            self.style.SUCCESS(f"Regression suite {suite_name!r} passed.")
        )
