from __future__ import annotations

from datetime import time

from django.test import TestCase
from django.utils import timezone

from apps.orders.lifecycle import (
    build_customer_progress_context,
    determine_current_stage,
)
from tests_stage1_helpers import Stage1DomainFactoryMixin


class NoShowLifecycleStageTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
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
            selected_payment_method="pay_in_salon",
        )

        self.detail = self.make_order_detail(
            order=self.order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=timezone.localdate(),
            start=time(10, 0),
            end=time(10, 30),
        )

    def test_no_show_is_a_terminal_lifecycle_stage(self):
        self.assertEqual(
            determine_current_stage(self.order),
            "no_show",
        )

        progress = build_customer_progress_context(self.order)

        self.assertEqual(
            progress["current_stage"],
            "no_show",
        )
        self.assertEqual(
            progress["current_stage_label"],
            "عدم حضور تأیید شد",
        )
        self.assertEqual(
            progress["current_step"]["key"],
            "no_show",
        )
        self.assertTrue(
            progress["current_step"]["is_current"],
        )
