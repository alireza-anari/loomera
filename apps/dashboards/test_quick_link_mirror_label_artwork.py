from __future__ import annotations

from unittest.mock import patch

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase
from PIL import Image

from apps.orders.quick_link_print_templates import (
    PRINT_TEMPLATE_BY_KEY,
    _render_mirror_label,
)


class MirrorLabelArtworkIntegrationTests(
    SimpleTestCase
):
    def test_artwork_is_real_transparent_png(self):
        resolved = finders.find(
            "branding/quick-links/"
            "mirror-label-print-art.png"
        )

        self.assertTrue(resolved)

        with Image.open(resolved) as image:
            self.assertEqual(
                image.size,
                (945, 945),
            )
            self.assertEqual(
                image.mode,
                "RGBA",
            )
            self.assertEqual(
                image.getpixel((0, 0))[3],
                0,
            )

    @patch(
        "apps.orders.quick_link_print_templates."
        "_qr_image"
    )
    def test_renderer_injects_live_qr_into_blank_area(
        self,
        qr_mock,
    ):
        qr_mock.return_value = Image.new(
            "RGBA",
            (305, 305),
            (0, 0, 0, 255),
        )

        spec = PRINT_TEMPLATE_BY_KEY[
            "mirror_label"
        ]

        rendered = _render_mirror_label(
            request=object(),
            quick_link=object(),
            spec=spec,
        )

        self.assertEqual(
            rendered.size,
            (945, 945),
        )
        self.assertEqual(
            rendered.getpixel((0, 0))[3],
            0,
        )

        center_pixel = rendered.getpixel(
            (472, 537)
        )

        self.assertEqual(
            center_pixel[:3],
            (0, 0, 0),
        )
        qr_mock.assert_called_once()
