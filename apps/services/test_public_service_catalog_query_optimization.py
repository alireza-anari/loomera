from __future__ import annotations

from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from apps.comments_scores_favories.models import Scoring
from apps.services.models import GroupServices, Services
from apps.services.views import _with_public_service_list_data
from tests_stage1_helpers import Stage1DomainFactoryMixin


class PublicServiceCatalogQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.customer = self.make_customer()

        self.service = self.make_service(
            name="خدمت عمومی بهینه‌شده",
            duration_minutes=45,
            base_price=250_000,
            is_platform_catalog=True,
        )

        self.active_group = self.service.service_group.get()

        self.inactive_group = GroupServices.objects.create(
            group_title="گروه غیرفعال تست",
            is_active=False,
        )
        self.service.service_group.add(self.inactive_group)

        Scoring.objects.create(
            scoring_user=self.customer,
            service=self.service,
            score=4,
        )

        second_customer = self.make_customer()
        Scoring.objects.create(
            scoring_user=second_customer,
            service=self.service,
            score=2,
        )

    def _prepared_services(self, queryset=None):
        if queryset is None:
            queryset = Services.objects.filter(
                pk=self.service.pk,
            )

        return list(_with_public_service_list_data(queryset).order_by("pk"))

    def test_service_list_and_groups_use_two_queries(self):
        with self.assertNumQueries(2):
            services = self._prepared_services()

        self.assertEqual(len(services), 1)

        service = services[0]
        self.assertEqual(float(service.public_avg_score), 3.0)
        self.assertEqual(
            [group.pk for group in service.public_service_groups],
            [self.active_group.pk],
        )

    def test_rendering_prepared_service_cards_runs_no_queries(self):
        services = self._prepared_services()

        with self.assertNumQueries(0):
            html = render_to_string(
                "services/partials/filtered_services.html",
                {
                    "services": services,
                },
            )

        self.assertIn("خدمت عمومی بهینه‌شده", html)
        self.assertIn(self.active_group.group_title, html)
        self.assertNotIn(self.inactive_group.group_title, html)

    def test_query_count_does_not_grow_with_more_services(self):
        service_ids = [self.service.pk]

        for index in range(12):
            service = self.make_service(
                name=f"خدمت کاتالوگ {index}",
                duration_minutes=30,
                base_price=100_000 + index,
                is_platform_catalog=True,
            )
            service_ids.append(service.pk)

        with self.assertNumQueries(2):
            services = self._prepared_services(
                Services.objects.filter(
                    pk__in=service_ids,
                )
            )

        with self.assertNumQueries(0):
            html = render_to_string(
                "services/partials/filtered_services.html",
                {
                    "services": services,
                },
            )

        self.assertEqual(len(services), 13)
        self.assertIn("خدمت کاتالوگ 11", html)

    def test_subgroup_ajax_endpoint_uses_fixed_query_budget(self):
        url = reverse(
            "services:get_service_of_subgroups",
            kwargs={
                "subgroup_id": self.active_group.pk,
            },
        )

        with self.assertNumQueries(3):
            response = self.client.get(
                url,
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "خدمت عمومی بهینه‌شده",
        )

    def test_public_average_score_matches_model_result(self):
        expected = self.service.get_average_score()

        service = self._prepared_services()[0]

        self.assertEqual(
            float(service.public_avg_score),
            float(expected),
        )
