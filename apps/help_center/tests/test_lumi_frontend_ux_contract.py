from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class LumiFrontendUxContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        base = Path(settings.BASE_DIR)
        cls.js = (
            base / "static" / "js" / "components" / "help_assistant.js"
        ).read_text(encoding="utf-8")
        cls.css = (
            base / "static" / "css" / "components" / "help_assistant.css"
        ).read_text(encoding="utf-8")

    def test_failed_regular_message_has_retry_without_duplicate_user_history(self):
        self.assertIn("data-lumi-retry-message", self.js)
        self.assertIn("form.dataset.lumiRetryMessage", self.js)
        self.assertIn("const isRetry =", self.js)
        self.assertIn("if (!isRetry)", self.js)
        self.assertIn("retryMessage: text", self.js)

    def test_network_errors_are_normalized(self):
        self.assertIn("function lumiRequestError(", self.js)
        self.assertIn("failed to fetch", self.js.lower())
        self.assertIn("اتصال اینترنت", self.js)
        self.assertIn("ارتباط با لومی برقرار نشد", self.js)

    def test_read_requests_have_timeout_but_execute_write_does_not(self):
        self.assertIn("function fetchWithTimeout(", self.js)
        self.assertIn('command === "execute"', self.js)
        self.assertIn(
            "? await fetch(root.dataset.assistantActionUrl, requestOptions)",
            self.js,
        )
        self.assertIn(
            ": await fetchWithTimeout(root.dataset.assistantActionUrl, requestOptions)",
            self.js,
        )
        self.assertIn(
            "await fetchWithTimeout(root.dataset.customerDiscoveryUrl",
            self.js,
        )
        self.assertIn(
            "await fetchWithTimeout(root.dataset.customerBookingUrl",
            self.js,
        )
        self.assertIn("await fetchWithTimeout(root.dataset.chatUrl", self.js)

    def test_error_and_retry_have_mobile_styles(self):
        self.assertIn(".lm-help-assistant__message--error", self.css)
        self.assertIn(".lm-help-assistant__retry", self.css)
        self.assertIn('aria-busy="true"', self.css)
