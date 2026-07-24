from __future__ import annotations

from unittest.mock import patch

from django.core.exceptions import FieldDoesNotExist
from django.test import SimpleTestCase

from apps.orders.models import OrderDetail
from apps.orders.views import _order_detail_date_field_kind


class OrderDetailDateFieldInspectionTests(SimpleTestCase):
    def test_current_order_detail_date_is_native_date_field(self):
        self.assertIs(
            _order_detail_date_field_kind(),
            True,
        )

    def test_missing_date_field_uses_manual_fallback(self):
        with patch.object(
            OrderDetail._meta,
            "get_field",
            side_effect=FieldDoesNotExist("date"),
        ):
            self.assertIsNone(
                _order_detail_date_field_kind()
            )

    def test_existing_non_date_field_uses_legacy_branch(self):
        with patch.object(
            OrderDetail._meta,
            "get_field",
            return_value=object(),
        ):
            self.assertIs(
                _order_detail_date_field_kind(),
                False,
            )

    def test_unexpected_metadata_error_is_not_silenced(self):
        with patch.object(
            OrderDetail._meta,
            "get_field",
            side_effect=RuntimeError(
                "unexpected model metadata failure"
            ),
        ):
            with self.assertRaises(RuntimeError):
                _order_detail_date_field_kind()
