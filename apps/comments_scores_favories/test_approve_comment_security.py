from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from tests_stage1_helpers import Stage1DomainFactoryMixin

from apps.comments_scores_favories.models import Comments


class ApproveCommentSecurityTests(Stage1DomainFactoryMixin, TestCase):
    def _approve_url(self, comment):
        return reverse(
            "csf:approve_comment",
            args=[comment.pk, comment.comment_user_id],
        )

    def test_approve_comment_requires_login(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)
        customer = self.make_customer()
        comment = Comments.objects.create(
            salon=salon,
            comment_user=customer,
            comment_text="نیازمند تایید",
            is_active=False,
        )

        response = self.client.post(self._approve_url(comment))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])

    def test_approve_comment_forbids_non_manager_user(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)
        customer = self.make_customer()
        comment = Comments.objects.create(
            salon=salon,
            comment_user=customer,
            comment_text="نیازمند تایید",
            is_active=False,
        )

        self.client.force_login(customer.user)
        response = self.client.post(self._approve_url(comment))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "access_denied")

        comment.refresh_from_db()
        self.assertFalse(comment.is_active)
        self.assertIsNone(comment.approved_user_id)

    def test_manager_can_approve_comment_for_owned_salon(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)
        customer = self.make_customer()
        comment = Comments.objects.create(
            salon=salon,
            comment_user=customer,
            comment_text="نیازمند تایید",
            is_active=False,
        )

        self.client.force_login(manager.user)
        response = self.client.post(self._approve_url(comment))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        comment.refresh_from_db()
        self.assertTrue(comment.is_active)
        self.assertEqual(comment.approved_user_id, manager.user_id)

    def test_manager_cannot_approve_comment_for_foreign_salon(self):
        manager = self.make_salon_manager()
        other_manager = self.make_salon_manager()

        own_salon = self.make_salon(manager=manager)
        other_salon = self.make_salon(manager=other_manager)

        customer = self.make_customer()
        self.make_customer()

        self.assertNotEqual(own_salon.pk, other_salon.pk)

        comment = Comments.objects.create(
            salon=other_salon,
            comment_user=customer,
            comment_text="نظر سالن دیگر",
            is_active=False,
        )

        self.client.force_login(manager.user)
        response = self.client.post(self._approve_url(comment))

        self.assertEqual(response.status_code, 404)

        comment.refresh_from_db()
        self.assertFalse(comment.is_active)
        self.assertIsNone(comment.approved_user_id)

    def test_approve_comment_rejects_customer_id_mismatch(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)
        customer = self.make_customer()
        other_customer = self.make_customer()

        comment = Comments.objects.create(
            salon=salon,
            comment_user=customer,
            comment_text="نظر مشتری اصلی",
            is_active=False,
        )

        url = reverse(
            "csf:approve_comment",
            args=[comment.pk, other_customer.pk],
        )

        self.client.force_login(manager.user)
        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)

        comment.refresh_from_db()
        self.assertFalse(comment.is_active)
        self.assertIsNone(comment.approved_user_id)

    def test_approve_comment_is_idempotent_for_already_approved_comment(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)
        customer = self.make_customer()
        comment = Comments.objects.create(
            salon=salon,
            comment_user=customer,
            comment_text="قبلاً تایید شده",
            is_active=True,
            approved_user=manager.user,
        )

        self.client.force_login(manager.user)
        response = self.client.post(self._approve_url(comment))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        comment.refresh_from_db()
        self.assertTrue(comment.is_active)
        self.assertEqual(comment.approved_user_id, manager.user_id)

    def test_approve_comment_rejects_get_method(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)
        customer = self.make_customer()
        comment = Comments.objects.create(
            salon=salon,
            comment_user=customer,
            comment_text="GET ممنوع",
            is_active=False,
        )

        self.client.force_login(manager.user)
        response = self.client.get(self._approve_url(comment))

        self.assertEqual(response.status_code, 405)

        comment.refresh_from_db()
        self.assertFalse(comment.is_active)