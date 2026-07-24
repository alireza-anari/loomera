from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.staticfiles import finders
from django.test import (
    RequestFactory,
    SimpleTestCase,
    override_settings,
)
from PIL import Image

from apps.orders.quick_link_print_templates import (
    PRINT_TEMPLATE_BY_KEY,
    TABLE_STAND_NAME_BOX,
    TABLE_STAND_PRINT_TEMPLATE_V2,
    TABLE_STAND_QR_BOX,
    TABLE_STAND_TRIM_BOX,
    _TableStandPublicRequest,
    _render_table_stand,
)


@override_settings(
    PUBLIC_BASE_URL="https://loomera.ir",
    SITE_URL="https://loomera.ir",
    ALLOWED_HOSTS=[
        "testserver",
        "127.0.0.1",
    ],
)
class TableStandArtworkTests(
    SimpleTestCase
):
    def test_reusable_template_is_print_ready(self):
        resolved = finders.find(
            "branding/quick-links/"
            "table-stand.png"
        )
        self.assertTrue(resolved)

        with Image.open(resolved) as image:
            self.assertEqual(
                image.size,
                (1311, 1819),
            )
            self.assertIn(
                image.mode,
                {"RGB", "RGBA"},
            )
            dpi = image.info.get("dpi")
            self.assertIsNotNone(dpi)
            self.assertAlmostEqual(
                dpi[0],
                300,
                delta=1,
            )

        spec = PRINT_TEMPLATE_BY_KEY[
            "table_stand"
        ]
        self.assertEqual(
            (
                spec.width,
                spec.height,
            ),
            (1311, 1819),
        )
        self.assertEqual(
            (
                spec.width_mm,
                spec.height_mm,
            ),
            (105, 148),
        )

    def test_dynamic_regions_and_bleed_contract(self):
        self.assertTrue(
            TABLE_STAND_PRINT_TEMPLATE_V2
        )
        self.assertEqual(
            TABLE_STAND_NAME_BOX,
            (240, 530, 1070, 820),
        )
        self.assertEqual(
            TABLE_STAND_QR_BOX,
            (735, 1295, 1025, 1585),
        )
        self.assertEqual(
            TABLE_STAND_TRIM_BOX,
            (35, 35, 1275, 1783),
        )

    def test_local_preview_builds_public_qr_url(self):
        request = RequestFactory().get(
            "/",
            HTTP_HOST="127.0.0.1:8000",
        )
        public_request = (
            _TableStandPublicRequest(
                request
            )
        )

        self.assertEqual(
            public_request.build_absolute_uri(
                "/orders/quick-link/test/"
            ),
            (
                "https://loomera.ir/"
                "orders/quick-link/test/"
            ),
        )

    @patch(
        "apps.orders.quick_link_print_templates."
        "_draw_rtl"
    )
    @patch(
        "apps.orders.quick_link_print_templates."
        "_fit_font"
    )
    @patch(
        "apps.orders.quick_link_print_templates."
        "_qr_image"
    )
    def test_every_salon_gets_its_own_name_and_qr(
        self,
        qr_mock,
        font_mock,
        draw_rtl_mock,
    ):
        qr_mock.return_value = Image.new(
            "RGBA",
            (290, 290),
            (0, 0, 0, 255),
        )
        font_mock.return_value = object()

        quick_link = SimpleNamespace(
            salon=SimpleNamespace(
                salon_name="مجموعه نمونه",
            ),
        )
        request = RequestFactory().get(
            "/",
            HTTP_HOST="127.0.0.1:8000",
        )
        spec = PRINT_TEMPLATE_BY_KEY[
            "table_stand"
        ]

        rendered = _render_table_stand(
            request=request,
            quick_link=quick_link,
            spec=spec,
        )

        self.assertEqual(
            rendered.size,
            (1311, 1819),
        )
        qr_mock.assert_called_once()
        draw_rtl_mock.assert_called_once()

        qr_request = (
            qr_mock.call_args.kwargs[
                "request"
            ]
        )
        self.assertEqual(
            qr_request.build_absolute_uri(
                "/orders/quick-link/test/"
            ),
            (
                "https://loomera.ir/"
                "orders/quick-link/test/"
            ),
        )
        self.assertEqual(
            qr_mock.call_args.kwargs[
                "target_size"
            ],
            290,
        )
