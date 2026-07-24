from __future__ import annotations

from datetime import time

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser, Customer, SalonManager, Stylist
from apps.comments_scores_favories.models import Comments, Scoring
from apps.orders.models import Order, OrderDetail
from apps.salons.models import Salon
from apps.services.models import GroupServices, Services


class AppointmentReviewSecurityTests(TestCase):
    def _user(self, *, mobile, name="کاربر", family="تست"):
        return CustomUser.objects.create(
            mobile_number=mobile,
            name=name,
            family=family,
            is_active=True,
        )

    def _customer(self, *, mobile="09124000001"):
        user = self._user(mobile=mobile, name="مشتری", family="تست")
        return Customer.objects.create(user=user)

    def _manager(self, *, mobile="09124000002"):
        user = self._user(mobile=mobile, name="مدیر", family="سالن")
        return SalonManager.objects.create(user=user, is_active=True)

    def _salon(self):
        return Salon.objects.create(
            salon_name="سالن تست",
            salon_manager=self._manager(),
            is_active=True,
            address="تهران",
        )

    def _group(self):
        return GroupServices.objects.create(
            group_title="گروه تست",
            slug="test-group",
            group_image="test/group.jpg",
            is_active=True,
        )

    def _service(self, group):
        service = Services.objects.create(
            service_name="خدمت تست",
            slug="test-service",
            is_active=True,
            is_platform_catalog=True,
            duration_minutes=30,
            base_price=100000,
        )
        service.service_group.add(group)
        return service

    def _stylist(self, salon, service, *, mobile="09124000003"):
        stylist = Stylist.objects.create(
            user=self._user(mobile=mobile, name="متخصص", family="تست"),
            is_active=True,
            expert="تست",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )
        salon.stylists.add(stylist)
        service.stylists.add(stylist)
        return stylist

    def _appointment(self, *, customer=None, completed=True):
        customer = customer or self._customer()
        salon = self._salon()
        group = self._group()
        service = self._service(group)
        salon.services.add(service)
        stylist = self._stylist(salon, service)

        order = Order.objects.create(
            customer=customer,
            salon=salon,
            status="completed" if completed else "pending",
            is_finally=True,
            is_paid=True,
            service_completed_at=timezone.now() if completed else None,
            total_amount=100000,
        )

        appointment = OrderDetail.objects.create(
            order=order,
            service=service,
            stylist=stylist,
            salon=salon,
            price=100000,
            date=timezone.localdate(),
            time=time(10, 0),
            end_time=time(10, 30),
            service_completed_at=timezone.now() if completed else None,
        )
        return appointment

    def test_review_requires_owner(self):
        owner = self._customer(mobile="09124000101")
        other = self._customer(mobile="09124000102")
        appointment = self._appointment(customer=owner, completed=True)

        self.client.force_login(other.user)

        response = self.client.post(
            reverse("orders:appointment_detail", kwargs={"pk": appointment.pk}),
            data={"score": "5", "comment_text": "عالی بود"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Comments.objects.count(), 0)
        self.assertEqual(Scoring.objects.count(), 0)

    def test_review_requires_completed_service(self):
        customer = self._customer(mobile="09124000103")
        appointment = self._appointment(customer=customer, completed=False)

        self.client.force_login(customer.user)

        response = self.client.post(
            reverse("orders:appointment_detail", kwargs={"pk": appointment.pk}),
            data={"score": "5", "comment_text": "عالی بود"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Comments.objects.count(), 0)
        self.assertEqual(Scoring.objects.count(), 0)

    def test_review_rejects_invalid_score(self):
        customer = self._customer(mobile="09124000104")
        appointment = self._appointment(customer=customer, completed=True)

        self.client.force_login(customer.user)

        response = self.client.post(
            reverse("orders:appointment_detail", kwargs={"pk": appointment.pk}),
            data={"score": "6", "comment_text": "عالی بود"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Comments.objects.count(), 0)
        self.assertEqual(Scoring.objects.count(), 0)

    @override_settings(APPOINTMENT_REVIEW_COMMENT_MAX_CHARS=10)
    def test_review_rejects_long_comment(self):
        customer = self._customer(mobile="09124000105")
        appointment = self._appointment(customer=customer, completed=True)

        self.client.force_login(customer.user)

        response = self.client.post(
            reverse("orders:appointment_detail", kwargs={"pk": appointment.pk}),
            data={"score": "5", "comment_text": "الف" * 11},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Comments.objects.count(), 0)
        self.assertEqual(Scoring.objects.count(), 0)

    @override_settings(APPOINTMENT_REVIEW_POST_MAX_BYTES=20)
    def test_review_rejects_large_payload(self):
        customer = self._customer(mobile="09124000106")
        appointment = self._appointment(customer=customer, completed=True)

        self.client.force_login(customer.user)

        response = self.client.post(
            reverse("orders:appointment_detail", kwargs={"pk": appointment.pk}),
            data={"score": "5", "comment_text": "الف" * 100},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Comments.objects.count(), 0)
        self.assertEqual(Scoring.objects.count(), 0)

    def test_review_accepts_valid_submission_once(self):
        customer = self._customer(mobile="09124000107")
        appointment = self._appointment(customer=customer, completed=True)

        self.client.force_login(customer.user)

        url = reverse("orders:appointment_detail", kwargs={"pk": appointment.pk})

        first_response = self.client.post(
            url,
            data={"score": "5", "comment_text": "عالی بود"},
        )
        second_response = self.client.post(
            url,
            data={"score": "4", "comment_text": "دوباره"},
        )

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 302)
        self.assertEqual(Comments.objects.count(), 1)
        self.assertEqual(Scoring.objects.count(), 1)

        appointment.order.refresh_from_db()
        self.assertIsNotNone(appointment.order.review_completed_at)
