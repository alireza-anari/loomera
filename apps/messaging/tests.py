from datetime import timedelta

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser, Customer, SalonManager, Stylist
from apps.notifications.models import (
    Notification,
    NotificationAudienceRole,
    NotificationChannel,
    NotificationCategory,
    NotificationDelivery,
    NotificationDeliveryAttempt,
    NotificationDeliveryStatus,
    NotificationRecipient,
    NotificationPreference,
)

from apps.notifications.delivery import deliver, process_queued_deliveries

from .constants import (
    MessagingMessageStatus,
    MessagingProviderKey,
    MessagingTokenPurpose,
)
from .models import (
    MessagingIdentity,
    MessagingMessageLog,
    MessagingToken,
    MessagingWebhookEvent,
)
from .roles import BotRoleKey, detect_user_bot_roles
from .services import (
    connect_identity_to_user,
    consume_token,
    ensure_default_providers,
    get_or_create_identity,
    issue_messaging_token,
    messaging_outbound_enabled,
    record_webhook_event,
)


class MessagingInfrastructureTests(TestCase):
    def setUp(self):
        self.providers = ensure_default_providers()
        self.bale = self.providers[MessagingProviderKey.BALE]
        self.user = CustomUser.objects.create_user(
            mobile_number="09120000001",
            email="user@example.com",
            name="کاربر",
            family="تست",
            password="pass",
        )

    def test_guest_identity_can_be_created_without_user(self):
        identity, created = get_or_create_identity(
            provider=self.bale,
            provider_user_id="bale-user-1",
            chat_id="chat-1",
            display_name="مهمان تست",
        )

        self.assertTrue(created)
        self.assertIsNone(identity.user)
        self.assertEqual(identity.provider, self.bale)
        self.assertEqual(identity.chat_id, "chat-1")

    def test_identity_can_be_connected_to_registered_user(self):
        identity, _ = get_or_create_identity(
            provider=self.bale,
            provider_user_id="bale-user-2",
            chat_id="chat-2",
        )

        connection = connect_identity_to_user(identity, self.user)
        identity.refresh_from_db()

        self.assertEqual(identity.user, self.user)
        self.assertEqual(connection.user, self.user)
        self.assertEqual(connection.identity, identity)

    def test_raw_token_is_not_stored_and_can_be_consumed_once(self):
        identity, _ = get_or_create_identity(
            provider=self.bale,
            provider_user_id="bale-user-3",
            chat_id="chat-3",
        )
        raw_token, token = issue_messaging_token(
            purpose=MessagingTokenPurpose.ACTION,
            provider=self.bale,
            identity=identity,
            user=self.user,
            action_key="appointment.confirm",
            expires_in=timedelta(minutes=10),
        )

        self.assertNotEqual(token.token_hash, raw_token)
        self.assertEqual(token.token_prefix, raw_token[:12])
        consumed = consume_token(raw_token, purpose=MessagingTokenPurpose.ACTION)
        self.assertEqual(consumed.pk, token.pk)

        with self.assertRaises(ValueError):
            consume_token(raw_token, purpose=MessagingTokenPurpose.ACTION)

    def test_expired_token_is_rejected(self):
        raw_token, token = issue_messaging_token(
            purpose=MessagingTokenPurpose.CONNECT_ACCOUNT,
            provider=self.bale,
            user=self.user,
            expires_in=timedelta(seconds=-1),
        )
        self.assertTrue(token.is_expired)
        with self.assertRaises(ValueError):
            consume_token(raw_token, purpose=MessagingTokenPurpose.CONNECT_ACCOUNT)

    def test_duplicate_webhook_event_does_not_create_second_row(self):
        first_event, first_created = record_webhook_event(
            provider=self.bale,
            event_id="evt-1",
            update_id="upd-1",
            event_type="message",
            payload={"text": "/start"},
        )
        second_event, second_created = record_webhook_event(
            provider=self.bale,
            event_id="evt-1",
            update_id="upd-1",
            event_type="message",
            payload={"text": "/start"},
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first_event.pk, second_event.pk)
        self.assertEqual(MessagingWebhookEvent.objects.count(), 1)

    def test_bale_notification_delivery_can_be_queued_without_real_send(self):
        notification = Notification.objects.create(
            event_type="messaging.test",
            title="تست بله",
            body="بدون ارسال واقعی",
        )
        recipient = NotificationRecipient.objects.create(
            notification=notification,
            user=self.user,
            audience_role=NotificationAudienceRole.CUSTOMER,
        )
        delivery = NotificationDelivery.objects.create(
            recipient=recipient,
            channel=NotificationChannel.BALE,
        )

        self.assertEqual(delivery.channel, "bale")
        self.assertEqual(delivery.status, "queued")

    @override_settings(MESSAGING_OUTBOUND_ENABLED=False)
    def test_outbound_feature_flag_is_disabled_by_default(self):
        self.assertFalse(messaging_outbound_enabled())
        self.assertFalse(getattr(settings, "MESSAGING_OUTBOUND_ENABLED", False))


class MessagingConnectionViewsStage3Tests(TestCase):
    def setUp(self):
        self.providers = ensure_default_providers()
        self.bale = self.providers[MessagingProviderKey.BALE]
        self.bale.is_active = True
        self.bale.save(update_fields=["is_active"])
        self.user = CustomUser.objects.create_user(
            mobile_number="09120000041",
            email="view@example.com",
            name="کاربر",
            family="وب",
            password="pass12345",
        )
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])

    def _login(self):
        self.assertTrue(
            self.client.login(mobile_number="09120000041", password="pass12345")
        )

    def test_status_page_requires_login(self):
        response = self.client.get("/messaging/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    @override_settings(
        MESSAGING_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        MESSAGING_CONNECT_TOKEN_TTL_MINUTES=15,
        BALE_BOT_USERNAME="loomera_test_bot",
    )
    def test_status_page_can_issue_one_time_connect_token(self):
        self._login()
        response = self.client.post(reverse("messaging:status"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            MessagingToken.objects.filter(
                purpose=MessagingTokenPurpose.CONNECT_ACCOUNT, user=self.user
            ).count(),
            1,
        )
        token = MessagingToken.objects.get(
            user=self.user, purpose=MessagingTokenPurpose.CONNECT_ACCOUNT
        )
        self.assertEqual(token.provider, self.bale)
        self.assertContains(response, "connect_")
        self.assertContains(response, "loomera_test_bot")

    @override_settings(MESSAGING_ENABLED=False, MESSAGING_ALLOWED_PROVIDERS=[])
    def test_status_page_does_not_issue_token_when_feature_is_disabled(self):
        self._login()
        response = self.client.post(reverse("messaging:status"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            MessagingToken.objects.filter(
                purpose=MessagingTokenPurpose.CONNECT_ACCOUNT, user=self.user
            ).exists()
        )

    def test_disconnect_only_disconnects_current_users_identity(self):
        self._login()
        identity, _ = get_or_create_identity(
            provider=self.bale, provider_user_id="view-user", chat_id="view-chat"
        )
        connect_identity_to_user(identity, self.user)

        response = self.client.post(
            reverse("messaging:disconnect", kwargs={"identity_id": identity.id})
        )

        self.assertEqual(response.status_code, 302)
        identity.refresh_from_db()
        self.assertEqual(identity.status, "disconnected")


class MessagingRoleDetectionStage4Tests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            mobile_number="09120000401",
            email="roles@example.com",
            name="نقش",
            family="چندگانه",
            password="pass12345",
        )

    def test_user_without_profile_has_no_bot_roles(self):
        context = detect_user_bot_roles(self.user)

        self.assertFalse(context.has_roles)
        self.assertEqual(context.roles, ())

    def test_customer_stylist_manager_roles_are_detected_from_real_models(self):
        Customer.objects.create(user=self.user)
        Stylist.objects.create(user=self.user, expert="پوست", is_active=True)
        SalonManager.objects.create(user=self.user, is_active=True)

        context = detect_user_bot_roles(self.user)

        self.assertTrue(context.is_multi_role)
        self.assertEqual(
            [role.key for role in context.roles],
            [BotRoleKey.CUSTOMER, BotRoleKey.STYLIST, BotRoleKey.MANAGER],
        )
        self.assertTrue(context.has_role(BotRoleKey.CUSTOMER))
        self.assertTrue(context.has_role(BotRoleKey.STYLIST))
        self.assertTrue(context.has_role(BotRoleKey.MANAGER))


class MessagingNotificationDeliveryStage5Tests(TestCase):
    def setUp(self):
        self.providers = ensure_default_providers()
        self.bale = self.providers[MessagingProviderKey.BALE]
        self.bale.is_active = True
        self.bale.save(update_fields=["is_active"])
        self.user = CustomUser.objects.create_user(
            mobile_number="09120000501",
            email="stage5@example.com",
            name="اعلان",
            family="بله",
            password="pass12345",
        )

    def _make_bale_delivery(self):
        notification = Notification.objects.create(
            event_type="messaging.stage5",
            title="یادآوری نوبت",
            body="فردا ساعت ۱۰ یک نوبت دارید.",
            action_url="/orders/1/",
        )
        recipient = NotificationRecipient.objects.create(
            notification=notification,
            user=self.user,
            audience_role=NotificationAudienceRole.CUSTOMER,
        )
        return NotificationDelivery.objects.create(
            recipient=recipient,
            channel=NotificationChannel.BALE,
        )

    def _connect_bale_identity(self):
        identity, _ = get_or_create_identity(
            provider=self.bale,
            provider_user_id="stage5-bale-user",
            chat_id="stage5-chat",
            display_name="کاربر مرحله پنج",
        )
        connect_identity_to_user(identity, self.user)
        return identity

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
    )
    def test_bale_delivery_is_logged_as_skipped_when_outbound_flag_is_off(self):
        identity = self._connect_bale_identity()
        delivery = self._make_bale_delivery()

        delivered = deliver(delivery)

        self.assertEqual(delivered.status, NotificationDeliveryStatus.SKIPPED)
        self.assertEqual(delivered.provider, MessagingProviderKey.BALE)
        self.assertEqual(delivered.attempt_count, 1)
        attempt = NotificationDeliveryAttempt.objects.get(delivery=delivered)
        self.assertEqual(attempt.status, NotificationDeliveryStatus.SKIPPED)
        self.assertEqual(attempt.provider_response["identity_id"], identity.pk)

        log = MessagingMessageLog.objects.get(notification_delivery=delivered)
        self.assertEqual(log.status, MessagingMessageStatus.SKIPPED)
        self.assertEqual(log.identity, identity)
        self.assertIn("یادآوری نوبت", log.text)
        self.assertIn(delivery.recipient.notification.action_url, log.text)
        self.assertNotIn("reply_markup", log.payload)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
    )
    def test_bale_delivery_without_connected_identity_needs_setup(self):
        delivery = self._make_bale_delivery()

        delivered = deliver(delivery)

        self.assertEqual(delivered.status, NotificationDeliveryStatus.PENDING_SETUP)
        attempt = NotificationDeliveryAttempt.objects.get(delivery=delivered)
        self.assertEqual(attempt.error_message, "missing_linked_messaging_identity")
        self.assertEqual(MessagingMessageLog.objects.count(), 0)

    @override_settings(
        MESSAGING_ENABLED=False, BALE_BOT_ENABLED=False, MESSAGING_ALLOWED_PROVIDERS=[]
    )
    def test_process_queue_ignores_bale_delivery_when_messaging_feature_is_off(self):
        self._connect_bale_identity()
        delivery = self._make_bale_delivery()

        result = process_queued_deliveries()

        self.assertEqual(result["processed"], 0)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, NotificationDeliveryStatus.QUEUED)
        self.assertEqual(NotificationDeliveryAttempt.objects.count(), 0)
        self.assertEqual(MessagingMessageLog.objects.count(), 0)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
    )
    def test_process_queue_keeps_bale_delivery_queued_when_outbound_is_off(self):
        self._connect_bale_identity()
        delivery = self._make_bale_delivery()

        result = process_queued_deliveries()

        self.assertEqual(result["processed"], 0)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, NotificationDeliveryStatus.QUEUED)
        self.assertEqual(delivery.attempt_count, 0)
        self.assertEqual(
            MessagingMessageLog.objects.filter(notification_delivery=delivery).count(),
            0,
        )


class MessagingActionDispatcherStage6Tests(TestCase):
    def setUp(self):
        self.providers = ensure_default_providers()
        self.bale = self.providers[MessagingProviderKey.BALE]
        self.bale.is_active = True
        self.bale.save(update_fields=["is_active"])
        self.user = CustomUser.objects.create_user(
            mobile_number="09120000601",
            email="stage6@example.com",
            name="اکشن",
            family="امن",
            password="pass12345",
        )
        self.identity, _ = get_or_create_identity(
            provider=self.bale,
            provider_user_id="stage6-bale-user",
            chat_id="stage6-chat",
            display_name="اکشن امن",
        )
        connect_identity_to_user(self.identity, self.user)

    def _issue_ack_token(self, **kwargs):
        from apps.messaging.actions import issue_action_token

        return issue_action_token(
            provider=self.bale,
            identity=self.identity,
            user=self.user,
            action_key="messaging.acknowledge",
            **kwargs,
        )

    def test_action_callback_executes_once_and_consumes_token(self):
        from apps.messaging.actions import (
            build_action_callback_data,
            dispatch_messaging_action_callback,
        )
        from apps.messaging.constants import MessagingActionStatus
        from apps.messaging.models import MessagingActionExecution

        raw_token, token = self._issue_ack_token()

        result = dispatch_messaging_action_callback(
            provider=self.bale,
            identity=self.identity,
            callback_data=build_action_callback_data(raw_token),
        )

        self.assertEqual(result.status, MessagingActionStatus.SUCCEEDED)
        token.refresh_from_db()
        self.assertIsNotNone(token.used_at)
        execution = MessagingActionExecution.objects.get(token=token)
        self.assertEqual(execution.status, MessagingActionStatus.SUCCEEDED)

        second = dispatch_messaging_action_callback(
            provider=self.bale,
            identity=self.identity,
            callback_data=build_action_callback_data(raw_token),
        )
        self.assertEqual(second.status, MessagingActionStatus.ALREADY_USED)

    def test_action_token_rejects_wrong_identity_without_consuming_token(self):
        from apps.messaging.actions import (
            build_action_callback_data,
            dispatch_messaging_action_callback,
        )
        from apps.messaging.constants import MessagingActionStatus

        raw_token, token = self._issue_ack_token()
        other_user = CustomUser.objects.create_user(
            mobile_number="09120000602",
            email="wrong@example.com",
            name="کاربر",
            family="اشتباه",
            password="pass12345",
        )
        other_identity, _ = get_or_create_identity(
            provider=self.bale,
            provider_user_id="stage6-other-user",
            chat_id="stage6-other-chat",
        )
        connect_identity_to_user(other_identity, other_user)

        result = dispatch_messaging_action_callback(
            provider=self.bale,
            identity=other_identity,
            callback_data=build_action_callback_data(raw_token),
        )

        self.assertEqual(result.status, MessagingActionStatus.DENIED)
        self.assertIn("حساب بله دیگری", result.user_message)
        token.refresh_from_db()
        self.assertIsNone(token.used_at)

    def test_expired_action_token_is_rejected(self):
        from apps.messaging.actions import (
            build_action_callback_data,
            dispatch_messaging_action_callback,
        )
        from apps.messaging.constants import MessagingActionStatus

        raw_token, token = self._issue_ack_token(expires_in=timedelta(seconds=-1))

        result = dispatch_messaging_action_callback(
            provider=self.bale,
            identity=self.identity,
            callback_data=build_action_callback_data(raw_token),
        )

        self.assertEqual(result.status, MessagingActionStatus.EXPIRED)
        token.refresh_from_db()
        self.assertIsNone(token.used_at)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
    )
    def test_actionable_notification_creates_masked_callback_button_and_token(self):
        notification = Notification.objects.create(
            event_type="messaging.stage6.actionable",
            title="اعلان قابل اقدام",
            body="برای تست ریل امن روی دکمه بزنید.",
            metadata={
                "messaging_actions": [
                    {
                        "type": "action",
                        "key": "messaging.acknowledge",
                        "label": "دریافت شد",
                    },
                    {
                        "type": "url",
                        "label": "مشاهده سایت",
                        "url": "https://example.com/view",
                    },
                ]
            },
        )
        recipient = NotificationRecipient.objects.create(
            notification=notification,
            user=self.user,
            audience_role=NotificationAudienceRole.CUSTOMER,
        )
        delivery = NotificationDelivery.objects.create(
            recipient=recipient, channel=NotificationChannel.BALE
        )

        delivered = deliver(delivery)

        self.assertEqual(delivered.status, NotificationDeliveryStatus.SKIPPED)
        self.assertEqual(
            MessagingToken.objects.filter(
                purpose=MessagingTokenPurpose.ACTION, user=self.user
            ).count(),
            1,
        )
        log = MessagingMessageLog.objects.get(notification_delivery=delivered)
        markup = log.payload.get("reply_markup", {})
        flat_buttons = [
            button for row in markup.get("inline_keyboard", []) for button in row
        ]
        action_button = next(
            button for button in flat_buttons if button.get("text") == "دریافت شد"
        )
        self.assertTrue(action_button["callback_data"].startswith("action:"))
        self.assertIn("…", action_button["callback_data"])
        self.assertNotIn(
            MessagingToken.objects.get(purpose=MessagingTokenPurpose.ACTION).token_hash,
            str(markup),
        )


class MessagingStage7StylistActionTests(TestCase):
    def test_stage7_stylist_action_handlers_are_registered(self):
        from apps.messaging.actions import get_messaging_action_handler
        from apps.messaging.stylist_actions import (
            ACTION_COMPLETE_SERVICE,
            ACTION_CONFIRM_APPOINTMENT,
            ACTION_REJECT_APPOINTMENT,
            ACTION_START_SERVICE,
        )

        self.assertIsNotNone(get_messaging_action_handler(ACTION_CONFIRM_APPOINTMENT))
        self.assertIsNotNone(get_messaging_action_handler(ACTION_REJECT_APPOINTMENT))
        self.assertIsNotNone(get_messaging_action_handler(ACTION_START_SERVICE))
        self.assertIsNotNone(get_messaging_action_handler(ACTION_COMPLETE_SERVICE))

    def test_stage7_stylist_menu_uses_safe_view_callbacks(self):
        from apps.bale_bot.menus import stylist_menu

        markup = stylist_menu("https://loomera.test")
        flat_buttons = [button for row in markup["inline_keyboard"] for button in row]
        callback_values = {
            button.get("callback_data")
            for button in flat_buttons
            if button.get("callback_data")
        }

        self.assertIn("menu:stylist_today", callback_values)
        self.assertIn("menu:stylist_slots", callback_values)
        self.assertIn("menu:stylist_booking_link", callback_values)


class MessagingStage8ManagerActionTests(TestCase):
    def test_stage8_manager_action_handlers_are_registered(self):
        from apps.messaging.actions import get_messaging_action_handler
        from apps.messaging.manager_actions import (
            ACTION_MANAGER_AVAILABLE_SLOTS,
            ACTION_MANAGER_LEAVE_APPROVE,
            ACTION_MANAGER_LEAVE_REJECT,
            ACTION_MANAGER_MEMBERSHIP_ACCEPT,
            ACTION_MANAGER_MEMBERSHIP_REJECT,
            ACTION_MANAGER_PENDING_REQUESTS,
            ACTION_MANAGER_SCHEDULE_APPROVE,
            ACTION_MANAGER_SCHEDULE_REJECT,
            ACTION_MANAGER_SHIFTS_OVERVIEW,
            ACTION_MANAGER_TODAY_CALENDAR,
            ACTION_MANAGER_TODAY_SUMMARY,
        )

        for action_key in [
            ACTION_MANAGER_MEMBERSHIP_ACCEPT,
            ACTION_MANAGER_MEMBERSHIP_REJECT,
            ACTION_MANAGER_LEAVE_APPROVE,
            ACTION_MANAGER_LEAVE_REJECT,
            ACTION_MANAGER_SCHEDULE_APPROVE,
            ACTION_MANAGER_SCHEDULE_REJECT,
            ACTION_MANAGER_SHIFTS_OVERVIEW,
            ACTION_MANAGER_TODAY_CALENDAR,
            ACTION_MANAGER_TODAY_SUMMARY,
            ACTION_MANAGER_AVAILABLE_SLOTS,
            ACTION_MANAGER_PENDING_REQUESTS,
        ]:
            self.assertIsNotNone(get_messaging_action_handler(action_key), action_key)

    def test_stage8_manager_menu_uses_safe_view_callbacks(self):
        from apps.bale_bot.menus import manager_menu

        markup = manager_menu("https://loomera.test")
        flat_buttons = [button for row in markup["inline_keyboard"] for button in row]
        callback_values = {
            button.get("callback_data")
            for button in flat_buttons
            if button.get("callback_data")
        }

        self.assertIn("menu:manager_today", callback_values)
        self.assertIn("menu:manager_summary", callback_values)
        self.assertIn("menu:manager_shifts", callback_values)
        self.assertIn("menu:manager_slots", callback_values)
        self.assertIn("menu:manager_requests", callback_values)


class MessagingCustomerBotStage9Tests(TestCase):
    def setUp(self):
        self.manager_user = CustomUser.objects.create_user(
            mobile_number="09120909001",
            email="manager-stage9@example.com",
            name="مدیر",
            family="مشتری",
            password="pass12345",
        )
        self.customer_user = CustomUser.objects.create_user(
            mobile_number="09120909002",
            email="customer-stage9@example.com",
            name="مشتری",
            family="مرحله۹",
            password="pass12345",
        )
        self.stylist_user = CustomUser.objects.create_user(
            mobile_number="09120909003",
            email="stylist-stage9@example.com",
            name="متخصص",
            family="مرحله۹",
            password="pass12345",
        )
        self.manager = SalonManager.objects.create(
            user=self.manager_user, is_active=True
        )
        self.customer = Customer.objects.create(user=self.customer_user)
        self.stylist = Stylist.objects.create(
            user=self.stylist_user, expert="پوست", is_active=True
        )

        from apps.salons.models import Salon
        from apps.services.models import Services

        self.service = Services.objects.create(
            service_name="پاکسازی پوست",
            is_active=True,
            duration_minutes=30,
            base_price=100000,
        )
        self.salon = Salon.objects.create(
            salon_name="سالن مرحله نه",
            salon_manager=self.manager,
            is_active=True,
            address="تهران",
        )
        self.salon.services.add(self.service)
        self.salon.stylists.add(self.stylist)
        self.service.stylists.add(self.stylist)

    def test_customer_salon_search_renders_active_salon_card(self):
        from apps.messaging.customer_bot import render_customer_salon_search

        text, markup = render_customer_salon_search(
            self.customer_user, "https://loomera.test", query="مرحله"
        )

        self.assertIn("سالن مرحله نه", text)
        self.assertIn("خدمات شاخص", text)
        self.assertIn("رزرو", str(markup))

    def test_customer_appointments_renders_payment_and_status_without_mutation(self):
        from apps.messaging.customer_bot import render_customer_appointments
        from apps.orders.models import Order, OrderDetail

        order = Order.objects.create(
            customer=self.customer,
            salon=self.salon,
            status="confirmed",
            selected_payment_method="pay_in_salon",
            is_finally=True,
        )
        OrderDetail.objects.create(
            order=order,
            salon=self.salon,
            service=self.service,
            stylist=self.stylist,
            date=timezone.localdate() + timedelta(days=1),
            time=timezone.localtime(timezone.now()).time(),
            end_time=timezone.localtime(timezone.now()).time(),
            price=100000,
        )

        text, markup = render_customer_appointments(
            self.customer_user, "https://loomera.test"
        )

        self.assertIn("نوبت‌های آینده", text)
        self.assertIn("پرداخت در سالن", text)
        self.assertIn("جزئیات نوبت", str(markup))

    def test_customer_booking_notification_queues_simple_bale_delivery(self):
        from apps.notifications.services import create_notification

        notification = create_notification(
            event_type="appointment_confirmed_customer",
            title="نوبت تایید شد",
            body="نوبت شما تایید شد.",
            recipients=[
                {
                    "user": self.customer_user,
                    "audience_role": NotificationAudienceRole.CUSTOMER,
                }
            ],
            category=NotificationCategory.BOOKING,
            channels=[NotificationChannel.DASHBOARD],
        )

        self.assertTrue(notification.metadata.get("messaging_customer_simple"))
        recipient = NotificationRecipient.objects.get(
            notification=notification, user=self.customer_user
        )
        self.assertTrue(
            NotificationDelivery.objects.filter(
                recipient=recipient, channel=NotificationChannel.BALE
            ).exists()
        )
        self.assertFalse(notification.metadata.get("messaging_actions"))


class MessagingPromotionStage10Tests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            mobile_number="09120001001",
            email="promo@example.com",
            name="پرومو",
            family="متخصص",
            password="pass12345",
        )
        self.stylist = Stylist.objects.create(
            user=self.user, expert="پوست", is_active=True
        )
        self.manager_user = CustomUser.objects.create_user(
            mobile_number="09120001002",
            email="manager-promo@example.com",
            name="مدیر",
            family="پرومو",
            password="pass12345",
        )
        self.manager = SalonManager.objects.create(
            user=self.manager_user, is_active=True
        )

        from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus
        from apps.services.models import Services

        self.salon = Salon.objects.create(
            salon_name="سالن پرومو",
            salon_manager=self.manager,
            is_active=True,
        )
        self.service = Services.objects.create(
            service_name="پاکسازی پوست", is_active=True, duration_minutes=30
        )
        self.salon.services.add(self.service)
        self.salon.stylists.add(self.stylist)
        self.service.stylists.add(self.stylist)
        SalonMembership.objects.create(
            salon=self.salon,
            stylist=self.stylist,
            status=SalonMembershipStatus.ACTIVE,
        )

    def test_stylist_promotion_pack_creates_manual_story_text_and_booking_link(self):
        from apps.messaging.promotion_bot import render_stylist_promotion_pack
        from apps.orders.models import BookingQuickLink

        text, markup = render_stylist_promotion_pack(self.user, "https://example.test")

        self.assertIn("تبلیغ و لینک رزرو متخصص", text)
        self.assertIn("متن آماده استوری", text)
        self.assertIn("انتشار خودکار استوری", text)
        self.assertTrue(
            BookingQuickLink.objects.filter(
                creator=self.user,
                stylist=self.stylist,
                mode=BookingQuickLink.Mode.STYLIST,
            ).exists()
        )
        self.assertTrue(markup["inline_keyboard"])

    def test_manager_promotion_pack_uses_salon_url_and_service_booking_link(self):
        from apps.messaging.promotion_bot import render_manager_promotion_pack
        from apps.orders.models import BookingQuickLink

        text, markup = render_manager_promotion_pack(
            self.manager_user, "https://example.test"
        )

        self.assertIn("تبلیغ سالن", text)
        self.assertIn("متن آماده استوری سالن", text)
        self.assertIn("انتشار خودکار استوری", text)
        self.assertTrue(
            BookingQuickLink.objects.filter(
                creator=self.manager_user,
                salon=self.salon,
                service=self.service,
                mode=BookingQuickLink.Mode.SERVICE,
            ).exists()
        )
        self.assertTrue(markup["inline_keyboard"])


class MessagingPrivacyPreferencesStage11Tests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            mobile_number="09120001101",
            email="privacy-stage11@example.com",
            name="حریم",
            family="خصوصی",
            password="pass12345",
        )
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])

        self.customer = Customer.objects.create(user=self.user)
        self.providers = ensure_default_providers()
        self.bale = self.providers[MessagingProviderKey.BALE]

    def test_preferences_helper_separates_operational_and_marketing_streams(self):
        from apps.messaging.preferences import (
            STREAM_MARKETING,
            STREAM_OPERATIONAL,
            set_stream_enabled,
            stream_enabled,
        )

        set_stream_enabled(
            user=self.user,
            channel=NotificationChannel.BALE,
            stream=STREAM_MARKETING,
            enabled=False,
        )
        self.assertFalse(
            stream_enabled(
                user=self.user,
                channel=NotificationChannel.BALE,
                stream=STREAM_MARKETING,
            )
        )
        self.assertTrue(
            stream_enabled(
                user=self.user,
                channel=NotificationChannel.BALE,
                stream=STREAM_OPERATIONAL,
            )
        )

    def test_queued_messaging_delivery_respects_latest_user_preference(self):
        from apps.messaging.notification_delivery import (
            messaging_delivery_preference_enabled,
        )
        from apps.messaging.preferences import STREAM_MARKETING, set_stream_enabled
        from apps.notifications.services import create_notification

        notification = create_notification(
            event_type="marketing_campaign_stage11",
            title="پیشنهاد ویژه",
            body="متن تبلیغاتی",
            recipients=[
                {
                    "user": self.user,
                    "audience_role": NotificationAudienceRole.CUSTOMER,
                    "channels": [NotificationChannel.BALE],
                }
            ],
            category=NotificationCategory.MARKETING,
            channels=[NotificationChannel.BALE],
        )
        recipient = NotificationRecipient.objects.get(
            notification=notification, user=self.user
        )
        delivery = NotificationDelivery.objects.get(
            recipient=recipient, channel=NotificationChannel.BALE
        )

        self.assertTrue(messaging_delivery_preference_enabled(delivery))
        set_stream_enabled(
            user=self.user,
            channel=NotificationChannel.BALE,
            stream=STREAM_MARKETING,
            enabled=False,
        )
        self.assertFalse(messaging_delivery_preference_enabled(delivery))

    def test_critical_messaging_delivery_ignores_opt_out(self):
        from apps.messaging.notification_delivery import (
            messaging_delivery_preference_enabled,
        )
        from apps.messaging.preferences import STREAM_OPERATIONAL, set_stream_enabled
        from apps.notifications.services import create_notification

        set_stream_enabled(
            user=self.user,
            channel=NotificationChannel.BALE,
            stream=STREAM_OPERATIONAL,
            enabled=False,
        )
        notification = create_notification(
            event_type="security_critical_stage11",
            title="پیام امنیتی",
            body="برای امنیت حساب",
            recipients=[
                {
                    "user": self.user,
                    "audience_role": NotificationAudienceRole.CUSTOMER,
                    "channels": [NotificationChannel.BALE],
                }
            ],
            category=NotificationCategory.SYSTEM,
            priority="critical",
            channels=[NotificationChannel.BALE],
        )
        recipient = NotificationRecipient.objects.get(
            notification=notification, user=self.user
        )
        delivery = NotificationDelivery.objects.get(
            recipient=recipient, channel=NotificationChannel.BALE
        )

        self.assertTrue(messaging_delivery_preference_enabled(delivery))

    def test_preferences_page_writes_unified_notification_preferences(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("messaging:preferences"),
            {
                "audience_role": "",
                "bale_operational": "1",
                "telegram_operational": "1",
                "whatsapp_operational": "1",
                "rubika_operational": "1",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            NotificationPreference.objects.filter(
                user=self.user,
                channel=NotificationChannel.BALE,
                category=NotificationCategory.BOOKING,
                is_enabled=True,
            ).exists()
        )

        self.assertTrue(
            NotificationPreference.objects.filter(
                user=self.user,
                channel=NotificationChannel.BALE,
                category=NotificationCategory.MARKETING,
                is_enabled=False,
            ).exists()
        )

    def test_bale_menus_link_to_messaging_preferences_for_all_roles(self):
        from apps.bale_bot.menus import (
            customer_menu,
            manager_menu,
            quick_links_menu,
            role_selector_menu,
            stylist_menu,
        )
        from apps.messaging.roles import detect_user_bot_roles

        base_url = "https://loomera.test"
        context = detect_user_bot_roles(self.user)
        combined = " ".join(
            str(markup)
            for markup in [
                role_selector_menu(base_url, context),
                customer_menu(base_url),
                stylist_menu(base_url),
                manager_menu(base_url),
                quick_links_menu(base_url),
            ]
        )

        self.assertIn("/messaging/preferences/", combined)
        self.assertNotIn("/accounts/notification_settings/", combined)
