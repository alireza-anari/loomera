from __future__ import annotations

from datetime import time
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.dashboards.appointment_management import (
    _apply_basic_filters,
    _apply_tab_filter,
    _build_appointment_summary_metrics,
    _build_appointment_tab_counts,
    build_manager_appointment_detail_context,
    get_allowed_partner_actions,
    get_order_status_meta,
)
from apps.dashboards.views import JALALI_WEEKDAY_MAP
from apps.orders.models import OrderDetail
from apps.salons.models import SalonOpeningHours
from tests_stage1_helpers import Stage1DomainFactoryMixin


class NoShowOperationalStatusTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.today = timezone.localdate()
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(
            manager=self.manager,
        )
        self.stylist = self.make_stylist()
        self.service = self.make_service()
        self.customer = self.make_customer()

        self.connect_service(
            salon=self.salon,
            stylist=self.stylist,
            service=self.service,
        )

        self.order = self.make_order(
            customer=self.customer,
            salon=self.salon,
            status="no_show",
            is_paid=False,
            is_finally=True,
            stylist_approved=True,
        )

        self.detail = self.make_order_detail(
            order=self.order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.today,
            start=time(10, 0),
            end=time(10, 30),
            no_show_confirmed_at=timezone.now(),
            no_show_confirmed_by=self.manager.user,
        )

        SalonOpeningHours.objects.create(
            salon=self.salon,
            day_of_week=(
                JALALI_WEEKDAY_MAP[
                    self.today.weekday()
                ]
            ),
            open_time=time(9, 0),
            close_time=time(20, 0),
            is_closed=False,
        )

    def test_no_show_is_terminal_in_manager_workspace(
        self,
    ):
        status_meta = get_order_status_meta(
            self.order
        )

        self.assertEqual(
            status_meta["key"],
            "no_show",
        )
        self.assertEqual(
            status_meta["label"],
            "عدم حضور",
        )
        self.assertEqual(
            get_allowed_partner_actions(
                self.order,
                self.detail,
            ),
            [],
        )

        context = (
            build_manager_appointment_detail_context(
                self.salon,
                self.detail,
            )["manager_appointment_detail"]
        )

        self.assertEqual(
            context["status"]["key"],
            "no_show",
        )
        self.assertEqual(
            context["actions"],
            [],
        )
        self.assertIn(
            "عدم حضور",
            [
                item["title"]
                for item in context["timeline"]
            ],
        )

    def test_no_show_is_excluded_from_active_counts(
        self,
    ):
        base_qs = OrderDetail.objects.filter(
            salon=self.salon
        )

        counts = _build_appointment_tab_counts(
            base_qs,
            self.today,
        )
        metrics = (
            _build_appointment_summary_metrics(
                base_qs,
                self.today,
            )
        )

        self.assertEqual(counts["no_show"], 1)
        self.assertEqual(counts["past"], 1)
        self.assertEqual(counts["upcoming"], 0)
        self.assertEqual(counts["in_progress"], 0)
        self.assertEqual(counts["attention"], 0)
        self.assertEqual(counts["unpaid"], 0)

        self.assertEqual(
            metrics["upcoming_count"],
            0,
        )
        self.assertEqual(
            metrics["unpaid_count"],
            0,
        )
        self.assertEqual(
            metrics["in_service_count"],
            0,
        )
        self.assertEqual(
            metrics["awaiting_confirm_count"],
            0,
        )
        self.assertEqual(
            metrics["pay_in_salon_pending_count"],
            0,
        )

        self.assertTrue(
            _apply_tab_filter(
                base_qs,
                "no_show",
                self.today,
            )
            .filter(pk=self.detail.pk)
            .exists()
        )

        self.assertFalse(
            _apply_tab_filter(
                base_qs,
                "unpaid",
                self.today,
            )
            .filter(pk=self.detail.pk)
            .exists()
        )

        self.assertFalse(
            _apply_basic_filters(
                base_qs,
                status="unpaid",
            )
            .filter(pk=self.detail.pk)
            .exists()
        )

    def test_calendar_api_reports_no_show(self):
        self.client.force_login(
            self.manager.user
        )

        with patch(
            "apps.dashboards.views."
            "_redirect_to_required_onboarding",
            return_value=None,
        ):
            response = self.client.get(
                reverse(
                    "dashboards:"
                    "api_get_calendar_data",
                    kwargs={
                        "salon_id": self.salon.pk,
                    },
                ),
                {
                    "date": self.today.isoformat(),
                },
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        appointment = next(
            item
            for item in response.json()[
                "appointments"
            ]
            if item["id"] == self.detail.pk
        )

        self.assertEqual(
            appointment["status"],
            "no_show",
        )
        self.assertEqual(
            appointment["status_label"],
            "عدم حضور",
        )
