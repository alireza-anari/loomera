from __future__ import annotations

from types import SimpleNamespace

from django.contrib.staticfiles import finders
from django.test import (
    RequestFactory,
    SimpleTestCase,
    override_settings,
)
from PIL import Image

from apps.orders.quick_link_print_templates import (
    BUSINESS_CARD_BACK_ROW_CENTERS,
    BUSINESS_CARD_FRONT_NAME_CENTER,
    BUSINESS_CARD_FRONT_QR_BOX,
    BUSINESS_CARD_PRINT_FIDELITY_V3,
    _business_card_public_salon_url,
)


@override_settings(
    PUBLIC_BASE_URL="https://loomera.ir",
    SITE_URL="https://loomera.ir",
    ALLOWED_HOSTS=[
        "testserver",
        "127.0.0.1",
    ],
)
class BusinessCardPrintFidelityTests(
    SimpleTestCase
):
    def test_assets_fill_white_print_canvas(self):
        white_points_by_asset = {
            (
                "branding/quick-links/"
                "business-card-front.png"
            ): (
                (0, 0),
                (0, 574),
                (500, 20),
                (500, 550),
            ),
            (
                "branding/quick-links/"
                "business-card-back.png"
            ): (
                (0, 0),
                (1074, 0),
                (0, 574),
                (1074, 574),
                (500, 20),
            ),
        }

        for static_path, white_points in (
            white_points_by_asset.items()
        ):
            resolved = finders.find(
                static_path
            )

            self.assertTrue(resolved)

            with Image.open(resolved) as image:
                self.assertEqual(
                    image.size,
                    (1075, 575),
                )
                self.assertEqual(
                    image.mode,
                    "RGB",
                )

                for point in white_points:
                    self.assertEqual(
                        image.getpixel(point),
                        (255, 255, 255),
                    )

                dpi = image.info.get(
                    "dpi"
                )
                self.assertIsNotNone(dpi)
                self.assertAlmostEqual(
                    dpi[0],
                    300,
                    delta=1,
                )

    def test_approved_assets_keep_dynamic_regions_blank(self):
        front_path = finders.find(
            "branding/quick-links/"
            "business-card-front.png"
        )
        back_path = finders.find(
            "branding/quick-links/"
            "business-card-back.png"
        )

        self.assertTrue(front_path)
        self.assertTrue(back_path)

        with Image.open(front_path) as front:
            front_rgb = front.convert("RGB")
            self.assertGreaterEqual(
                min(
                    front_rgb.getpixel(
                        (850, 286)
                    )
                ),
                245,
            )
            self.assertGreaterEqual(
                min(
                    front_rgb.getpixel(
                        (278, 463)
                    )
                ),
                245,
            )

        with Image.open(back_path) as back:
            back_rgb = back.convert("RGB")

            for row_y in (
                149,
                223,
                297,
                371,
                444,
            ):
                self.assertGreaterEqual(
                    min(
                        back_rgb.getpixel(
                            (680, row_y)
                        )
                    ),
                    245,
                )

    def test_dynamic_regions_are_calibrated(self):
        self.assertTrue(
            BUSINESS_CARD_PRINT_FIDELITY_V3
        )
        self.assertEqual(
            BUSINESS_CARD_FRONT_QR_BOX,
            (742, 174, 966, 398),
        )
        self.assertEqual(
            BUSINESS_CARD_FRONT_NAME_CENTER,
            (278, 463),
        )
        self.assertEqual(
            BUSINESS_CARD_BACK_ROW_CENTERS,
            (
                149,
                223,
                297,
                371,
                444,
            ),
        )

    def test_local_request_host_is_not_printed(self):
        salon = SimpleNamespace(
            canonical_url="",
            get_absolute_url=lambda: (
                "/salons/example/"
            ),
        )
        request = RequestFactory().get(
            "/",
            HTTP_HOST="127.0.0.1:8000",
        )

        result = (
            _business_card_public_salon_url(
                request,
                salon,
            )
        )

        self.assertEqual(
            result,
            (
                "https://loomera.ir/"
                "salons/example/"
            ),
        )
        self.assertNotIn(
            "127.0.0.1",
            result,
        )
