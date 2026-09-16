from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.dashboards.views import (
    SalonMembershipStatus,
    TeamMemberView,
    _active_upcoming_appointment_q,
    _build_team_member_stylists_queryset,
)
from apps.orders.models import OrderDetail
from tests_stage1_helpers import Stage1DomainFactoryMixin


class DashboardUpcomingAppointmentSemanticsTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(manager=self.manager)
        self.stylist = self.make_stylist()
        self.customer = self.make_customer()
        self.service = self.make_service(name="کوتاهی")
        self.connect_service(
            salon=self.salon,
            stylist=self.stylist,
            service=self.service,
        )

    def _detail(self, *, at_time, status="confirmed", confirmation_status=None):
        order = self.make_order(
            customer=self.customer,
            salon=self.salon,
            status=status,
        )
        kwargs = {}
        if confirmation_status is not None:
            kwargs["confirmation_status"] = confirmation_status
        return self.make_order_detail(
            order=order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.now.date(),
            start=at_time,
            end=(
                datetime.combine(self.now.date(), at_time)
                + timedelta(minutes=30)
            ).time(),
            **kwargs,
        )

    def test_team_card_does_not_count_past_appointments_from_today_as_upcoming(self):
        self.now = timezone.make_aware(
            datetime(2026, 8, 29, 18, 0),
            timezone.get_current_timezone(),
        )
        for start in (time(9, 0), time(10, 15), time(11, 45)):
            self._detail(
                at_time=start,
                confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED,
            )

        with patch("apps.dashboards.views.timezone.now", return_value=self.now):
            stylist = list(
                _build_team_member_stylists_queryset(self.salon).order_by("pk")
            )[0]

        stylist.membership_status_for_salon = SalonMembershipStatus.ACTIVE
        card = TeamMemberView()._serialize_stylist(stylist, self.salon)

        self.assertEqual(stylist.upcoming_count, 0)
        self.assertEqual(card["upcoming_count"], 0)
        self.assertEqual(card["status_label"], "آماده پذیرش")

    def test_upcoming_definition_matches_lumi_active_future_rules(self):
        self.now = timezone.make_aware(
            datetime(2026, 8, 29, 12, 0),
            timezone.get_current_timezone(),
        )

        self._detail(
            at_time=time(9, 0),
            confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED,
        )
        future = self._detail(
            at_time=time(14, 0),
            confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED,
        )
        self._detail(
            at_time=time(15, 0),
            confirmation_status=OrderDetail.ConfirmationStatus.REJECTED,
        )
        self._detail(
            at_time=time(16, 0),
            status="completed",
            confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED,
        )

        rows = list(
            OrderDetail.objects.filter(
                salon=self.salon,
                stylist=self.stylist,
            )
            .filter(_active_upcoming_appointment_q(now=self.now))
            .order_by("time")
            .values_list("pk", flat=True)
        )

        self.assertEqual(rows, [future.pk])
