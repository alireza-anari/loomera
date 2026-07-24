from __future__ import annotations

from django.test import SimpleTestCase

from apps.payments.finance import _safe_int as finance_safe_int
from apps.payments.ledger import _safe_int as ledger_safe_int


class UnexpectedIntFailure:
    def __int__(self):
        raise RuntimeError("unexpected integer conversion failure")


class PaymentSafeNumericConversionTests(SimpleTestCase):
    converters = (
        ("finance", finance_safe_int),
        ("ledger", ledger_safe_int),
    )

    def test_valid_values_are_converted(self):
        for name, converter in self.converters:
            with self.subTest(converter=name):
                self.assertEqual(converter(1250), 1250)
                self.assertEqual(converter("1250"), 1250)
                self.assertEqual(converter(None), 0)
                self.assertEqual(converter(""), 0)

    def test_expected_invalid_values_fall_back_to_zero(self):
        for name, converter in self.converters:
            with self.subTest(converter=name):
                self.assertEqual(converter("not-a-number"), 0)
                self.assertEqual(converter(object()), 0)

    def test_unexpected_conversion_errors_are_not_silenced(self):
        for name, converter in self.converters:
            with self.subTest(converter=name):
                with self.assertRaises(RuntimeError):
                    converter(UnexpectedIntFailure())
