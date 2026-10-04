from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.test import SimpleTestCase

from apps.dashboards.views import _is_step2_complete


class OptionalLocationAreaFieldsRegressionTests(SimpleTestCase):
    def test_step2_completion_does_not_require_zone_or_neighborhood(self):
        salon = SimpleNamespace(
            zone=None,
            neighborhood_id=None,
            address="اصفهان، خیابان حکیم نظامی",
            location=object(),
        )

        self.assertTrue(_is_step2_complete(salon))

    def test_zone_and_neighborhood_are_labeled_optional_in_onboarding(self):
        template_path = Path(settings.BASE_DIR) / "templates" / "dashboards" / "salon_profile_creator_step2.html"
        source = template_path.read_text(encoding="utf-8")

        self.assertIn("منطقه / ناحیه (اختیاری)", source)
        self.assertIn("محله (اختیاری)", source)
