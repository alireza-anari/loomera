from __future__ import annotations

from datetime import time, timedelta
from pathlib import Path

from django.test import TestCase
from django.utils import timezone

from tests_stage1_helpers import Stage1DomainFactoryMixin

from apps.dashboards.layout import _build_dashboard_notifications
from apps.notifications.models import NotificationRecipient
from apps.orders.lifecycle import create_notification
from apps.orders.views import _notify_manager_and_stylists_for_customer_order_event


class StylistNotificationRegressionTests(Stage1DomainFactoryMixin, TestCase):
    def _context(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)
        stylist = self.make_stylist()
        service = self.make_service()
        customer = self.make_customer()
        self.connect_service(salon=salon, stylist=stylist, service=service)
        order = self.make_order(customer=customer, salon=salon)
        detail = self.make_order_detail(
            order=order,
            service=service,
            stylist=stylist,
            salon=salon,
            date_value=timezone.localdate() + timedelta(days=1),
            start=time(10, 0),
            end=time(10, 30),
        )
        return salon, stylist, order, detail

    def test_booking_notification_does_not_render_contextual_duplicate(self):
        salon, stylist, order, detail = self._context()
        create_notification(
            order=order,
            order_detail=detail,
            audience_role="stylist",
            channel="dashboard",
            event_type="booking_created",
            title="نوبت جدید برای شما ثبت شد",
            body="رزرو جدید ثبت شده است.",
            stylist=stylist,
            target_user=stylist.user,
            delivery_status="sent",
            meta={"detail_id": detail.pk},
        )

        payload = _build_dashboard_notifications(
            salon,
            role="stylist",
            user=stylist.user,
            stylist=stylist,
        )
        booking_items = [
            item for item in payload["items"]
            if item.get("event_type") == "booking_created"
        ]
        self.assertEqual(len(booking_items), 1)

    def test_reschedule_and_cancel_create_unified_stylist_recipients(self):
        _salon, stylist, order, detail = self._context()

        _notify_manager_and_stylists_for_customer_order_event(
            order,
            event_type="booking_rescheduled",
            manager_title="زمان نوبت تغییر کرد",
            stylist_title="زمان نوبت شما تغییر کرد",
            body="زمان جدید را بررسی کنید.",
            detail_meta={"base_appointment_id": detail.pk},
        )
        self.assertEqual(
            NotificationRecipient.objects.filter(
                user=stylist.user,
                audience_role="stylist",
                notification__event_type="booking_rescheduled",
            ).count(),
            1,
        )

        _notify_manager_and_stylists_for_customer_order_event(
            order,
            event_type="booking_cancelled",
            manager_title="نوبت لغو شد",
            stylist_title="نوبت شما لغو شد",
            body="مشتری نوبت را لغو کرد.",
            detail_meta={"base_appointment_id": detail.pk},
        )
        self.assertEqual(
            NotificationRecipient.objects.filter(
                user=stylist.user,
                audience_role="stylist",
                notification__event_type="booking_cancelled",
            ).count(),
            1,
        )

    def test_dashboard_notification_polling_is_visible_and_short_interval(self):
        script = Path("static/js/pages/dashboard_layout.js").read_text(encoding="utf-8")
        self.assertIn('document.visibilityState === "visible"', script)
        self.assertIn('}, 10000);', script)
