from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tests_stage1_helpers import Stage1DomainFactoryMixin

from apps.comments_scores_favories.models import Comments, Scoring
from apps.orders.models import OrderDetail


class ReviewSubmissionSecurityTests(Stage1DomainFactoryMixin, TestCase):
    def _make_reviewable_context(self):
        customer = self.make_customer()
        manager = self.make_salon_manager()
        stylist = self.make_stylist()
        salon = self.make_salon(manager=manager)
        service = self.make_service()

        order = self.make_order(
            customer=customer,
            salon=salon,
            status="completed",
            service_completed_at=timezone.now(),
        )
        detail = self.make_order_detail(
            order=order,
            service=service,
            stylist=stylist,
            salon=salon,
            date_value=timezone.localdate(),
            start=timezone.datetime.strptime("10:00", "%H:%M").time(),
            end=timezone.datetime.strptime("10:30", "%H:%M").time(),
            lifecycle_status=OrderDetail.ServiceLifecycleStatus.COMPLETED,
            service_completed_at=timezone.now(),
        )

        return customer, salon, stylist, service, order, detail

    def _url(self, salon):
        return f"{reverse('csf:salon_comment_score')}?salon_id={salon.pk}"

    def test_review_submission_rejects_invalid_salon_id(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.post(
            f"{reverse('csf:salon_comment_score')}?salon_id=abc",
            {
                "comment_text": "نظر تست",
                "score": "5",
            },
        )

        self.assertEqual(response.status_code, 404)

    @override_settings(CSF_REVIEW_POST_MAX_BYTES=64)
    def test_review_submission_rejects_oversized_payload(self):
        customer, salon, stylist, service, _order, _detail = (
            self._make_reviewable_context()
        )
        self.client.force_login(customer.user)

        response = self.client.post(
            self._url(salon),
            {
                "comment_text": "x" * 200,
                "score": "5",
                "stylist": str(stylist.pk),
                "service": str(service.pk),
            },
        )

        self.assertEqual(response.status_code, 413)
        self.assertFalse(Comments.objects.filter(comment_user=customer).exists())
        self.assertFalse(Scoring.objects.filter(scoring_user=customer).exists())

    @override_settings(CSF_REVIEW_COMMENT_MAX_CHARS=12)
    def test_review_submission_rejects_too_long_comment_text(self):
        customer, salon, stylist, service, _order, _detail = (
            self._make_reviewable_context()
        )
        self.client.force_login(customer.user)

        response = self.client.post(
            self._url(salon),
            {
                "comment_text": "این متن بیشتر از حد مجاز است",
                "score": "5",
                "stylist": str(stylist.pk),
                "service": str(service.pk),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Comments.objects.filter(comment_user=customer).exists())
        self.assertFalse(Scoring.objects.filter(scoring_user=customer).exists())

    def test_review_submission_rejects_score_above_allowed_range(self):
        customer, salon, stylist, service, _order, _detail = (
            self._make_reviewable_context()
        )
        self.client.force_login(customer.user)

        response = self.client.post(
            self._url(salon),
            {
                "comment_text": "نظر معتبر",
                "score": "99",
                "stylist": str(stylist.pk),
                "service": str(service.pk),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Comments.objects.filter(comment_user=customer).exists())
        self.assertFalse(Scoring.objects.filter(scoring_user=customer).exists())

    def test_review_submission_accepts_valid_completed_order_review(self):
        customer, salon, stylist, service, _order, _detail = (
            self._make_reviewable_context()
        )
        self.client.force_login(customer.user)

        response = self.client.post(
            self._url(salon),
            {
                "comment_text": "تجربه خوبی بود",
                "score": "5",
                "stylist": str(stylist.pk),
                "service": str(service.pk),
            },
        )

        self.assertEqual(response.status_code, 302)

        comment = Comments.objects.get(comment_user=customer, salon=salon)
        self.assertEqual(comment.comment_text, "تجربه خوبی بود")
        self.assertFalse(comment.is_active)

        scoring = Scoring.objects.get(comment=comment)
        self.assertEqual(scoring.score, 5)

    def test_review_submission_reads_appointment_id_only_from_post(self):
        customer, salon, _stylist, _service, _order, detail = (
            self._make_reviewable_context()
        )
        self.client.force_login(customer.user)

        response = self.client.post(
            f"{self._url(salon)}&appointment_id={detail.pk}",
            {
                "comment_text": "نظر بدون appointment در body",
                "score": "5",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Comments.objects.filter(comment_user=customer).exists())
        self.assertFalse(Scoring.objects.filter(scoring_user=customer).exists())
