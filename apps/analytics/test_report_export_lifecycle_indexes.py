from django.db import connection, models
from django.test import TestCase

from apps.analytics.models import (
    ReportExportJob,
)


class ReportExportLifecycleIndexTests(
    TestCase,
):
    expected_indexes = {
        "rexport_status_dt": {
            "fields": (
                "status",
                "created_at",
            ),
            "condition": None,
        },
        "rexport_proc_start": {
            "fields": ("started_at",),
            "condition": models.Q(
                status="processing",
            ),
        },
        "rexport_done_exp": {
            "fields": ("expires_at",),
            "condition": models.Q(
                status="completed",
            ),
        },
        "rexport_done_comp": {
            "fields": ("completed_at",),
            "condition": models.Q(
                status="completed",
            ),
        },
        "rexport_fail_comp": {
            "fields": ("completed_at",),
            "condition": models.Q(
                status="failed",
            ),
        },
        "rexport_exp_upd": {
            "fields": ("updated_at",),
            "condition": models.Q(
                status="expired",
            ),
        },
    }

    def test_model_declares_lifecycle_indexes(
        self,
    ):
        indexes = {index.name: index for index in ReportExportJob._meta.indexes}

        self.assertEqual(
            set(indexes),
            set(self.expected_indexes),
        )

        for (
            index_name,
            expected,
        ) in self.expected_indexes.items():
            with self.subTest(
                index=index_name,
            ):
                index = indexes[index_name]

                self.assertEqual(
                    tuple(index.fields),
                    expected["fields"],
                )
                self.assertEqual(
                    index.condition,
                    expected["condition"],
                )

    def test_database_contains_lifecycle_indexes(
        self,
    ):
        table_name = ReportExportJob._meta.db_table

        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(
                cursor,
                table_name,
            )

        for index_name in self.expected_indexes:
            with self.subTest(
                index=index_name,
            ):
                self.assertIn(
                    index_name,
                    constraints,
                )
                self.assertTrue(
                    constraints[index_name]["index"],
                )

    def test_lifecycle_indexes_are_not_unique(
        self,
    ):
        table_name = ReportExportJob._meta.db_table

        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(
                cursor,
                table_name,
            )

        for index_name in self.expected_indexes:
            with self.subTest(
                index=index_name,
            ):
                self.assertFalse(
                    constraints[index_name]["unique"],
                )
