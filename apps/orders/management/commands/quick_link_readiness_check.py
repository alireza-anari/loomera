from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata

from django.contrib.contenttypes.models import ContentType
from django.contrib.staticfiles import finders
from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db.models import Count, F, Subquery
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent
from apps.orders.models import BookingQuickLink, Order
from apps.orders.quick_link_qr import (
    BOOKING_QUICK_LINK_QR_GLYPH,
)
from apps.orders.quick_links import (
    BOOKING_QUICK_LINK_CONVERTED_EVENT,
    BOOKING_QUICK_LINK_OPENED_EVENT,
    BOOKING_QUICK_LINK_STARTED_EVENT,
)


@dataclass(frozen=True)
class ReadinessFinding:
    level: str
    code: str
    message: str
    count: int = 0


class Command(BaseCommand):
    help = (
        "Run read-only integrity and dependency checks for "
        "Loomera booking quick links."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fail-on-warnings",
            action="store_true",
            help=(
                "Return a non-zero exit code when warning "
                "findings are present."
            ),
        )

    def handle(self, *args, **options):
        findings = self._collect_findings()

        failures = [
            finding
            for finding in findings
            if finding.level == "FAIL"
        ]
        warnings = [
            finding
            for finding in findings
            if finding.level == "WARN"
        ]
        passes = [
            finding
            for finding in findings
            if finding.level == "PASS"
        ]

        self.stdout.write(
            "Loomera quick-link readiness started."
        )

        for finding in findings:
            suffix = (
                f" (count={finding.count})"
                if finding.count
                else ""
            )
            line = (
                f"{finding.level:<4} "
                f"{finding.code}: "
                f"{finding.message}"
                f"{suffix}"
            )

            if finding.level == "FAIL":
                self.stdout.write(
                    self.style.ERROR(line)
                )
            elif finding.level == "WARN":
                self.stdout.write(
                    self.style.WARNING(line)
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(line)
                )

        self.stdout.write("")
        self.stdout.write(
            "Summary: "
            f"{len(passes)} pass, "
            f"{len(warnings)} warning, "
            f"{len(failures)} failure."
        )

        if failures:
            raise CommandError(
                "Quick-link readiness failed."
            )

        if (
            warnings
            and options["fail_on_warnings"]
        ):
            raise CommandError(
                "Quick-link readiness has warnings."
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Quick-link readiness passed."
            )
        )

    def _collect_findings(self):
        findings = []
        findings.extend(
            self._dependency_findings()
        )
        findings.extend(
            self._model_contract_findings()
        )
        findings.extend(
            self._data_integrity_findings()
        )
        return findings

    def _dependency_findings(self):
        findings = []

        glyph_path = finders.find(
            BOOKING_QUICK_LINK_QR_GLYPH
        )

        if glyph_path:
            findings.append(
                ReadinessFinding(
                    "PASS",
                    "qr-glyph",
                    (
                        "Official Loomera QR glyph "
                        "is available."
                    ),
                )
            )
        else:
            findings.append(
                ReadinessFinding(
                    "FAIL",
                    "qr-glyph",
                    (
                        "Official Loomera QR glyph "
                        "could not be resolved."
                    ),
                )
            )

        for package_name in (
            "qrcode",
            "Pillow",
        ):
            try:
                version = metadata.version(
                    package_name
                )
            except metadata.PackageNotFoundError:
                findings.append(
                    ReadinessFinding(
                        "FAIL",
                        f"dependency-{package_name.lower()}",
                        (
                            f"{package_name} is not "
                            "installed."
                        ),
                    )
                )
            else:
                findings.append(
                    ReadinessFinding(
                        "PASS",
                        f"dependency-{package_name.lower()}",
                        (
                            f"{package_name} "
                            f"{version} is installed."
                        ),
                    )
                )

        return findings

    def _model_contract_findings(self):
        required_link_fields = {
            "placement",
            "campaign_name",
            "internal_note",
            "opens_count",
            "archived_at",
            "last_converted_at",
        }

        link_field_names = {
            field.name
            for field
            in BookingQuickLink._meta.get_fields()
        }

        missing_link_fields = sorted(
            required_link_fields
            - link_field_names
        )

        if missing_link_fields:
            findings = [
                ReadinessFinding(
                    "FAIL",
                    "model-contract",
                    (
                        "BookingQuickLink is missing: "
                        + ", ".join(
                            missing_link_fields
                        )
                    ),
                )
            ]
        else:
            findings = [
                ReadinessFinding(
                    "PASS",
                    "model-contract",
                    (
                        "BookingQuickLink analytics "
                        "and management fields exist."
                    ),
                )
            ]

        order_field_names = {
            field.name
            for field
            in Order._meta.get_fields()
        }

        if "booking_quick_link" not in order_field_names:
            findings.append(
                ReadinessFinding(
                    "FAIL",
                    "order-attribution-field",
                    (
                        "Order.booking_quick_link "
                        "is missing."
                    ),
                )
            )
        else:
            findings.append(
                ReadinessFinding(
                    "PASS",
                    "order-attribution-field",
                    (
                        "Order booking attribution "
                        "field exists."
                    ),
                )
            )

        return findings

    def _data_integrity_findings(self):
        findings = []

        content_type = (
            ContentType.objects.get_for_model(
                BookingQuickLink,
                for_concrete_model=False,
            )
        )

        archived_active_count = (
            BookingQuickLink.objects.filter(
                archived_at__isnull=False,
                is_active=True,
            ).count()
        )
        findings.append(
            self._count_finding(
                code="archived-active",
                count=archived_active_count,
                fail_message=(
                    "Archived links are still active."
                ),
                pass_message=(
                    "Archived links are inactive."
                ),
            )
        )

        cross_salon_order_count = (
            Order.objects.filter(
                booking_quick_link__isnull=False,
            )
            .exclude(
                salon_id=F(
                    "booking_quick_link__salon_id"
                )
            )
            .count()
        )
        findings.append(
            self._count_finding(
                code="cross-salon-attribution",
                count=cross_salon_order_count,
                fail_message=(
                    "Attributed orders reference "
                    "a quick link from another salon."
                ),
                pass_message=(
                    "Order attribution remains "
                    "inside the owning salon."
                ),
            )
        )

        link_ids = (
            BookingQuickLink.objects.order_by()
            .values("pk")
        )

        orphan_event_count = (
            AnalyticsEvent.objects.filter(
                target_content_type=content_type,
                event_type__in=[
                    BOOKING_QUICK_LINK_OPENED_EVENT,
                    BOOKING_QUICK_LINK_STARTED_EVENT,
                    BOOKING_QUICK_LINK_CONVERTED_EVENT,
                ],
            )
            .exclude(
                target_object_id__in=Subquery(
                    link_ids
                )
            )
            .count()
        )
        findings.append(
            self._count_finding(
                code="orphan-events",
                count=orphan_event_count,
                fail_message=(
                    "Quick-link analytics events "
                    "reference a missing link."
                ),
                pass_message=(
                    "Quick-link analytics targets "
                    "are valid."
                ),
            )
        )

        duplicate_conversion_count = (
            AnalyticsEvent.objects.filter(
                target_content_type=content_type,
                event_type=(
                    BOOKING_QUICK_LINK_CONVERTED_EVENT
                ),
                order_id__isnull=False,
            )
            .values(
                "target_object_id",
                "order_id",
            )
            .annotate(total=Count("id"))
            .filter(total__gt=1)
            .count()
        )
        findings.append(
            self._count_finding(
                code="duplicate-conversions",
                count=duplicate_conversion_count,
                fail_message=(
                    "An order has duplicate "
                    "conversion events for one link."
                ),
                pass_message=(
                    "Conversion events are "
                    "idempotent per order and link."
                ),
            )
        )

        conversion_order_mismatch_count = (
            AnalyticsEvent.objects.filter(
                target_content_type=content_type,
                event_type=(
                    BOOKING_QUICK_LINK_CONVERTED_EVENT
                ),
                order_id__isnull=False,
            )
            .exclude(
                order__booking_quick_link_id=F(
                    "target_object_id"
                )
            )
            .count()
        )
        findings.append(
            self._count_finding(
                code="conversion-order-mismatch",
                count=(
                    conversion_order_mismatch_count
                ),
                fail_message=(
                    "Conversion event target and "
                    "Order.booking_quick_link differ."
                ),
                pass_message=(
                    "Conversion events match "
                    "their attributed orders."
                ),
            )
        )

        blank_session_count = (
            AnalyticsEvent.objects.filter(
                target_content_type=content_type,
                event_type__in=[
                    BOOKING_QUICK_LINK_OPENED_EVENT,
                    BOOKING_QUICK_LINK_STARTED_EVENT,
                ],
                session_key="",
            ).count()
        )
        findings.append(
            self._warning_count_finding(
                code="blank-analytics-session",
                count=blank_session_count,
                warning_message=(
                    "Opened or started events "
                    "have an empty session key."
                ),
                pass_message=(
                    "Opened and started events "
                    "have session attribution."
                ),
            )
        )

        expired_active_count = (
            BookingQuickLink.objects.filter(
                is_active=True,
                is_permanent=False,
                archived_at__isnull=True,
                expires_at__isnull=False,
                expires_at__lte=timezone.now(),
            ).count()
        )
        findings.append(
            self._warning_count_finding(
                code="expired-active",
                count=expired_active_count,
                warning_message=(
                    "Expired temporary links "
                    "still have is_active=True. "
                    "They remain blocked by can_open."
                ),
                pass_message=(
                    "No expired temporary link "
                    "is marked active."
                ),
            )
        )

        multi_order_one_time_count = (
            BookingQuickLink.objects.filter(
                is_permanent=False,
            )
            .annotate(
                attributed_count=Count(
                    "attributed_orders",
                    distinct=True,
                )
            )
            .filter(
                attributed_count__gt=1
            )
            .count()
        )
        findings.append(
            self._count_finding(
                code="one-time-multiple-orders",
                count=multi_order_one_time_count,
                fail_message=(
                    "A non-permanent link is "
                    "attributed to multiple orders."
                ),
                pass_message=(
                    "Non-permanent links have "
                    "at most one attributed order."
                ),
            )
        )

        return findings

    @staticmethod
    def _count_finding(
        *,
        code,
        count,
        fail_message,
        pass_message,
    ):
        if count:
            return ReadinessFinding(
                "FAIL",
                code,
                fail_message,
                count=count,
            )

        return ReadinessFinding(
            "PASS",
            code,
            pass_message,
        )

    @staticmethod
    def _warning_count_finding(
        *,
        code,
        count,
        warning_message,
        pass_message,
    ):
        if count:
            return ReadinessFinding(
                "WARN",
                code,
                warning_message,
                count=count,
            )

        return ReadinessFinding(
            "PASS",
            code,
            pass_message,
        )
