from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from apps.dashboards.beta_readiness import (
    serialize_beta_salon_readiness,
    summarize_beta_salon_readiness,
    with_beta_readiness_annotations,
)
from apps.salons.models import Salon


class Command(BaseCommand):
    help = (
        "Inspect beta salon onboarding readiness without changing any data. "
        "The command is read-only and safe for Local readiness reviews."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--salon-id",
            action="append",
            dest="salon_ids",
            type=int,
            default=[],
            help=(
                "Inspect only this salon id. The option may be repeated "
                "for multiple beta salons."
            ),
        )
        parser.add_argument(
            "--slug",
            action="append",
            dest="slugs",
            default=[],
            help=(
                "Inspect only this salon slug. The option may be repeated "
                "for multiple beta salons."
            ),
        )
        parser.add_argument(
            "--active-only",
            action="store_true",
            help="Inspect only salons currently marked active.",
        )
        parser.add_argument(
            "--only-incomplete",
            action="store_true",
            help="Hide salons whose readiness checklist is fully complete.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Return machine-readable JSON output.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help=(
                "Exit with status 1 if any selected salon is incomplete "
                "or has no real bookable path."
            ),
        )

    @staticmethod
    def _normalize_slugs(values):
        return {
            str(value or "").strip() for value in values if str(value or "").strip()
        }

    def _build_queryset(self, *, salon_ids, slugs, active_only):
        queryset = with_beta_readiness_annotations(
            Salon.objects.select_related(
                "salon_manager",
                "salon_manager__user",
            )
        ).order_by("pk")

        selected_ids = {int(value) for value in salon_ids if int(value) > 0}
        selected_slugs = self._normalize_slugs(slugs)

        if selected_ids or selected_slugs:
            from django.db.models import Q

            scope = Q()
            if selected_ids:
                scope |= Q(pk__in=selected_ids)
            if selected_slugs:
                scope |= Q(slug__in=selected_slugs)
            queryset = queryset.filter(scope)

        if active_only:
            queryset = queryset.filter(is_active=True)

        salons = list(queryset)

        if selected_ids:
            found_ids = {salon.pk for salon in salons}
            missing_ids = sorted(selected_ids - found_ids)
            if missing_ids:
                raise CommandError(
                    "Unknown or out-of-scope salon id(s): "
                    + ", ".join(str(value) for value in missing_ids)
                )

        if selected_slugs:
            found_slugs = {salon.slug for salon in salons}
            missing_slugs = sorted(selected_slugs - found_slugs)
            if missing_slugs:
                raise CommandError(
                    "Unknown or out-of-scope salon slug(s): " + ", ".join(missing_slugs)
                )

        return salons

    @staticmethod
    def _serialize_salon(salon):
        return serialize_beta_salon_readiness(salon)

    @staticmethod
    def _build_summary(salons):
        return summarize_beta_salon_readiness(salons)

    def _write_text(self, *, salons, summary):
        self.stdout.write("Loomera Beta Salon Readiness")
        self.stdout.write("=" * 36)

        if not salons:
            self.stdout.write("No salons matched the selected scope.")
            return

        for salon in salons:
            status = (
                self.style.SUCCESS("READY")
                if salon["beta_ready"]
                else self.style.WARNING("INCOMPLETE")
            )

            self.stdout.write("")
            self.stdout.write(
                f"[{status}] "
                f"#{salon['salon_id']} "
                f"{salon['salon_name']} "
                f"({salon['slug']})"
            )
            self.stdout.write(
                "  readiness: "
                f"{salon['readiness_percent']}%"
                f" | bookable_path="
                f"{salon['has_bookable_path']}"
                f" | active={salon['is_active']}"
            )

            if salon["critical_missing_keys"]:
                self.stdout.write(
                    "  critical_missing: " + ", ".join(salon["critical_missing_keys"])
                )

            if salon["missing_items"]:
                for item in salon["missing_items"]:
                    self.stdout.write(f"  - {item['key']}: " f"{item['title']}")
            else:
                self.stdout.write("  - no missing checklist items")

        self.stdout.write("")
        self.stdout.write(
            "Summary: "
            f"total={summary['total']} "
            f"ready={summary['ready']} "
            f"incomplete={summary['incomplete']} "
            "without_bookable_path="
            f"{summary['without_bookable_path']}"
        )

    def handle(self, *args, **options):
        salons = self._build_queryset(
            salon_ids=options["salon_ids"],
            slugs=options["slugs"],
            active_only=options["active_only"],
        )

        serialized = [self._serialize_salon(salon) for salon in salons]

        if options["only_incomplete"]:
            serialized = [salon for salon in serialized if not salon["beta_ready"]]

        summary = self._build_summary(serialized)

        payload = {
            "ok": True,
            "read_only": True,
            "summary": summary,
            "salons": serialized,
        }

        if options["as_json"]:
            self.stdout.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            self._write_text(
                salons=serialized,
                summary=summary,
            )

        if options["strict"] and (not serialized or not summary["all_ready"]):
            raise CommandError("One or more selected beta salons are not ready.")
