from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.main.models import AdminRoleAssignment, SupportTicket, SupportTicketMessage


class SupportTicketAccessSecurityTests(TestCase):
    def _user(self, *, mobile="09131000001", name="کاربر", family="تست"):
        return CustomUser.objects.create(
            mobile_number=mobile,
            name=name,
            family=family,
            is_active=True,
        )

    def _support_admin(self, *, mobile="09131000999"):
        user = self._user(mobile=mobile, name="ادمین", family="پشتیبانی")
        AdminRoleAssignment.objects.create(
            user=user,
            role=AdminRoleAssignment.Role.SUPPORT_ADMIN,
            is_active=True,
        )
        return user

    def _ticket(self, *, user, status="open", subject="تیکت تست"):
        return SupportTicket.objects.create(
            user=user,
            email=f"{user.mobile_number}@example.test",
            issue_type="other",
            support_reason="other",
            subject=subject,
            description="شرح تست",
            status=status,
            requester_role="customer",
        )

    def test_user_cannot_view_foreign_ticket(self):
        owner = self._user(mobile="09131000101")
        attacker = self._user(mobile="09131000102")
        ticket = self._ticket(user=owner)

        self.client.force_login(attacker)

        response = self.client.get(
            reverse("main:support_ticket_detail", kwargs={"pk": ticket.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_user_detail_hides_internal_messages(self):
        owner = self._user(mobile="09131000103")
        ticket = self._ticket(user=owner)

        SupportTicketMessage.objects.create(
            ticket=ticket,
            sender=owner,
            sender_role="customer",
            message_type=SupportTicketMessage.MESSAGE_TYPE_PUBLIC,
            body="پیام عمومی",
        )
        SupportTicketMessage.objects.create(
            ticket=ticket,
            sender=None,
            sender_role="support_admin",
            message_type=SupportTicketMessage.MESSAGE_TYPE_INTERNAL,
            body="یادداشت داخلی محرمانه",
        )

        self.client.force_login(owner)

        response = self.client.get(
            reverse("main:support_ticket_detail", kwargs={"pk": ticket.pk})
        )

        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("پیام عمومی", body)
        self.assertNotIn("یادداشت داخلی محرمانه", body)

    def test_user_cannot_reply_to_foreign_ticket(self):
        owner = self._user(mobile="09131000104")
        attacker = self._user(mobile="09131000105")
        ticket = self._ticket(user=owner)

        self.client.force_login(attacker)

        response = self.client.post(
            reverse("main:support_ticket_reply", kwargs={"pk": ticket.pk}),
            data={"body": "پیام غیرمجاز"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(SupportTicketMessage.objects.count(), 0)

    def test_user_cannot_reply_to_closed_ticket(self):
        owner = self._user(mobile="09131000106")
        ticket = self._ticket(user=owner, status="closed")

        self.client.force_login(owner)

        response = self.client.post(
            reverse("main:support_ticket_reply", kwargs={"pk": ticket.pk}),
            data={"body": "پاسخ بعد از بسته‌شدن"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(SupportTicketMessage.objects.count(), 0)

    def test_user_cannot_close_foreign_ticket(self):
        owner = self._user(mobile="09131000107")
        attacker = self._user(mobile="09131000108")
        ticket = self._ticket(user=owner, status="open")

        self.client.force_login(attacker)

        response = self.client.post(
            reverse("main:support_ticket_close", kwargs={"pk": ticket.pk})
        )

        self.assertEqual(response.status_code, 404)

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "open")

    @override_settings(PLATFORM_SUPPORT_ACTION_POST_MAX_BYTES=20)
    def test_platform_support_action_rejects_large_payload_before_update(self):
        owner = self._user(mobile="09131000109")
        admin = self._support_admin(mobile="09131000110")
        ticket = self._ticket(user=owner, status="open")

        self.client.force_login(admin)

        with patch(
            "apps.main.support_services.update_support_ticket_status"
        ) as mocked_update, patch(
            "apps.main.support_services.add_support_message"
        ) as mocked_message:
            response = self.client.post(
                reverse(
                    "platform_admin:support_status_action",
                    kwargs={"pk": ticket.pk},
                ),
                data={
                    "status": "closed",
                    "priority": "normal",
                    "assigned_team": "support",
                    "admin_reply": "الف" * 100,
                    "internal_note": "",
                },
            )

        self.assertEqual(response.status_code, 302)
        mocked_update.assert_not_called()
        mocked_message.assert_not_called()

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "open")
