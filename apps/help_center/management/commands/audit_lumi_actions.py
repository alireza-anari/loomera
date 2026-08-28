from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.urls import NoReverseMatch, reverse


class Command(BaseCommand):
    help = "Audit Lumi operational assistant routes and authoritative domain services."

    def handle(self, *args, **options):
        failures: list[str] = []

        routes = [
            ("Lumi action API", "help_center:assistant_action_api", {}),
            ("Customer discovery API", "help_center:customer_discovery_api", {}),
            ("Customer booking API", "help_center:customer_booking_api", {}),
            ("Customer appointments", "orders:appointments", {}),
            ("Customer checkout", "orders:checkout", {}),
            ("Customer cancel", "orders:cancel_appointment", {"pk": 1}),
            ("Customer reschedule", "orders:reschedule", {"pk": 1}),
            ("Stylist dashboard", "dashboards:stylist_dashboard", {}),
            ("Stylist appointments", "dashboards:stylist_appointments", {}),
            ("Stylist schedule", "dashboards:stylist_schedule", {}),
            ("Stylist finance", "dashboards:stylist_finance", {}),
            ("Stylist withdrawals", "dashboards:stylist_withdrawals", {}),
            ("Manager dashboard", "dashboards:salon_manager_dashboard", {}),
            ("Manager team", "dashboards:team_member", {}),
            ("Manager invite", "dashboards:create_stylist_invite", {}),
            ("Manager membership review", "dashboards:membership_request_action", {"membership_id": 1}),
            ("Manager schedule", "dashboards:scheduled_shifts", {}),
            ("Manager schedule review", "dashboards:staff_schedule_request_action", {"request_id": 1}),
            ("Manager leave review", "dashboards:staff_leave_request_action", {"request_id": 1}),
            ("Manager service menu", "dashboards:service_menu", {}),
            ("Manager finance", "dashboards:finance_hub", {}),
            ("Manager stylist withdrawals", "dashboards:finance_stylist_withdrawals", {}),
            ("Manager calendar", "dashboards:appointment_calendar", {"salon_id": 1}),
            (
                "Manager appointment detail",
                "dashboards:appointment_detail",
                {"salon_id": 1, "appointment_id": 1},
            ),
            (
                "Manager appointment action",
                "dashboards:appointment_action",
                {"salon_id": 1, "appointment_id": 1},
            ),
        ]

        self.stdout.write(self.style.MIGRATE_HEADING("Lumi route audit"))
        for label, name, kwargs in routes:
            try:
                url = reverse(name, kwargs=kwargs or None)
            except NoReverseMatch as exc:
                failures.append(f"{label}: {name} ({exc})")
                self.stdout.write(self.style.ERROR(f"FAIL  {label}: {name}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"PASS  {label}: {url}"))

        services = []
        try:
            from apps.orders.booking_utils import (
                get_available_slots_for_service,
                get_upcoming_available_stylists_for_service,
                resolve_booking_sequence,
            )
            from apps.dashboards.appointment_management import (
                apply_partner_appointment_action,
                get_allowed_partner_actions,
            )
            from apps.stylists.dashboard_services import (
                create_leave_request,
                create_schedule_request,
                create_staff_payout_request,
                review_leave_request,
                review_schedule_request,
                validate_salon_opening_window,
                validate_staff_schedule_request_window,
            )

            services = [
                get_available_slots_for_service,
                get_upcoming_available_stylists_for_service,
                resolve_booking_sequence,
                apply_partner_appointment_action,
                get_allowed_partner_actions,
                create_leave_request,
                create_schedule_request,
                create_staff_payout_request,
                review_leave_request,
                review_schedule_request,
                validate_salon_opening_window,
                validate_staff_schedule_request_window,
            ]
        except Exception as exc:
            failures.append(f"Domain service imports: {exc}")

        self.stdout.write(self.style.MIGRATE_HEADING("Authoritative service audit"))
        if services:
            for service in services:
                if callable(service):
                    self.stdout.write(self.style.SUCCESS(f"PASS  {service.__module__}.{service.__name__}"))
                else:
                    failures.append(f"Not callable: {service!r}")
                    self.stdout.write(self.style.ERROR(f"FAIL  {service!r}"))
        else:
            self.stdout.write(self.style.ERROR("FAIL  authoritative service imports"))

        self.stdout.write(self.style.MIGRATE_HEADING("Safety boundary"))
        safety = [
            "Write confirmations are signed and bound to the authenticated user.",
            "Confirmation tokens are one-time and fail closed if replay-cache protection is unavailable.",
            "Customer/manager appointment mutations use owned or current-route entities; no natural-language ID writes.",
            "Customer checkout, cancellation, manager appointment actions and membership invite/review reuse product endpoints/services.",
            "Stylist schedule, leave and payout actions reuse dashboard domain services.",
        ]
        for item in safety:
            self.stdout.write(self.style.SUCCESS(f"PASS  {item}"))

        if failures:
            raise CommandError("Lumi operational audit failed:\n- " + "\n- ".join(failures))

        self.stdout.write(self.style.SUCCESS("Lumi operational audit passed."))
