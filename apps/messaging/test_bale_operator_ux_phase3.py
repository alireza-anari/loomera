from datetime import time

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import CustomUser, Customer, SalonManager, Stylist
from apps.orders.models import Order, OrderDetail
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus
from apps.services.models import Services
from apps.stylists.models import StaffLeaveRequest

from .actions import (
    build_action_callback_data,
    dispatch_messaging_action_callback,
    issue_action_token,
)
from .constants import MessagingActionStatus, MessagingProviderKey, MessagingTokenPurpose
from .models import MessagingToken
from .services import connect_identity_to_user, ensure_default_providers, get_or_create_identity


@override_settings(MESSAGING_ACTIONS_ENABLED=True)
class BaleOperatorUxPhase3Tests(TestCase):
    def setUp(self):
        providers = ensure_default_providers()
        self.bale = providers[MessagingProviderKey.BALE]

        self.manager_user = CustomUser.objects.create_user(
            mobile_number="09120008901",
            email="manager-bale-ux3@example.com",
            name="مریم",
            family="مدیر",
            password="pass12345",
        )
        self.stylist_user = CustomUser.objects.create_user(
            mobile_number="09120008902",
            email="stylist-bale-ux3@example.com",
            name="سارا",
            family="متخصص",
            password="pass12345",
        )
        self.customer_user = CustomUser.objects.create_user(
            mobile_number="09120008903",
            email="customer-bale-ux3@example.com",
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
            salon_name="سالن اول",
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
            provider_user_id="bale-stylist-ux3",
            chat_id="chat-stylist-ux3",
        )
        connect_identity_to_user(self.stylist_identity, self.stylist_user)
        self.stylist_identity.refresh_from_db()

        self.manager_identity, _ = get_or_create_identity(
            provider=self.bale,
            provider_user_id="bale-manager-ux3",
            chat_id="chat-manager-ux3",
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

    def test_multi_salon_manager_gets_selector_and_scoped_callbacks(self):
        second = Salon.objects.create(
            salon_name="سالن دوم",
            salon_manager=self.manager,
            is_active=True,
        )

        from apps.bale_bot.menus import manager_menu, menu_for_role
        from .roles import detect_user_bot_roles

        text, markup = menu_for_role(
            "https://staging.loomera.ir", self.manager_user, "manager"
        )
        self.assertIn("کدام سالن", text)
        callbacks = {
            button.get("callback_data")
            for row in markup["inline_keyboard"]
            for button in row
            if button.get("callback_data")
        }
        self.assertIn(f"menu:manager_salon:{self.salon.pk}", callbacks)
        self.assertIn(f"menu:manager_salon:{second.pk}", callbacks)

        role = detect_user_bot_roles(self.manager_user).get_role("manager")
        scoped = manager_menu(
            "https://staging.loomera.ir", role, salon_id=self.salon.pk
        )
        scoped_callbacks = {
            button.get("callback_data")
            for row in scoped["inline_keyboard"]
            for button in row
            if button.get("callback_data")
        }
        self.assertIn(f"menu:manager_today:{self.salon.pk}", scoped_callbacks)
        self.assertIn(f"menu:manager_shifts:{self.salon.pk}", scoped_callbacks)

    def test_stylist_reject_preview_does_not_change_appointment(self):
        from .stylist_actions import (
            ACTION_REJECT_APPOINTMENT,
            ACTION_REJECT_APPOINTMENT_PREVIEW,
        )

        detail = self._appointment(
            confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED
        )
        raw_token, _ = issue_action_token(
            provider=self.bale,
            identity=self.stylist_identity,
            user=self.stylist_user,
            related_object=detail,
            action_key=ACTION_REJECT_APPOINTMENT_PREVIEW,
            audience_role="stylist",
            salon_id=self.salon.pk,
            metadata={"order_detail_id": detail.pk},
        )

        result = dispatch_messaging_action_callback(
            provider=self.bale,
            identity=self.stylist_identity,
            callback_data=build_action_callback_data(raw_token),
            base_url="https://staging.loomera.ir",
        )

        detail.refresh_from_db()
        self.assertEqual(result.status, MessagingActionStatus.SUCCEEDED)
        self.assertTrue(result.result.get("preview"))
        self.assertEqual(
            detail.confirmation_status, OrderDetail.ConfirmationStatus.CONFIRMED
        )
        self.assertIn("این نوبت لغو شود؟", result.user_message)
        self.assertTrue(
            MessagingToken.objects.filter(
                purpose=MessagingTokenPurpose.ACTION,
                user=self.stylist_user,
                action_key=ACTION_REJECT_APPOINTMENT,
                used_at__isnull=True,
            ).exists()
        )

    def test_manager_leave_preview_keeps_request_pending_and_shows_conflict(self):
        from .manager_actions import (
            ACTION_MANAGER_LEAVE_APPROVE,
            ACTION_MANAGER_LEAVE_APPROVE_PREVIEW,
        )

        self._appointment(
            confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED
        )
        leave = StaffLeaveRequest.objects.create(
            salon=self.salon,
            stylist=self.stylist,
            date=timezone.localdate(),
            start_time=time(15, 30),
            end_time=time(17, 30),
            reason="کار شخصی",
        )
        raw_token, _ = issue_action_token(
            provider=self.bale,
            identity=self.manager_identity,
            user=self.manager_user,
            related_object=leave,
            action_key=ACTION_MANAGER_LEAVE_APPROVE_PREVIEW,
            audience_role="manager",
            salon_id=self.salon.pk,
            metadata={"leave_request_id": leave.pk},
        )

        result = dispatch_messaging_action_callback(
            provider=self.bale,
            identity=self.manager_identity,
            callback_data=build_action_callback_data(raw_token),
            base_url="https://staging.loomera.ir",
        )

        leave.refresh_from_db()
        self.assertEqual(result.status, MessagingActionStatus.SUCCEEDED)
        self.assertTrue(result.result.get("preview"))
        self.assertEqual(leave.status, StaffLeaveRequest.Status.PENDING)
        self.assertIn("نوبت ثبت‌شده در این بازه: ۱", result.user_message)
        self.assertIn("تأیید این مرخصی؟", result.user_message)
        self.assertTrue(
            MessagingToken.objects.filter(
                purpose=MessagingTokenPurpose.ACTION,
                user=self.manager_user,
                action_key=ACTION_MANAGER_LEAVE_APPROVE,
                used_at__isnull=True,
            ).exists()
        )
