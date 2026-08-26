from datetime import time, timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import CustomUser, Customer, SalonManager, Stylist
from apps.notifications.models import (
    Notification,
    NotificationAudienceRole,
    NotificationChannel,
    NotificationDelivery,
    NotificationRecipient,
)
from apps.orders.models import Order, OrderDetail
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus
from apps.services.models import Services
from apps.stylists.models import StaffLeaveRequest

from .constants import MessagingProviderKey, MessagingTokenPurpose
from .models import MessagingToken
from .notification_delivery import render_simple_notification_text
from .services import connect_identity_to_user, ensure_default_providers, get_or_create_identity


@override_settings(MESSAGING_ACTIONS_ENABLED=True)
class BaleOperatorUxTests(TestCase):
    def setUp(self):
        providers = ensure_default_providers()
        self.bale = providers[MessagingProviderKey.BALE]

        self.manager_user = CustomUser.objects.create_user(
            mobile_number="09120009901",
            email="manager-bale-ux@example.com",
            name="مریم",
            family="مدیر",
            password="pass12345",
        )
        self.stylist_user = CustomUser.objects.create_user(
            mobile_number="09120009902",
            email="stylist-bale-ux@example.com",
            name="سارا",
            family="متخصص",
            password="pass12345",
        )
        self.customer_user = CustomUser.objects.create_user(
            mobile_number="09120009903",
            email="customer-bale-ux@example.com",
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
            salon_name="سالن تست Loomera",
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
            provider_user_id="bale-stylist-ux",
            chat_id="chat-stylist-ux",
        )
        connect_identity_to_user(self.stylist_identity, self.stylist_user)
        self.stylist_identity.refresh_from_db()

        self.manager_identity, _ = get_or_create_identity(
            provider=self.bale,
            provider_user_id="bale-manager-ux",
            chat_id="chat-manager-ux",
        )
        connect_identity_to_user(self.manager_identity, self.manager_user)
        self.manager_identity.refresh_from_db()

    def _appointment(self, *, confirmation_status=OrderDetail.ConfirmationStatus.PENDING):
        order = Order.objects.create(
            customer=self.customer,
            salon=self.salon,
            status="confirmed",
            selected_payment_method="pay_in_salon",
            is_finally=True,
        )
        return OrderDetail.objects.create(
            order=order,
            salon=self.salon,
            service=self.service,
            stylist=self.stylist,
            date=timezone.localdate(),
            time=time(16, 0),
            end_time=time(17, 0),
            scheduled_duration_minutes=60,
            price=450000,
            confirmation_status=confirmation_status,
        )

    def test_guest_menu_uses_quick_connect_flow(self):
        from apps.bale_bot.menus import guest_main_menu

        markup = guest_main_menu("https://staging.loomera.ir")
        buttons = [button for row in markup["inline_keyboard"] for button in row]
        connect = next(button for button in buttons if "وصل کردن حساب" in button["text"])
        self.assertIn("/messaging/connect/bale/", connect["url"])

    def test_stylist_today_shows_decision_data_and_action_buttons(self):
        from .stylist_bot import render_stylist_today

        self._appointment()
        text, markup = render_stylist_today(
            self.stylist_user,
            "https://staging.loomera.ir",
            provider=self.bale,
            identity=self.stylist_identity,
        )

        self.assertIn("علی مشتری", text)
        self.assertIn("رنگ ریشه", text)
        self.assertIn("۴۵۰,۰۰۰ تومان", text)
        buttons = [button for row in markup["inline_keyboard"] for button in row]
        self.assertTrue(any("تأیید نوبت" in button["text"] for button in buttons))
        self.assertTrue(any("رد نوبت" in button["text"] for button in buttons))
        self.assertGreaterEqual(
            MessagingToken.objects.filter(
                purpose=MessagingTokenPurpose.ACTION,
                user=self.stylist_user,
            ).count(),
            2,
        )

    def test_manager_leave_request_shows_booking_conflict_before_decision(self):
        self._appointment(confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED)
        StaffLeaveRequest.objects.create(
            salon=self.salon,
            stylist=self.stylist,
            date=timezone.localdate(),
            start_time=time(15, 30),
            end_time=time(17, 30),
            reason="کار شخصی",
        )

        from .manager_bot import render_manager_shifts_overview

        text, markup = render_manager_shifts_overview(
            self.manager_user,
            "https://staging.loomera.ir",
            provider=self.bale,
            identity=self.manager_identity,
        )

        self.assertIn("کار شخصی", text)
        self.assertIn("نوبت ثبت‌شده در این بازه: ۱", text)
        buttons = [button for row in markup["inline_keyboard"] for button in row]
        self.assertTrue(any("تأیید مرخصی" in button["text"] for button in buttons))
        self.assertTrue(any("رد مرخصی" in button["text"] for button in buttons))

    def test_stylist_notification_is_rendered_as_decision_card(self):
        detail = self._appointment()
        notification = Notification.objects.create(
            event_type="stylist_booking_pending",
            title="اعلان رزرو",
            body="یک رزرو جدید دارید.",
            related_object=detail,
            salon=self.salon,
        )
        recipient = NotificationRecipient.objects.create(
            notification=notification,
            user=self.stylist_user,
            audience_role=NotificationAudienceRole.STYLIST,
        )
        delivery = NotificationDelivery.objects.create(
            recipient=recipient,
            channel=NotificationChannel.BALE,
        )

        text = render_simple_notification_text(delivery)

        self.assertIn("نوبت جدید برای تأیید", text)
        self.assertIn("مشتری: علی مشتری", text)
        self.assertIn("خدمت: رنگ ریشه", text)
        self.assertNotIn("یک رزرو جدید دارید", text)
