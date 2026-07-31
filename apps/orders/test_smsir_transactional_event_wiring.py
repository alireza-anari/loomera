from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.notifications.smsir_transactional import template_setting_name
from apps.orders.lifecycle import (
    queue_customer_booking_cancelled_sms,
    queue_customer_booking_confirmed_sms,
    queue_customer_booking_created_sms,
    queue_customer_booking_rescheduled_sms,
)


class SMSIRTransactionalEventWiringTests(SimpleTestCase):
    def _order(self):
        user = SimpleNamespace(pk=23)
        customer = SimpleNamespace(pk=11, user=user)
        return SimpleNamespace(pk=17, customer=customer)

    def _run_on_commit_immediately(self, callback):
        callback()

    def test_paid_customer_uses_booking_created_template(self):
        self.assertEqual(
            template_setting_name(
                event_type="booking_paid",
                audience_role="customer",
            ),
            "SMSIR_BOOKING_CREATED_TEMPLATE_ID",
        )

    @patch("apps.orders.lifecycle._create_sms_notification")
    @patch("apps.orders.lifecycle.transaction.on_commit")
    def test_booking_created_is_queued_after_commit(
        self,
        mocked_on_commit,
        mocked_create_sms,
    ):
        mocked_on_commit.side_effect = self._run_on_commit_immediately
        order = self._order()

        queued = queue_customer_booking_created_sms(
            order,
            event_type="booking_paid",
        )

        self.assertTrue(queued)
        mocked_create_sms.assert_called_once()
        kwargs = mocked_create_sms.call_args.kwargs
        self.assertEqual(kwargs["event_type"], "booking_paid")
        self.assertEqual(kwargs["audience_role"], "customer")
        self.assertIs(kwargs["order"], order)

    @patch("apps.orders.lifecycle._create_sms_notification")
    @patch("apps.orders.lifecycle.transaction.on_commit")
    def test_confirmation_uses_detail_and_confirmed_event(
        self,
        mocked_on_commit,
        mocked_create_sms,
    ):
        mocked_on_commit.side_effect = self._run_on_commit_immediately
        order = self._order()
        detail = SimpleNamespace(pk=91)

        queued = queue_customer_booking_confirmed_sms(
            order,
            order_detail=detail,
        )

        self.assertTrue(queued)
        kwargs = mocked_create_sms.call_args.kwargs
        self.assertEqual(kwargs["event_type"], "stylist_confirmed")
        self.assertIs(kwargs["order_detail"], detail)

    @patch("apps.orders.lifecycle._create_sms_notification")
    @patch("apps.orders.lifecycle.transaction.on_commit")
    def test_cancel_and_reschedule_use_approved_event_names(
        self,
        mocked_on_commit,
        mocked_create_sms,
    ):
        mocked_on_commit.side_effect = self._run_on_commit_immediately
        order = self._order()

        queue_customer_booking_cancelled_sms(
            order,
            event_type="stylist_rejected_cancelled",
        )
        queue_customer_booking_rescheduled_sms(order)

        event_types = [
            call.kwargs["event_type"]
            for call in mocked_create_sms.call_args_list
        ]
        self.assertEqual(
            event_types,
            ["stylist_rejected_cancelled", "booking_rescheduled"],
        )

    @patch("apps.orders.lifecycle._create_sms_notification")
    @patch("apps.orders.lifecycle.transaction.on_commit")
    def test_missing_customer_user_does_not_queue(
        self,
        mocked_on_commit,
        mocked_create_sms,
    ):
        order = SimpleNamespace(pk=17, customer=SimpleNamespace(user=None))

        queued = queue_customer_booking_created_sms(order)

        self.assertFalse(queued)
        mocked_on_commit.assert_not_called()
        mocked_create_sms.assert_not_called()
