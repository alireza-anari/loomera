from django.test import TestCase

from apps.dashboards.beta_readiness import (
    serialize_beta_salon_readiness,
    with_beta_readiness_annotations,
)
from apps.salons.models import Salon
from tests_stage1_helpers import Stage1DomainFactoryMixin


class BetaReadinessQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(manager=self.manager)

    def test_annotated_readiness_matches_legacy_result(self):
        legacy_salon = Salon.objects.get(pk=self.salon.pk)
        expected = serialize_beta_salon_readiness(legacy_salon)

        optimized_salon = with_beta_readiness_annotations(
            Salon.objects.filter(pk=self.salon.pk)
        ).get()

        with self.assertNumQueries(0):
            actual = serialize_beta_salon_readiness(optimized_salon)

        self.assertEqual(actual, expected)

    def test_serializing_annotated_salons_adds_no_queries(self):
        salon_ids = [self.salon.pk]

        for index in range(4):
            manager = self.make_salon_manager(
                user_kwargs={
                    "mobile_number": f"0912111000{index}",
                    "email": f"manager-{index}@example.com",
                }
            )
            salon_ids.append(self.make_salon(manager=manager).pk)

        salons = list(
            with_beta_readiness_annotations(
                Salon.objects.filter(pk__in=salon_ids).order_by("pk")
            )
        )

        with self.assertNumQueries(0):
            results = [serialize_beta_salon_readiness(salon) for salon in salons]

        self.assertEqual(len(results), 5)
        self.assertEqual(
            {result["salon_id"] for result in results},
            set(salon_ids),
        )

    def test_unannotated_serializer_remains_backward_compatible(self):
        salon = Salon.objects.get(pk=self.salon.pk)

        result = serialize_beta_salon_readiness(salon)

        self.assertEqual(result["salon_id"], self.salon.pk)
        self.assertIn("beta_ready", result)
        self.assertIn("has_bookable_path", result)
