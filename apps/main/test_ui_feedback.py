import ast
import re
from pathlib import Path
from types import SimpleNamespace

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.api.v1.responses import api_error
from apps.main.ui_feedback import (
    DEFAULT_ERROR_MESSAGE,
    DEFAULT_FORM_ERROR_MESSAGE,
    pop_redirect_form_errors,
    safe_form_errors,
    stash_form_errors,
    user_error_message,
    user_ui_message,
)


LATIN_RE = re.compile(r"[A-Za-z]")


class FeedbackSanitizerTests(SimpleTestCase):
    def test_persian_validation_error_is_preserved(self):
        message = "شماره موبایل واردشده معتبر نیست."
        self.assertEqual(user_error_message(ValidationError(message)), message)

    def test_mixed_validation_messages_keep_only_safe_persian_copy(self):
        result = user_error_message(
            ValidationError([
                "شماره موبایل واردشده معتبر نیست.",
                "Internal Server Error",
            ])
        )
        self.assertEqual(result, "شماره موبایل واردشده معتبر نیست.")
        self.assertIsNone(LATIN_RE.search(result))

    def test_raw_technical_exception_is_never_exposed(self):
        result = user_error_message(ValueError("ValueError: database connection failed"))
        self.assertEqual(result, DEFAULT_ERROR_MESSAGE)
        self.assertIsNone(LATIN_RE.search(result))

    def test_literal_validation_collection_is_normalized(self):
        result = user_ui_message("['مقدار اول معتبر نیست.', 'مقدار دوم را بررسی کنید.']")
        self.assertEqual(result, "مقدار اول معتبر نیست، مقدار دوم را بررسی کنید.")
        self.assertIsNone(LATIN_RE.search(result))

    def test_approved_file_format_term_is_localized(self):
        result = user_error_message(ValidationError("فایل PDF معتبر نیست."))
        self.assertIn("پی‌دی‌اِف", result)
        self.assertIsNone(LATIN_RE.search(result))

    def test_user_ui_message_replaces_english_provider_text(self):
        result = user_ui_message("Internal Server Error")
        self.assertEqual(result, "پیام قابل نمایش در دسترس نیست.")
        self.assertIsNone(LATIN_RE.search(result))

    def test_positive_message_can_keep_latin_entity_name(self):
        result = user_ui_message(
            "نمای داشبورد روی سالن Nova تنظیم شد.",
            allow_latin_data=True,
        )
        self.assertEqual(result, "نمای داشبورد روی سالن Nova تنظیم شد.")

    def test_technical_message_is_rejected_even_when_latin_data_is_allowed(self):
        result = user_ui_message(
            "اتصال Nova با ValueError: timeout روبه‌رو شد.",
            allow_latin_data=True,
        )
        self.assertEqual(result, "پیام قابل نمایش در دسترس نیست.")

    def test_form_error_serialization_sanitizes_each_message(self):
        class MixedForm(forms.Form):
            title = forms.CharField(required=False)

            def clean_title(self):
                raise ValidationError([
                    "عنوان واردشده معتبر نیست.",
                    "Internal Server Error",
                ])

        form = MixedForm(data={"title": "x"})
        self.assertFalse(form.is_valid())
        self.assertEqual(
            safe_form_errors(form),
            {"title": [
                "عنوان واردشده معتبر نیست.",
                DEFAULT_FORM_ERROR_MESSAGE,
            ]},
        )

    def test_api_error_keeps_machine_code_but_sanitizes_human_message(self):
        response = api_error("provider_failure", "Gateway timeout error")
        self.assertEqual(response.data["error"]["code"], "provider_failure")
        self.assertEqual(
            response.data["error"]["message"],
            "درخواست انجام نشد. لطفاً اطلاعات ارسالی را بررسی کنید.",
        )
        self.assertIsNone(LATIN_RE.search(response.data["error"]["message"]))


class RedirectedFormErrorTests(SimpleTestCase):
    class SampleForm(forms.Form):
        title = forms.CharField(
            required=True,
            error_messages={"required": "عنوان را وارد کنید."},
        )

    def test_redirect_contract_keeps_only_safe_field_errors(self):
        form = self.SampleForm(data={"title": ""})
        self.assertFalse(form.is_valid())
        request = SimpleNamespace(path="/sample/action/", session={})

        stash_form_errors(request, form)
        payload = pop_redirect_form_errors(request)

        self.assertEqual(payload["action_path"], "/sample/action/")
        self.assertEqual(
            payload["errors"],
            [{"field": "title", "message": "عنوان را وارد کنید."}],
        )
        self.assertEqual(request.session, {})


class FeedbackSourceContractTests(SimpleTestCase):
    def _python_sources(self):
        apps_root = Path(settings.BASE_DIR) / "apps"
        for path in apps_root.rglob("*.py"):
            if "migrations" in path.parts or path.name.startswith("test_"):
                continue
            yield path

    def test_validation_error_message_lists_are_only_unwrapped_by_sanitizer(self):
        offenders = []
        direct_message_access = (
            re.compile(r"getattr\([^\n]*[\"']messages[\"']"),
            re.compile(r"\.messages\[[0-9]+\]"),
            re.compile(r"\.message_dict"),
        )
        sanitizer = (Path(settings.BASE_DIR) / "apps/main/ui_feedback.py").resolve()

        for path in self._python_sources():
            if path.resolve() == sanitizer:
                continue
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                1,
            ):
                if any(pattern.search(line) for pattern in direct_message_access):
                    offenders.append(f"{path.relative_to(settings.BASE_DIR)}:{line_number}")

        self.assertEqual(offenders, [])

    def test_user_facing_python_calls_do_not_embed_raw_exceptions(self):
        offenders = []
        response_calls = {
            "JsonResponse",
            "HttpResponse",
            "HttpResponseBadRequest",
            "HttpResponseForbidden",
            "HttpResponseNotAllowed",
            "HttpResponseServerError",
            "Response",
        }
        message_methods = {"error", "warning", "success", "info"}

        def call_name(node):
            if isinstance(node, ast.Name):
                return node.id
            if isinstance(node, ast.Attribute):
                return node.attr
            return ""

        def contains_raw_exception(node):
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Name)
                    and child.func.id == "str"
                    and child.args
                    and isinstance(child.args[0], ast.Name)
                    and child.args[0].id in {"exc", "e", "error", "exception"}
                ):
                    return True
                if (
                    isinstance(child, ast.FormattedValue)
                    and isinstance(child.value, ast.Name)
                    and child.value.id in {"exc", "e", "error", "exception"}
                ):
                    return True
                if (
                    isinstance(child, ast.Attribute)
                    and isinstance(child.value, ast.Name)
                    and child.value.id in {"exc", "e", "error", "exception"}
                    and child.attr in {"message", "messages", "args", "message_dict"}
                ):
                    return True
            return False

        for path in self._python_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                user_facing = call_name(node.func) in response_calls
                if isinstance(node.func, ast.Attribute):
                    user_facing = user_facing or node.func.attr == "add_error"
                    user_facing = user_facing or (
                        node.func.attr in message_methods
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "messages"
                    )
                if user_facing and contains_raw_exception(node):
                    offenders.append(
                        f"{path.relative_to(settings.BASE_DIR)}:{node.lineno}"
                    )

        self.assertEqual(offenders, [])

    def test_native_browser_alert_is_not_used_as_feedback(self):
        offenders = []
        alert_pattern = re.compile(r"(?<![\w.])alert\s*\(|window\.alert\s*\(")
        roots = (
            Path(settings.BASE_DIR) / "static/js",
            Path(settings.BASE_DIR) / "templates",
        )
        for root in roots:
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix not in {".js", ".html"}:
                    continue
                for line_number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(),
                    1,
                ):
                    if alert_pattern.search(line):
                        offenders.append(
                            f"{path.relative_to(settings.BASE_DIR)}:{line_number}"
                        )

        self.assertEqual(offenders, [])

    def test_framework_error_handlers_are_persian_and_hide_raw_details(self):
        self.assertEqual(
            settings.CSRF_FAILURE_VIEW,
            "apps.main.views.csrf_failure_view",
        )

        templates_root = Path(settings.BASE_DIR) / "templates"
        for template_name in ("400.html", "403.html", "404.html", "500.html"):
            source = (templates_root / template_name).read_text(encoding="utf-8")
            self.assertRegex(source, r"[\u0600-\u06FF]")

        main_views = (
            Path(settings.BASE_DIR) / "apps/main/views.py"
        ).read_text(encoding="utf-8")
        csrf_source = main_views[
            main_views.index("def csrf_failure_view"):
            main_views.index("class RobotsTxtView")
        ]
        self.assertNotIn("reason", csrf_source.split("return render", 1)[1])
        self.assertNotIn("exception", csrf_source.split("return render", 1)[1])

    def test_http_error_exceptions_do_not_contain_latin_user_copy(self):
        offenders = []
        exception_names = {"Http404", "PermissionDenied"}
        latin_re = re.compile(r"[A-Za-z]")

        for path in self._python_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                    continue
                if not isinstance(node.exc.func, ast.Name):
                    continue
                if node.exc.func.id not in exception_names or not node.exc.args:
                    continue
                first_arg = node.exc.args[0]
                if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                    if latin_re.search(first_arg.value):
                        offenders.append(
                            f"{path.relative_to(settings.BASE_DIR)}:{node.lineno}"
                        )

        self.assertEqual(offenders, [])

    def test_json_error_literals_are_persian_or_machine_codes(self):
        offenders = []
        machine_code = re.compile(r"^[a-z][a-z0-9_]*$")
        latin_re = re.compile(r"[A-Za-z]")

        for path in self._python_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                call_name = (
                    node.func.id if isinstance(node.func, ast.Name)
                    else node.func.attr if isinstance(node.func, ast.Attribute)
                    else ""
                )
                if call_name not in {"JsonResponse", "Response"}:
                    continue
                payload = node.args[0]
                if not isinstance(payload, ast.Dict):
                    continue
                for key, value in zip(payload.keys, payload.values):
                    if not (
                        isinstance(key, ast.Constant)
                        and key.value == "error"
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                    ):
                        continue
                    text = value.value.strip()
                    if latin_re.search(text) and not machine_code.fullmatch(text):
                        offenders.append(
                            f"{path.relative_to(settings.BASE_DIR)}:{node.lineno}"
                        )

        self.assertEqual(offenders, [])

    def test_django_flash_messages_have_one_template_renderer(self):
        renderers = []
        templates_root = Path(settings.BASE_DIR) / "templates"
        pattern = re.compile(r"{%\s*for\s+message\s+in\s+messages\s*%}")
        for path in templates_root.rglob("*.html"):
            if pattern.search(path.read_text(encoding="utf-8")):
                renderers.append(str(path.relative_to(settings.BASE_DIR)))

        self.assertEqual(renderers, ["templates/partials/messages.html"])
