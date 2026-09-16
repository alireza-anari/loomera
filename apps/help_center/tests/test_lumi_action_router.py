from unittest.mock import Mock, patch

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase

from apps.help_center.actions.router import is_assistant_action_candidate, run_assistant_action


class LumiActionRouterTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_guest_can_ask_for_capabilities(self):
        request = self.factory.post("/help/api/actions/assistant/")
        request.user = AnonymousUser()
        self.assertTrue(
            is_assistant_action_candidate(
                request,
                message="چه کارهایی میتونی برام انجام بدی؟",
                current_path="/",
            )
        )
        result = run_assistant_action(
            request,
            message="چه کارهایی میتونی برام انجام بدی؟",
            action_state=None,
            current_path="/",
        )
        self.assertTrue(result["handled"])
        self.assertEqual(result["kind"], "action_capabilities")

    def test_generic_help_question_is_not_captured(self):
        request = self.factory.post("/help/api/actions/assistant/")
        request.user = AnonymousUser()
        self.assertFalse(
            is_assistant_action_candidate(
                request,
                message="چطور رمز عبورم رو عوض کنم؟",
                current_path="/",
            )
        )


class LumiAssistantActionApiTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("apps.help_center.action_views._consume_action_limit", return_value=True)
    @patch("apps.help_center.action_views.run_assistant_action")
    @patch("apps.help_center.action_views.is_assistant_action_candidate", return_value=True)
    def test_api_forwards_operational_message(self, _candidate, runner, _limit):
        from apps.help_center.action_views import assistant_action_api

        runner.return_value = {"handled": True, "kind": "action_collect", "answer": "ok"}
        request = self.factory.post(
            "/help/api/actions/assistant/",
            data='{"message":"برای فردا مرخصی میخوام","current_path":"/"}',
            content_type="application/json",
        )
        request.user = Mock(is_authenticated=True, pk=7)
        response = assistant_action_api(request)
        self.assertEqual(response.status_code, 200)
        runner.assert_called_once()

    def test_api_rejects_execute_without_token(self):
        from apps.help_center.action_views import assistant_action_api

        request = self.factory.post(
            "/help/api/actions/assistant/",
            data='{"command":"execute"}',
            content_type="application/json",
        )
        request.user = Mock(is_authenticated=True, pk=7)
        response = assistant_action_api(request)
        self.assertEqual(response.status_code, 400)
