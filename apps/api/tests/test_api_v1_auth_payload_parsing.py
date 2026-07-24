from __future__ import annotations

import inspect

from django.test import SimpleTestCase

from apps.api.v1.auth_otp import (
    ApiOtpPayloadInvalid,
    ApiOtpPayloadTooLarge,
)
from apps.api.v1.auth_views import (
    ApiOtpRequestAPIView,
    ApiOtpVerifyAPIView,
    _load_auth_json_object_payload,
    _parse_content_length,
)


class DummyRequest:
    def __init__(
        self,
        *,
        body=b"{}",
        content_length=None,
    ):
        self.body = body
        self.META = {}

        if content_length is not None:
            self.META["CONTENT_LENGTH"] = (
                content_length
            )


class ExplodingBodyRequest:
    META = {}

    @property
    def body(self):
        raise RuntimeError(
            "unexpected request body failure"
        )


class ApiAuthPayloadParsingTests(SimpleTestCase):
    def test_valid_json_object_is_returned(self):
        request = DummyRequest(
            body=b'{"mobile_number":"09121234567"}',
            content_length="35",
        )

        payload = _load_auth_json_object_payload(
            request,
            max_bytes=1024,
        )

        self.assertEqual(
            payload["mobile_number"],
            "09121234567",
        )

    def test_empty_body_uses_empty_object(self):
        request = DummyRequest(
            body=b"",
            content_length="0",
        )

        self.assertEqual(
            _load_auth_json_object_payload(
                request,
                max_bytes=1024,
            ),
            {},
        )

    def test_non_object_json_is_rejected(self):
        for raw_body in (
            b"[]",
            b'"text"',
            b"123",
            b"null",
        ):
            with self.subTest(raw_body=raw_body):
                with self.assertRaises(
                    ApiOtpPayloadInvalid
                ):
                    _load_auth_json_object_payload(
                        DummyRequest(body=raw_body),
                        max_bytes=1024,
                    )

    def test_malformed_json_and_utf8_are_rejected(self):
        for raw_body in (
            b"{not-json",
            b"\xff\xfe",
        ):
            with self.subTest(raw_body=raw_body):
                with self.assertRaises(
                    ApiOtpPayloadInvalid
                ):
                    _load_auth_json_object_payload(
                        DummyRequest(body=raw_body),
                        max_bytes=1024,
                    )

    def test_invalid_content_length_is_rejected(self):
        for value in (
            "invalid",
            object(),
            -1,
            "-5",
        ):
            with self.subTest(value=value):
                with self.assertRaises(
                    ApiOtpPayloadInvalid
                ):
                    _parse_content_length(value)

    def test_large_header_or_body_is_rejected(self):
        with self.assertRaises(
            ApiOtpPayloadTooLarge
        ):
            _load_auth_json_object_payload(
                DummyRequest(
                    body=b"{}",
                    content_length="2048",
                ),
                max_bytes=1024,
            )

        with self.assertRaises(
            ApiOtpPayloadTooLarge
        ):
            _load_auth_json_object_payload(
                DummyRequest(
                    body=b"x" * 1025,
                ),
                max_bytes=1024,
            )

    def test_unexpected_request_error_is_not_silenced(self):
        with self.assertRaises(RuntimeError):
            _load_auth_json_object_payload(
                ExplodingBodyRequest(),
                max_bytes=1024,
            )

    def test_both_otp_views_use_shared_parser(self):
        for view_class in (
            ApiOtpRequestAPIView,
            ApiOtpVerifyAPIView,
        ):
            with self.subTest(
                view=view_class.__name__
            ):
                source = inspect.getsource(
                    view_class._load_payload
                )

                self.assertIn(
                    "_load_auth_json_object_payload",
                    source,
                )
                self.assertNotIn(
                    "json.loads",
                    source,
                )
                self.assertNotIn(
                    "except ",
                    source,
                )
