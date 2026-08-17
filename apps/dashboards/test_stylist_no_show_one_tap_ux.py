from datetime import time, timedelta
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.dashboards.views import (
    _apply_stylist_lifecycle_action,
    _get_allowed_stylist_lifecycle_actions,
    _serialize_stylist_appointment_card,
)
from apps.orders.appointment_lifecycle import auto_confirm_order_details
from apps.orders.models import DelayPolicy, OrderDetail
from tests_stage1_helpers import Stage1DomainFactoryMixin


class StylistNoShowOneTapBackendTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(manager=self.manager)
        self.stylist = self.make_stylist()
        self.service = self.make_service(duration_minutes=30)
        self.customer = self.make_customer()
        self.connect_service(salon=self.salon, stylist=self.stylist, service=self.service)
        DelayPolicy.objects.update_or_create(
            salon=self.salon,
            defaults={"no_show_after_minutes": 0, "no_show_dispute_window_hours": 12},
        )

    def make_eligible_detail(self):
        order = self.make_order(
            customer=self.customer,
            salon=self.salon,
            status="pending",
            is_paid=False,
            is_finally=True,
            stylist_approved=False,
        )
        detail = self.make_order_detail(
            order=order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=timezone.localdate() - timedelta(days=1),
            start=time(10, 0),
            end=time(10, 30),
        )
        auto_confirm_order_details(order=order)
        detail.refresh_from_db()
        return order, detail

    def test_eligible_no_show_exposes_one_decision_action(self):
        _, detail = self.make_eligible_detail()
        keys = [item["key"] for item in _get_allowed_stylist_lifecycle_actions(detail)]
        self.assertIn("no_show_decision", keys)
        self.assertNotIn("no_show_pending", keys)
        self.assertNotIn("confirm_no_show", keys)
        self.assertNotIn("mark_disputed", keys)
        card = _serialize_stylist_appointment_card(detail)
        self.assertEqual(card["exception_action"]["key"], "no_show_decision")

    def test_direct_confirmation_finishes_no_show_in_one_request(self):
        order, detail = self.make_eligible_detail()
        message = _apply_stylist_lifecycle_action(detail, "no_show_confirm_direct", actor=self.stylist.user)
        detail.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(message, "عدم حضور مشتری تأیید شد.")
        self.assertIsNotNone(detail.no_show_pending_at)
        self.assertIsNotNone(detail.no_show_confirmed_at)
        self.assertEqual(detail.lifecycle_status, OrderDetail.ServiceLifecycleStatus.NO_SHOW_CONFIRMED)
        self.assertEqual(order.status, "no_show")

    def test_review_choice_moves_appointment_to_dispute(self):
        order, detail = self.make_eligible_detail()
        message = _apply_stylist_lifecycle_action(detail, "no_show_review", actor=self.stylist.user)
        detail.refresh_from_db()
        order.refresh_from_db()
        self.assertIn("بررسی پشتیبانی", message)
        self.assertIsNotNone(detail.no_show_pending_at)
        self.assertEqual(detail.lifecycle_status, OrderDetail.ServiceLifecycleStatus.DISPUTED)
        self.assertEqual(order.status, "disputed")


class StylistNoShowOneTapStaticTests(TestCase):
    def test_all_specialist_surfaces_use_the_same_decision_dialog(self):
        base = Path(settings.BASE_DIR)
        partial = (base / "templates/dashboards/partials/stylist_no_show_decision_dialog.html").read_text(encoding="utf-8")
        self.assertIn("مشتری نیامد؟", partial)
        self.assertIn('value="no_show_confirm_direct"', partial)
        self.assertIn('value="no_show_review"', partial)
        self.assertIn("تأیید عدم حضور", partial)
        self.assertIn("نیاز به بررسی", partial)
        for relative in (
            "templates/dashboards/stylist_dashboard.html",
            "templates/dashboards/stylist_appointments.html",
            "templates/dashboards/stylist_appointment_detail.html",
        ):
            template = (base / relative).read_text(encoding="utf-8")
            self.assertIn("stylist_no_show_decision_dialog.html", template)
            self.assertIn("data-no-show-decision-open", template)
