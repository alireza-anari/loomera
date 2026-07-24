from datetime import timedelta

from django.contrib.contenttypes.models import (
    ContentType,
)
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import WorkSamples
from apps.analytics.models import DailyContentMetric
from apps.analytics.services import (
    _collect_daily_content_metric_payloads,
    build_daily_content_metrics,
)
from apps.articles.models import (
    Article,
    ContentReport,
    SalonStory,
)
from tests_stage1_helpers import (
    Stage1DomainFactoryMixin,
)


class DailyContentMetricsQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.day = timezone.localdate()

        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(
            manager=self.manager,
        )
        self.stylist = self.make_stylist()
        self.service = self.make_service()

        self.connect_service(
            salon=self.salon,
            stylist=self.stylist,
            service=self.service,
        )

        self.article = Article.objects.create(
            title="مقاله تحلیل روزانه",
            slug="daily-content-article",
            summary="خلاصه مقاله تست",
            content="متن مقاله تست",
            author_salon=self.salon,
            view_count=11,
        )

        self.story = SalonStory.objects.create(
            salon=self.salon,
            title="استوری تحلیل روزانه",
            view_count=22,
            click_count=3,
        )

        self.work_sample = WorkSamples.objects.create(
            stylist=self.stylist,
            service=self.service,
            salon=self.salon,
            sample_image=("images/work_samples/" "daily-content-sample.jpg"),
            description="نمونه‌کار تحلیل روزانه",
            like_count=4,
            is_active=True,
            is_public=True,
        )

        self._create_report(self.article)
        self._create_report(self.article)
        self._create_report(self.story)
        self._create_report(self.work_sample)

        old_report = self._create_report(self.article)
        ContentReport.objects.filter(
            pk=old_report.pk,
        ).update(created_at=(timezone.now() - timedelta(days=2)))

    def _create_report(self, target):
        content_type = ContentType.objects.get_for_model(
            target,
            for_concrete_model=False,
        )

        return ContentReport.objects.create(
            target_content_type=content_type,
            target_object_id=target.pk,
            reason=ContentReport.Reason.OTHER,
            description="گزارش تست",
        )

    def _payloads(self):
        return _collect_daily_content_metric_payloads(self.day)

    def test_payload_collection_uses_at_most_five_queries(
        self,
    ):
        # Force the ContentType lookup to exercise its cold-cache path.
        ContentType.objects.clear_cache()

        with self.assertNumQueries(5):
            payloads = self._payloads()

        self.assertEqual(len(payloads), 3)

    def test_payload_values_preserve_existing_semantics(self):
        payloads = {
            (
                payload["content_kind"],
                payload["object_id"],
            ): payload
            for payload in self._payloads()
        }

        article = payloads[
            (
                "article",
                self.article.pk,
            )
        ]
        self.assertEqual(
            article["salon_id"],
            self.salon.pk,
        )
        self.assertEqual(article["views"], 11)
        self.assertEqual(
            article["cta_clicks"],
            0,
        )
        self.assertEqual(
            article["reports_count"],
            2,
        )

        story = payloads[
            (
                "story",
                self.story.pk,
            )
        ]
        self.assertEqual(story["views"], 22)
        self.assertEqual(
            story["cta_clicks"],
            3,
        )
        self.assertEqual(
            story["reports_count"],
            1,
        )

        work_sample = payloads[
            (
                "work_sample",
                self.work_sample.pk,
            )
        ]
        self.assertEqual(
            work_sample["views"],
            0,
        )
        self.assertEqual(
            work_sample["cta_clicks"],
            4,
        )
        self.assertEqual(
            work_sample["reports_count"],
            1,
        )

    def test_report_counts_are_scoped_by_type_and_date(
        self,
    ):
        # IDs may overlap between different database tables. Content type
        # must remain part of the report lookup key.
        payloads = {
            (
                payload["content_kind"],
                payload["object_id"],
            ): payload
            for payload in self._payloads()
        }

        self.assertEqual(
            payloads[
                (
                    "article",
                    self.article.pk,
                )
            ]["reports_count"],
            2,
        )
        self.assertEqual(
            payloads[
                (
                    "story",
                    self.story.pk,
                )
            ]["reports_count"],
            1,
        )

    def test_query_count_does_not_grow_with_more_content(
        self,
    ):
        for index in range(20):
            Article.objects.create(
                title=f"مقاله اضافه {index}",
                slug=f"daily-content-extra-{index}",
                summary="خلاصه",
                content="متن",
                author_salon=self.salon,
                view_count=index,
            )

            SalonStory.objects.create(
                salon=self.salon,
                title=f"استوری اضافه {index}",
                view_count=index,
                click_count=index,
            )

            WorkSamples.objects.create(
                stylist=self.stylist,
                service=self.service,
                salon=self.salon,
                sample_image=("images/work_samples/" f"extra-{index}.jpg"),
                description=f"نمونه‌کار {index}",
                like_count=index,
                is_active=True,
                is_public=True,
            )

        ContentType.objects.clear_cache()

        with self.assertNumQueries(5):
            payloads = self._payloads()

        self.assertEqual(
            len(payloads),
            63,
        )

    def test_bulk_upsert_is_idempotent_and_preserves_booking_fields(
        self,
    ):
        article_content_type = ContentType.objects.get_for_model(
            self.article,
            for_concrete_model=False,
        )

        DailyContentMetric.objects.create(
            content_type=article_content_type,
            object_id=self.article.pk,
            content_kind="article",
            salon=self.salon,
            date=self.day,
            views=1,
            cta_clicks=0,
            booking_starts=7,
            booking_completed=2,
            reports_count=0,
        )

        build_daily_content_metrics(self.day)

        self.assertEqual(
            DailyContentMetric.objects.filter(
                date=self.day,
            ).count(),
            3,
        )

        metric = DailyContentMetric.objects.get(
            content_type=article_content_type,
            object_id=self.article.pk,
            date=self.day,
        )

        self.assertEqual(metric.views, 11)
        self.assertEqual(
            metric.reports_count,
            2,
        )
        self.assertEqual(
            metric.booking_starts,
            7,
        )
        self.assertEqual(
            metric.booking_completed,
            2,
        )

        Article.objects.filter(
            pk=self.article.pk,
        ).update(
            view_count=99,
        )
        self._create_report(self.article)

        build_daily_content_metrics(self.day)

        self.assertEqual(
            DailyContentMetric.objects.filter(
                date=self.day,
            ).count(),
            3,
        )

        metric.refresh_from_db()

        self.assertEqual(metric.views, 99)
        self.assertEqual(
            metric.reports_count,
            3,
        )
        self.assertEqual(
            metric.booking_starts,
            7,
        )
        self.assertEqual(
            metric.booking_completed,
            2,
        )
