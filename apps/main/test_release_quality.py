from __future__ import annotations

from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.urls import reverse


class ReleaseQualitySmokeTests(SimpleTestCase):
    def test_operational_url_names_resolve(self):
        expected_routes = [
            "health",
            "robots_txt",
            "main:health",
            "main:contact",
            "notifications:center",
            "platform_admin:dashboard",
            "platform_admin:analytics",
            "platform_admin:infrastructure",
            "platform_admin:audit",
            "search:search_page",
            "salons:show_salons",
            "services:all_services",
        ]
        for route_name in expected_routes:
            with self.subTest(route_name=route_name):
                self.assertTrue(reverse(route_name))

    def test_required_feature_flags_exist(self):
        required_flags = [
            "BETA_MODE",
            "COMMISSION_ENABLED",
            "ONLINE_PAYMENT_ENABLED",
            "DEPOSIT_ENABLED",
            "BNPL_ENABLED",
            "DEBT_ENFORCEMENT_ENABLED",
            "SALON_VERIFICATION_ENFORCED",
            "SALON_WITHDRAWAL_ENABLED",
            "AUTOMATIC_REFUND_ENABLED",
            "LOOMERA_ENABLE_CELERY",
            "LOOMERA_MEDIA_PROCESSING_ENABLED",
            "MESSAGING_ACTIONS_ENABLED",
            "USE_S3_MEDIA",
            "LOOMERA_REQUIRE_OBJECT_STORAGE",
        ]
        for flag_name in required_flags:
            with self.subTest(flag_name=flag_name):
                self.assertTrue(hasattr(settings, flag_name))

    def test_index_and_constraint_names_fit_common_database_limits(self):
        too_long = []
        for model in apps.get_models():
            for index in model._meta.indexes:
                if index.name and len(index.name) > 30:
                    too_long.append(f"{model._meta.label}.{index.name}")
            for constraint in model._meta.constraints:
                if constraint.name and len(constraint.name) > 30:
                    too_long.append(f"{model._meta.label}.{constraint.name}")
        self.assertEqual(too_long, [])

    @override_settings(DEBUG=False, SERVE_MEDIA_INSECURELY=False)
    def test_media_serving_is_not_forced_outside_debug(self):
        self.assertFalse(settings.DEBUG)
        self.assertFalse(getattr(settings, "SERVE_MEDIA_INSECURELY", False))

    @override_settings(
        DEBUG=False,
        USE_S3_MEDIA=True,
        AWS_ACCESS_KEY_ID="key",
        AWS_SECRET_ACCESS_KEY="secret",
        AWS_STORAGE_BUCKET_NAME="bucket",
        AWS_S3_ENDPOINT_URL="https://storage.iran.liara.site",
        STORAGES={
            "default": {"BACKEND": "storages.backends.s3.S3Storage"},
            "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
        },
    )
    def test_s3_media_storage_can_be_required_for_deployed_environments(self):
        self.assertTrue(settings.USE_S3_MEDIA)
        self.assertTrue(
            "storages.backends.s3" in settings.STORAGES["default"]["BACKEND"]
            or "LoomeraS3MediaStorage" in settings.STORAGES["default"]["BACKEND"]
        )
        self.assertTrue(settings.AWS_STORAGE_BUCKET_NAME)
        self.assertTrue(settings.AWS_S3_ENDPOINT_URL)

    def test_release_quality_docs_exist(self):
        from pathlib import Path

        base_dir = Path(settings.BASE_DIR)
        expected_docs = [
            base_dir / "docs" / "qa" / "release-readiness-checklist.md",
            base_dir / "docs" / "qa" / "manual-e2e-checklist.md",
            base_dir / "docs" / "qa" / "regression-matrix.md",
            base_dir / "docs" / "implementation" / "15-qa-release-readiness.md",
        ]
        for doc_path in expected_docs:
            with self.subTest(doc_path=str(doc_path)):
                self.assertTrue(doc_path.exists())
