from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.analytics.models import (
    DailySearchMetric,
)
from apps.analytics.services import (
    _collect_daily_search_metric_payloads,
    build_daily_search_metrics,
)
from apps.search.models import (
    SearchConversion,
    SearchLog,
    SearchResultClick,
)
from tests_stage1_helpers import (
    Stage1DomainFactoryMixin,
)


class DailySearchMetricsQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.day = timezone.localdate()

        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(
            manager=self.manager,
        )
        self.customer = self.make_customer()

        self.first_hair_log = self._make_log(
            query="رنگ مو",
            normalized_query="رنگ مو",
            results_count=5,
            no_result=False,
        )
        self.second_hair_log = self._make_log(
            query="رنگ‌مو",
            normalized_query="رنگ مو",
            results_count=0,
            no_result=True,
        )
        self.haircut_log = self._make_log(
            query="کوتاهی مو",
            normalized_query="کوتاهی مو",
            results_count=2,
            no_result=False,
        )

        self._make_click(
            self.first_hair_log,
            rank=1,
        )
        self._make_click(
            self.second_hair_log,
            rank=2,
        )
        self._make_click(
            self.haircut_log,
            rank=1,
        )

        self._make_conversion(
            self.first_hair_log,
            "booking_started",
        )
        self._make_conversion(
            self.first_hair_log,
            "booking_completed",
        )
        self._make_conversion(
            self.second_hair_log,
            "booking_started",
        )

        self._create_outside_day_events()

    def _make_log(
        self,
        *,
        query,
        normalized_query,
        results_count,
        no_result,
    ):
        return SearchLog.objects.create(
            user=self.customer.user,
            session_key="analytics-search-test",
            query=query,
            normalized_query=normalized_query,
            results_count=results_count,
            no_result=no_result,
        )

    def _make_click(
        self,
        search_log,
        *,
        rank,
    ):
        return SearchResultClick.objects.create(
            search_log=search_log,
            user=self.customer.user,
            salon=self.salon,
            rank=rank,
            source="search",
        )

    def _make_conversion(
        self,
        search_log,
        conversion_type,
    ):
        return SearchConversion.objects.create(
            search_log=search_log,
            user=self.customer.user,
            salon=self.salon,
            conversion_type=conversion_type,
        )

    def _create_outside_day_events(self):
        old_time = timezone.now() - timedelta(days=2)

        old_log = self._make_log(
            query="رنگ مو قدیمی",
            normalized_query="رنگ مو",
            results_count=100,
            no_result=False,
        )
        SearchLog.objects.filter(
            pk=old_log.pk,
        ).update(
            created_at=old_time,
        )

        # Current click attached to an old SearchLog must not enter the
        # current day's metric.
        self._make_click(
            old_log,
            rank=1,
        )

        old_click = self._make_click(
            self.first_hair_log,
            rank=3,
        )
        SearchResultClick.objects.filter(
            pk=old_click.pk,
        ).update(
            created_at=old_time,
        )

        old_conversion = self._make_conversion(
            self.first_hair_log,
            "booking_completed",
        )
        SearchConversion.objects.filter(
            pk=old_conversion.pk,
        ).update(
            created_at=old_time,
        )

    def _payloads(self):
        return _collect_daily_search_metric_payloads(self.day)

    def test_payload_collection_uses_three_queries(self):
        with self.assertNumQueries(3):
            payloads = self._payloads()

        self.assertEqual(len(payloads), 2)

    def test_normalized_query_variants_are_consolidated(self):
        payloads = {
            payload["normalized_query"]: payload for payload in self._payloads()
        }

        hair = payloads["رنگ مو"]

        self.assertEqual(
            hair["searches_count"],
            2,
        )
        self.assertEqual(
            hair["results_total"],
            5,
        )
        self.assertEqual(
            hair["no_result_count"],
            1,
        )
        self.assertIn(
            hair["query"],
            {
                "رنگ مو",
                "رنگ‌مو",
            },
        )

    def test_click_and_conversion_counts_preserve_day_scope(
        self,
    ):
        payloads = {
            payload["normalized_query"]: payload for payload in self._payloads()
        }

        hair = payloads["رنگ مو"]

        self.assertEqual(
            hair["clicks_count"],
            2,
        )
        self.assertEqual(
            hair["booking_starts"],
            2,
        )
        self.assertEqual(
            hair["booking_completed"],
            1,
        )

        haircut = payloads["کوتاهی مو"]

        self.assertEqual(
            haircut["clicks_count"],
            1,
        )
        self.assertEqual(
            haircut["booking_starts"],
            0,
        )
        self.assertEqual(
            haircut["booking_completed"],
            0,
        )

    def test_query_count_does_not_grow_with_more_queries(
        self,
    ):
        for index in range(30):
            search_log = self._make_log(
                query=f"جستجوی اضافه {index}",
                normalized_query=(f"جستجوی اضافه {index}"),
                results_count=index,
                no_result=(index == 0),
            )

            self._make_click(
                search_log,
                rank=1,
            )

            if index % 2 == 0:
                self._make_conversion(
                    search_log,
                    "booking_started",
                )

        with self.assertNumQueries(3):
            payloads = self._payloads()

        self.assertEqual(
            len(payloads),
            32,
        )

    def test_bulk_upsert_is_idempotent_and_updates_metric(
        self,
    ):
        build_daily_search_metrics(self.day)

        self.assertEqual(
            DailySearchMetric.objects.filter(
                date=self.day,
            ).count(),
            2,
        )

        metric = DailySearchMetric.objects.get(
            date=self.day,
            normalized_query="رنگ مو",
            filters_hash="",
        )

        self.assertEqual(
            metric.searches_count,
            2,
        )
        self.assertEqual(
            metric.clicks_count,
            2,
        )
        self.assertEqual(
            metric.booking_completed,
            1,
        )

        extra_log = self._make_log(
            query="رنگ مو",
            normalized_query="رنگ مو",
            results_count=7,
            no_result=False,
        )
        self._make_click(
            extra_log,
            rank=1,
        )
        self._make_conversion(
            extra_log,
            "booking_completed",
        )

        build_daily_search_metrics(self.day)

        self.assertEqual(
            DailySearchMetric.objects.filter(
                date=self.day,
            ).count(),
            2,
        )

        metric.refresh_from_db()

        self.assertEqual(
            metric.searches_count,
            3,
        )
        self.assertEqual(
            metric.results_total,
            12,
        )
        self.assertEqual(
            metric.no_result_count,
            1,
        )
        self.assertEqual(
            metric.clicks_count,
            3,
        )
        self.assertEqual(
            metric.booking_starts,
            2,
        )
        self.assertEqual(
            metric.booking_completed,
            2,
        )

    def test_filters_hash_remains_backward_compatible(self):
        build_daily_search_metrics(self.day)

        self.assertFalse(
            DailySearchMetric.objects.filter(
                date=self.day,
            )
            .exclude(filters_hash="")
            .exists()
        )
