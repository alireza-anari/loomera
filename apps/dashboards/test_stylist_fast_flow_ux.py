from datetime import time
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


class StylistFastFlowBackendTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(manager=self.manager)
        self.stylist = self.make_stylist()
        self.service = self.make_service(duration_minutes=30)
        self.customer = self.make_customer()
        self.connect_service(
            salon=self.salon,
            stylist=self.stylist,
            service=self.service,
        )
        DelayPolicy.objects.update_or_create(
            salon=self.salon,
            defaults={"no_show_after_minutes": 1440},
        )

    def make_pending_today(self):
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
            date_value=timezone.localdate(),
            start=time(10, 0),
            end=time(10, 30),
        )
        return order, detail

    def test_finalized_booking_auto_confirms_without_specialist_tap(self):
        order, detail = self.make_pending_today()

        confirmed = auto_confirm_order_details(order=order)

        self.assertEqual([item.pk for item in confirmed], [detail.pk])
        detail.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(
            detail.confirmation_status,
            OrderDetail.ConfirmationStatus.CONFIRMED,
        )
        self.assertEqual(
            detail.lifecycle_status,
            OrderDetail.ServiceLifecycleStatus.CONFIRMED,
        )
        self.assertTrue(order.stylist_approved)
        self.assertEqual(order.status, "confirmed")

    def test_today_happy_path_exposes_start_not_confirm_or_arrival(self):
        _, detail = self.make_pending_today()

        keys = [
            item["key"]
            for item in _get_allowed_stylist_lifecycle_actions(detail)
        ]

        self.assertIn("start_service", keys)
        self.assertIn("reject", keys)
        self.assertNotIn("confirm", keys)
        self.assertNotIn("arrived", keys)
        self.assertNotIn("client_late", keys)

    def test_start_is_one_tap_confirmation_checkin_and_service_start(self):
        order, detail = self.make_pending_today()

        message = _apply_stylist_lifecycle_action(
            detail,
            "start_service",
            actor=self.stylist.user,
        )

        detail.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(message, "خدمت شروع شد.")
        self.assertEqual(
            detail.confirmation_status,
            OrderDetail.ConfirmationStatus.CONFIRMED,
        )
        self.assertIsNotNone(detail.customer_arrived_at)
        self.assertIsNotNone(detail.service_started_at)
        self.assertEqual(
            detail.lifecycle_status,
            OrderDetail.ServiceLifecycleStatus.IN_SERVICE,
        )

        actions = _get_allowed_stylist_lifecycle_actions(detail)
        self.assertEqual(
            [item["key"] for item in actions],
            ["complete_service"],
        )

    def test_pay_in_salon_uses_one_collection_confirmation_after_completion(self):
        order, detail = self.make_pending_today()
        order.selected_payment_method = "pay_in_salon"
        order.save(update_fields=["selected_payment_method", "update_date"])

        _apply_stylist_lifecycle_action(detail, "start_service", actor=self.stylist.user)
        detail.refresh_from_db()
        _apply_stylist_lifecycle_action(detail, "complete_service", actor=self.stylist.user)
        detail.refresh_from_db()
        order.refresh_from_db()

        actions = _get_allowed_stylist_lifecycle_actions(detail)
        self.assertEqual([item["key"] for item in actions], ["confirm_cash_payment"])
        self.assertEqual(actions[0]["label"], "دریافت وجه شد")

        card = _serialize_stylist_appointment_card(detail)
        self.assertEqual(card["quick_action"]["key"], "confirm_cash_payment")

        message = _apply_stylist_lifecycle_action(
            detail, "confirm_cash_payment", actor=self.stylist.user
        )
        self.assertEqual(message, "دریافت وجه ثبت شد و پرداخت رزرو نهایی شد.")

        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertTrue(order.is_finally)
        self.assertEqual(order.status, "completed")
        payment = order.payment_order.filter(
            provider="manual", meta__source="pay_in_salon_cash"
        ).order_by("-id").first()
        self.assertIsNotNone(payment)
        self.assertTrue(payment.is_finally)
        self.assertEqual(payment.state, "success")
        self.assertTrue(payment.meta.get("received_at"))
        self.assertFalse(bool(payment.meta.get("customer_confirmed_at")))

        detail.refresh_from_db()
        self.assertEqual(_get_allowed_stylist_lifecycle_actions(detail), [])

    def test_customer_cannot_finalize_pay_in_salon_cash_receipt(self):
        from django.core.exceptions import ValidationError
        from apps.payments.finance import confirm_pay_in_salon_cash_payment

        order, _ = self.make_pending_today()
        with self.assertRaises(ValidationError):
            confirm_pay_in_salon_cash_payment(
                order, actor=self.customer.user, role="customer"
            )

    def test_today_card_serializes_primary_and_exception_actions(self):
        _, detail = self.make_pending_today()

        card = _serialize_stylist_appointment_card(detail)

        self.assertEqual(card["quick_action"]["key"], "start_service")
        self.assertEqual(card["exception_action"]["key"], "reject")


class StylistFastFlowStaticTests(TestCase):
    def test_today_surfaces_show_actions_without_opening_detail(self):
        base = Path(settings.BASE_DIR)
        home = (
            base / "templates/dashboards/stylist_dashboard.html"
        ).read_text(encoding="utf-8")
        appointments = (
            base / "templates/dashboards/stylist_appointments.html"
        ).read_text(encoding="utf-8")

        for template in (home, appointments):
            self.assertIn("data-stylist-fast-flow-card", template)
            self.assertIn("item.quick_action", template)
            self.assertIn("item.exception_action", template)
            self.assertIn('name="next"', template)
            self.assertIn('data-lm-form-ux="off"', template)

    def test_happy_path_action_builder_has_no_manual_confirm_or_arrival(self):
        views = (
            Path(settings.BASE_DIR) / "apps/dashboards/views.py"
        ).read_text(encoding="utf-8")

        allowed_block = views.split(
            "def _get_allowed_stylist_lifecycle_actions", 1
        )[1].split("def _apply_stylist_lifecycle_action", 1)[0]

        self.assertNotIn('"key": "confirm"', allowed_block)
        self.assertNotIn('"key": "arrived"', allowed_block)
        self.assertNotIn('"key": "client_late"', allowed_block)
        self.assertIn('"key": "start_service"', allowed_block)
        self.assertIn('"key": "complete_service"', allowed_block)

    def test_completion_attempts_financial_finalization_automatically(self):
        views = (
            Path(settings.BASE_DIR) / "apps/dashboards/views.py"
        ).read_text(encoding="utf-8")

        complete_block = views.split(
            'if action == "complete_service":', 1
        )[1].split('raise ValidationError("این عملیات معتبر نیست.")', 1)[0]
        self.assertIn("finalize_order_financials(", complete_block)
        self.assertIn("Automatic financial finalization failed", complete_block)

    def test_customer_booking_copy_no_longer_promises_manual_confirmation(self):
        lifecycle = (
            Path(settings.BASE_DIR) / "apps/orders/lifecycle.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "قطعی ثبت شد و در برنامه کاری متخصص قرار گرفت",
            lifecycle,
        )
        self.assertNotIn(
            "ثبت شد و در انتظار تایید مجموعه/متخصص است",
            lifecycle,
        )

    def test_dashboard_manual_bookings_create_confirmed_details(self):
        views = (
            Path(settings.BASE_DIR) / "apps/dashboards/views.py"
        ).read_text(encoding="utf-8")

        self.assertGreaterEqual(
            views.count(
                "confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED"
            ),
            2,
        )
        self.assertGreaterEqual(
            views.count(
                "lifecycle_status=OrderDetail.ServiceLifecycleStatus.CONFIRMED"
            ),
            2,
        )
