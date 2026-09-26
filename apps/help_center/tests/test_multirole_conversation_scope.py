"""Conversation scope must come from current server-side workspace authorization."""

import json
from unittest.mock import patch

from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser, SalonManager, Stylist, UserWorkspacePreference
from apps.help_center.actions.common import issue_confirmation
from apps.help_center.actions.manager_operations import _manager_salon
from apps.help_center.actions.router import run_assistant_action
from apps.help_center.models import HelpConversation
from apps.help_center.multirole_scope import help_workspace_scope
from apps.help_center.services import get_or_create_conversation
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus


class MultiroleHelpConversationScopeTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            mobile_number="09123000001", name="مدیر", family="آزمایش", password="test-pass",
        )
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        manager = SalonManager.objects.create(user=self.user)
        self.salon_a = Salon.objects.create(salon_name="الف", salon_manager=manager)
        self.salon_b = Salon.objects.create(salon_name="ب", salon_manager=manager)
        self.other = CustomUser.objects.create_user(
            mobile_number="09123000002", name="دیگر", family="آزمایش", password="test-pass",
        )
        self.other.is_active = True
        self.other.save(update_fields=["is_active"])
        other_manager = SalonManager.objects.create(user=self.other)
        self.foreign = Salon.objects.create(salon_name="دیگر", salon_manager=other_manager)
        self.client.force_login(self.user)
        self.factory = RequestFactory()

    def _select(self, salon):
        UserWorkspacePreference.objects.update_or_create(
            user=self.user,
            defaults={"kind": "manager", "salon": salon, "was_salon_workspace": True,
                      "has_chosen_multirole_workspace": True},
        )

    def _request(self):
        request = self.factory.get("/help/api/conversation/?salon_id=" + str(self.foreign.pk))
        request.user = self.user
        request.session = self.client.session
        return request

    def _conversation(self):
        return get_or_create_conversation(
            self._request(), page_path="/", page_key="general", route_name="",
        )

    def test_no_explicit_choice_for_multi_salon_manager_does_not_guess_first_salon(self):
        self.assertEqual(help_workspace_scope(self._request()), {"role": "customer", "salon_id": None})

    def test_scope_comes_from_validated_workspace_not_request_salon_id(self):
        self._select(self.salon_a)
        self.assertEqual(help_workspace_scope(self._request()), {
            "role": "manager", "salon_id": self.salon_a.pk,
        })
        self._select(self.foreign)
        self.assertEqual(help_workspace_scope(self._request()), {"role": "customer", "salon_id": None})

    def test_stylist_scope_follows_only_current_active_membership(self):
        stylist = Stylist.objects.create(user=self.user, is_active=True)
        membership = SalonMembership.objects.create(
            salon=self.salon_a, stylist=stylist, status=SalonMembershipStatus.ACTIVE,
        )
        UserWorkspacePreference.objects.update_or_create(
            user=self.user, defaults={"kind": "stylist", "salon": None},
        )
        session = self.client.session
        session["active_stylist_salon_id"] = self.salon_a.pk
        session.save()
        self.assertEqual(help_workspace_scope(self._request()), {
            "role": "stylist", "salon_id": self.salon_a.pk,
        })
        membership.status = SalonMembershipStatus.PAUSED
        membership.save(update_fields=["status"])
        self.assertEqual(help_workspace_scope(self._request()), {
            "role": "stylist", "salon_id": None,
        })

    def test_other_salon_and_revocation_cannot_read_previous_messages(self):
        self._select(self.salon_a)
        old = self._conversation()
        self.assertEqual(old.metadata["workspace_scope"], {
            "v": 1, "role": "manager", "salon_id": self.salon_a.pk,
        })
        endpoint = reverse("help_center:conversation_api")
        self.assertEqual(self.client.get(endpoint, {"conversation_id": str(old.public_id)}).status_code, 200)

        self._select(self.salon_b)
        self.assertEqual(self.client.get(endpoint, {"conversation_id": str(old.public_id)}).status_code, 404)
        self._select(self.salon_a)
        self.salon_a.salon_manager = SalonManager.objects.get(user=self.other)
        self.salon_a.save(update_fields=["salon_manager"])
        self.assertEqual(self.client.get(endpoint, {"conversation_id": str(old.public_id)}).status_code, 404)

    def test_legacy_unscoped_manager_chat_is_not_guessed_into_salon(self):
        self._select(self.salon_a)
        legacy = HelpConversation.objects.create(user=self.user, role="manager", metadata={})
        self.assertEqual(self.client.get(reverse("help_center:conversation_api"), {
            "conversation_id": str(legacy.public_id),
        }).status_code, 404)

    @patch("apps.help_center.actions.router.run_manager_operation")
    def test_professional_actions_follow_selected_role_not_all_profiles(self, manager_action):
        manager_action.return_value = {"handled": True, "kind": "action_collect"}
        self._select(self.salon_a)
        UserWorkspacePreference.objects.filter(user=self.user).update(kind="customer", salon=None)
        request = self._request()
        self.assertEqual(run_assistant_action(
            request, message="دعوت متخصص جدید کن", action_state=None,
        ), {"handled": False})
        manager_action.assert_not_called()
        self._select(self.salon_a)
        self.assertTrue(run_assistant_action(
            self._request(), message="دعوت متخصص جدید کن", action_state=None,
        )["handled"])
        manager_action.assert_called_once()

    @patch("apps.help_center.action_views._consume_action_limit", return_value=True)
    @patch("apps.help_center.action_views.execute_assistant_confirmation")
    def test_old_signed_manager_operation_cannot_execute_after_salon_switch(
        self, execute, _limit,
    ):
        self._select(self.salon_a)
        token = issue_confirmation(user=self.user, action="manager_invite_prepare_submit", data={
            "salon_id": self.salon_a.pk,
        })
        self._select(self.salon_b)
        response = self.client.post(reverse("help_center:assistant_action_api"),
            data=json.dumps({"command": "execute", "confirmation_token": token}),
            content_type="application/json")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["workspace_changed"])
        execute.assert_not_called()

    def test_old_manager_action_state_cannot_follow_workspace_switch(self):
        self._select(self.salon_b)
        response = self.client.post(reverse("help_center:assistant_action_api"),
            data=json.dumps({
                "command": "message", "message": "ادامه بده",
                "action_state": {"mode": "manager_invite", "salon_id": self.salon_a.pk},
            }), content_type="application/json")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["workspace_changed"])

    def test_manager_read_actions_remain_in_chosen_salon_even_if_other_is_owned(self):
        from django.core.exceptions import ValidationError

        self._select(self.salon_a)
        self.assertEqual(_manager_salon(self._request()).pk, self.salon_a.pk)
        with self.assertRaises(ValidationError):
            _manager_salon(self._request(), salon_id=self.salon_b.pk)

    @patch("apps.help_center.views.consume_rate_limit", return_value=(True, 29))
    @patch("apps.help_center.views.answer_help_question")
    def test_only_scoped_server_history_reaches_answer_engine(self, answer, _limit):
        # The view consumes redacted_question with pop() on each response.
        # Return a fresh dictionary per mocked call, like the real answer engine.
        answer.side_effect = lambda **_kwargs: {
            "answer": "پاسخ", "sources": [], "guide": None, "page_key": "general",
            "ai": False, "model_name": "", "redacted_question": "سؤال معتبر",
        }
        self._select(self.salon_a)
        endpoint = reverse("help_center:chat_api")

        def post(conversation_id=None):
            return self.client.post(endpoint, data=json.dumps({
                "message": "سؤال معتبر", "conversation_id": conversation_id,
                "history": [{"role": "user", "content": "SECRET_FROM_OTHER_WORKSPACE"}],
                "salon_id": self.foreign.pk, "role": "manager",
            }), content_type="application/json")

        first = post()
        self.assertEqual(first.status_code, 200)
        first_id = first.json()["conversation_id"]
        self.assertTrue(first_id)
        self.assertEqual(answer.call_args.kwargs["history"], [])
        self.assertEqual(answer.call_args.kwargs["role"], "manager")
        second = post(first_id)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["conversation_id"], first_id)
        self.assertNotIn("SECRET_FROM_OTHER_WORKSPACE", str(answer.call_args.kwargs["history"]))
        self.assertIn("سؤال معتبر", str(answer.call_args.kwargs["history"]))
        self._select(self.salon_b)
        third = post(first_id)
        self.assertEqual(third.status_code, 200)
        self.assertNotEqual(third.json()["conversation_id"], first_id)
        self.assertEqual(answer.call_args.kwargs["history"], [])

    @patch("apps.help_center.views.consume_rate_limit", return_value=(True, 29))
    @patch("apps.help_center.views.answer_help_question")
    def test_revocation_during_answer_never_returns_old_scope_response(self, answer, _limit):
        self._select(self.salon_a)

        def revoke(**_kwargs):
            self._select(self.salon_b)
            return {
                "answer": "OLD_SALON_ANSWER", "sources": [], "guide": None,
                "page_key": "general", "ai": False, "model_name": "",
                "redacted_question": "سؤال",
            }

        answer.side_effect = revoke
        response = self.client.post(reverse("help_center:chat_api"),
            data=json.dumps({"message": "سؤال"}), content_type="application/json")
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("OLD_SALON_ANSWER", response.content.decode("utf-8"))
        self.assertEqual(HelpConversation.objects.filter(user=self.user).count(), 0)
