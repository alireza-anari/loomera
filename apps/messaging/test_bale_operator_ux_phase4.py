from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import CustomUser, Customer, SalonManager, Stylist
from apps.notifications.models import (
    NotificationAudienceRole,
    NotificationChannel,
    NotificationDelivery,
)
from apps.orders.lifecycle import notify_manager_and_stylists_for_booking
from apps.orders.models import Order, OrderDetail
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus
from apps.services.models import Services

from .actions import (
    build_action_callback_data,
    dispatch_messaging_action_callback,
    issue_action_token,
)
from .constants import MessagingActionStatus, MessagingProviderKey
from .services import connect_identity_to_user, ensure_default_providers, get_or_create_identity


@override_settings(
    MESSAGING_ACTIONS_ENABLED=True,
    LOOMERA_SEND_NOTIFICATIONS_IMMEDIATELY=False,
)
class BaleOperatorUxPhase4Tests(TestCase):
    def setUp(self):
        providers = ensure_default_providers()
        self.bale = providers[MessagingProviderKey.BALE]

        self.manager_user = CustomUser.objects.create_user(
            mobile_number="09120007901",
            email="manager-bale-ux4@example.com",
            name="مریم",
            family="مدیر",
            password="pass12345",
        )
        self.stylist_user = CustomUser.objects.create_user(
            mobile_number="09120007902",
            email="stylist-bale-ux4@example.com",
            name="سارا",
            family="متخصص",
            password="pass12345",
        )
        self.customer_user = CustomUser.objects.create_user(
            mobile_number="09120007903",
            email="customer-bale-ux4@example.com",
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
            salon_name="سالن تست فاز چهار",
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

        self.identity, _ = get_or_create_identity(
            provider=self.bale,
            provider_user_id="bale-stylist-ux4",
            chat_id="chat-stylist-ux4",
        )
        connect_identity_to_user(self.identity, self.stylist_user)
        self.identity.refresh_from_db()

    def _appointment(self, *, date_value=None, confirmation_status=None):
        order = Order.objects.create(
            customer=self.customer,
            salon=self.salon,
            status="pending",
            selected_payment_method="pay_in_salon",
            is_finally=True,
        )
        detail = OrderDetail.objects.create(
            order=order,
            salon=self.salon,
            service=self.service,
            stylist=self.stylist,
            date=date_value or timezone.localdate(),
            time=time(16, 0),
            end_time=time(17, 0),
            scheduled_duration_minutes=60,
            price=450000,
            confirmation_status=(
                confirmation_status
                or OrderDetail.ConfirmationStatus.CONFIRMED
            ),
        )
        return order, detail

    def test_new_auto_confirmed_booking_queues_bale_for_stylist(self):
        order, detail = self._appointment(
            date_value=timezone.localdate() + timedelta(days=2)
        )

        notify_manager_and_stylists_for_booking(order, event_type="booking_created")

        delivery = (
            NotificationDelivery.objects.select_related(
                "recipient__notification",
                "recipient__user",
            )
            .filter(
                recipient__user=self.stylist_user,
                recipient__audience_role=NotificationAudienceRole.STYLIST,
                recipient__notification__event_type="booking_created",
                channel=NotificationChannel.BALE,
            )
            .order_by("-id")
            .first()
        )

        self.assertIsNotNone(delivery)
        metadata = delivery.recipient.notification.metadata or {}
        self.assertTrue(metadata.get("messaging_stylist_simple"))
        actions = metadata.get("messaging_actions") or []
        labels = {item.get("label") for item in actions}
        self.assertNotIn("تأیید نوبت", labels)
        self.assertIn("امکان انجام ندارم", labels)

    def test_today_menu_uses_start_and_cannot_perform_without_confirm(self):
        _, detail = self._appointment()

        from .stylist_bot import render_stylist_today

        fixed_now = timezone.make_aware(
            datetime.combine(timezone.localdate(), time(15, 0)),
            timezone.get_current_timezone(),
        )
        with patch("apps.messaging.stylist_actions.timezone.now", return_value=fixed_now):
            text, markup = render_stylist_today(
                self.stylist_user,
                "https://staging.loomera.ir",
                provider=self.bale,
                identity=self.identity,
            )

        self.assertIn("رنگ ریشه", text)
        buttons = [button for row in markup["inline_keyboard"] for button in row]
        labels = [button["text"] for button in buttons]
        self.assertFalse(any("تأیید نوبت" in label for label in labels))
        self.assertTrue(any("شروع خدمت" in label for label in labels))
        self.assertTrue(any("امکان انجام ندارم" in label for label in labels))

    def test_today_menu_switches_exception_to_no_show_after_threshold(self):
        _, detail = self._appointment()

        from .stylist_bot import render_stylist_today

        fixed_now = timezone.make_aware(
            datetime.combine(timezone.localdate(), time(17, 0)),
            timezone.get_current_timezone(),
        )
        with patch("apps.messaging.stylist_actions.timezone.now", return_value=fixed_now):
            text, markup = render_stylist_today(
                self.stylist_user,
                "https://staging.loomera.ir",
                provider=self.bale,
                identity=self.identity,
            )

        self.assertIn("رنگ ریشه", text)
        buttons = [button for row in markup["inline_keyboard"] for button in row]
        labels = [button["text"] for button in buttons]
        self.assertTrue(any("شروع خدمت" in label for label in labels))
        self.assertTrue(any("مشتری نیامد" in label for label in labels))
        self.assertFalse(any("امکان انجام ندارم" in label for label in labels))

    def test_cancel_preview_accepts_auto_confirmed_booking(self):
        _, detail = self._appointment()
        from .stylist_actions import ACTION_REJECT_APPOINTMENT_PREVIEW

        raw_token, _ = issue_action_token(
            provider=self.bale,
            identity=self.identity,
            user=self.stylist_user,
            related_object=detail,
            action_key=ACTION_REJECT_APPOINTMENT_PREVIEW,
            audience_role="stylist",
            salon_id=self.salon.pk,
            metadata={"order_detail_id": detail.pk},
        )

        result = dispatch_messaging_action_callback(
            provider=self.bale,
            identity=self.identity,
            callback_data=build_action_callback_data(raw_token),
            base_url="https://staging.loomera.ir",
        )

        detail.refresh_from_db()
        self.assertEqual(result.status, MessagingActionStatus.SUCCEEDED)
        self.assertEqual(
            detail.confirmation_status,
            OrderDetail.ConfirmationStatus.CONFIRMED,
        )
        self.assertIn("این نوبت لغو شود؟", result.user_message)

    def test_start_service_from_bale_implicitly_records_arrival(self):
        _, detail = self._appointment()
        from .stylist_actions import ACTION_START_SERVICE

        raw_token, _ = issue_action_token(
            provider=self.bale,
            identity=self.identity,
            user=self.stylist_user,
            related_object=detail,
            action_key=ACTION_START_SERVICE,
            audience_role="stylist",
            salon_id=self.salon.pk,
            metadata={"order_detail_id": detail.pk},
        )

        result = dispatch_messaging_action_callback(
            provider=self.bale,
            identity=self.identity,
            callback_data=build_action_callback_data(raw_token),
            base_url="https://staging.loomera.ir",
        )

        detail.refresh_from_db()
        self.assertEqual(result.status, MessagingActionStatus.SUCCEEDED)
        self.assertIsNotNone(detail.customer_arrived_at)
        self.assertIsNotNone(detail.service_started_at)
        self.assertIn("خدمت شروع شد", result.user_message)
