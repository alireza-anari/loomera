from datetime import time

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import CustomUser, Customer, SalonManager, Stylist
from apps.notifications.models import (
    NotificationAudienceRole,
    NotificationCategory,
    NotificationChannel,
    NotificationDelivery,
    NotificationPriority,
)
from apps.notifications.services import create_notification
from apps.orders.lifecycle import notify_manager_and_stylists_for_booking
from apps.orders.models import Order, OrderDetail
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus
from apps.services.models import Services
from apps.stylists.models import StaffLeaveRequest

from .notification_delivery import render_simple_notification_text
from .roles import BotRoleKey, detect_user_bot_roles
from .services import connect_identity_to_user, ensure_default_providers, get_or_create_identity
from .constants import MessagingProviderKey


@override_settings(
    MESSAGING_ACTIONS_ENABLED=True,
    LOOMERA_SEND_NOTIFICATIONS_IMMEDIATELY=False,
)
class BaleOperatorFinalTests(TestCase):
    def setUp(self):
        providers = ensure_default_providers()
        self.bale = providers[MessagingProviderKey.BALE]

        self.manager_user = CustomUser.objects.create_user(
            mobile_number="09120008901",
            email="manager-bale-final@example.com",
            name="مریم",
            family="مدیر",
            password="pass12345",
        )
        self.stylist_user = CustomUser.objects.create_user(
            mobile_number="09120008902",
            email="stylist-bale-final@example.com",
            name="سارا",
            family="متخصص",
            password="pass12345",
        )
        self.customer_user = CustomUser.objects.create_user(
            mobile_number="09120008903",
            email="customer-bale-final@example.com",
            name="علی",
            family="مشتری",
            password="pass12345",
        )
        self.manager = SalonManager.objects.create(user=self.manager_user, is_active=True)
        self.stylist = Stylist.objects.create(
            user=self.stylist_user,
            expert="رنگ و لایت",
            is_active=True,
        )
        self.customer = Customer.objects.create(user=self.customer_user)
        self.salon = Salon.objects.create(
            salon_name="سالن تست نهایی بله",
            salon_manager=self.manager,
            is_active=True,
        )
        self.service = Services.objects.create(
            service_name="رنگ ریشه",
            is_active=True,
            duration_minutes=60,
            base_price=450000,
        )
        self.salon.services.add(self.service)
        self.salon.stylists.add(self.stylist)
        self.service.stylists.add(self.stylist)
        SalonMembership.objects.create(
            salon=self.salon,
            stylist=self.stylist,
            status=SalonMembershipStatus.ACTIVE,
        )

        self.stylist_identity, _ = get_or_create_identity(
            provider=self.bale,
            provider_user_id="bale-stylist-final",
            chat_id="chat-stylist-final",
        )
        connect_identity_to_user(self.stylist_identity, self.stylist_user)
        self.stylist_identity.refresh_from_db()

    def _appointment(self, *, order_status="confirmed", is_paid=False):
        order = Order.objects.create(
            customer=self.customer,
            salon=self.salon,
            status=order_status,
            selected_payment_method="pay_in_salon",
            is_finally=True,
            is_paid=is_paid,
            subtotal_amount=450000,
            total_amount=450000,
        )
        detail = OrderDetail.objects.create(
            order=order,
            salon=self.salon,
            service=self.service,
            stylist=self.stylist,
            date=timezone.localdate(),
            time=time(16, 0),
            end_time=time(17, 0),
            scheduled_duration_minutes=60,
            price=450000,
            confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED,
        )
        return order, detail

    def test_stylist_menu_uses_current_lifecycle_language(self):
        self._appointment()
        from apps.bale_bot.menus import stylist_menu_text

        role = detect_user_bot_roles(self.stylist_user).get_role(BotRoleKey.STYLIST)
        text = stylist_menu_text(self.stylist_user, role)

        self.assertIn("آماده شروع", text)
        self.assertNotIn("منتظر تأیید", text)

    def test_no_show_pending_exposes_only_completion_decision(self):
        _, detail = self._appointment()
        detail.no_show_pending_at = timezone.now()
        detail.save(update_fields=["no_show_pending_at"])

        from .stylist_bot import render_stylist_today

        _, markup = render_stylist_today(
            self.stylist_user,
            "https://staging.loomera.ir",
            provider=self.bale,
            identity=self.stylist_identity,
        )
        labels = [button["text"] for row in markup["inline_keyboard"] for button in row]

        self.assertTrue(any("تکمیل عدم حضور" in label for label in labels))
        self.assertFalse(any("شروع خدمت" in label for label in labels))
        self.assertFalse(any("امکان انجام ندارم" in label for label in labels))

    def test_completed_pay_in_salon_stays_visible_until_cash_is_recorded(self):
        order, detail = self._appointment(order_status="completed")
        now = timezone.now()
        order.service_completed_at = now
        order.save(update_fields=["service_completed_at", "update_date"])
        detail.service_started_at = now
        detail.service_completed_at = now
        detail.save(update_fields=["service_started_at", "service_completed_at"])

        from .stylist_bot import render_stylist_today

        text, markup = render_stylist_today(
            self.stylist_user,
            "https://staging.loomera.ir",
            provider=self.bale,
            identity=self.stylist_identity,
        )
        labels = [button["text"] for row in markup["inline_keyboard"] for button in row]

        self.assertIn("منتظر ثبت دریافت وجه", text)
        self.assertTrue(any("دریافت وجه" in label for label in labels))

    def test_manager_summary_has_operational_state_not_legacy_confirmation(self):
        self._appointment()
        from .manager_bot import render_manager_today_summary

        text, _ = render_manager_today_summary(
            self.manager_user,
            "https://staging.loomera.ir",
            salon_id=self.salon.pk,
        )

        self.assertIn("آماده شروع", text)
        self.assertIn("نیازمند پیگیری عملیاتی", text)
        self.assertNotIn("منتظر تأیید متخصص", text)

    def test_staff_review_notification_is_queued_for_stylist_on_bale(self):
        leave = StaffLeaveRequest.objects.create(
            salon=self.salon,
            stylist=self.stylist,
            date=timezone.localdate(),
            reason="کار شخصی",
            status=StaffLeaveRequest.Status.APPROVED,
        )
        notification = create_notification(
            event_type="staff_leave_reviewed",
            category=NotificationCategory.STAFF,
            priority=NotificationPriority.HIGH,
            title="درخواست مرخصی شما تأیید شد",
            body="درخواست مرخصی بررسی شد.",
            recipients=[
                {
                    "user": self.stylist_user,
                    "audience_role": NotificationAudienceRole.STYLIST,
                    "channels": [NotificationChannel.DASHBOARD],
                }
            ],
            salon=self.salon,
            related_object=leave,
        )

        delivery = NotificationDelivery.objects.filter(
            recipient__notification=notification,
            recipient__user=self.stylist_user,
            channel=NotificationChannel.BALE,
        ).first()
        self.assertIsNotNone(delivery)
        self.assertTrue(notification.metadata.get("messaging_stylist_simple"))
        text = render_simple_notification_text(delivery)
        self.assertIn("درخواست مرخصی شما تأیید شد", text)
        self.assertIn("سالن تست نهایی بله", text)

    def test_booking_created_queues_customer_bale_with_useful_details(self):
        order, _ = self._appointment()

        notify_manager_and_stylists_for_booking(order, event_type="booking_created")

        delivery = (
            NotificationDelivery.objects.select_related("recipient__notification")
            .filter(
                recipient__user=self.customer_user,
                recipient__audience_role=NotificationAudienceRole.CUSTOMER,
                recipient__notification__event_type="booking_created",
                channel=NotificationChannel.BALE,
            )
            .order_by("-id")
            .first()
        )
        self.assertIsNotNone(delivery)
        text = render_simple_notification_text(delivery)
        self.assertIn("سالن تست نهایی بله", text)
        self.assertIn("رنگ ریشه", text)
        self.assertIn("پرداخت", text)
