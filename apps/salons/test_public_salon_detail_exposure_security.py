from __future__ import annotations

from datetime import time, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import (
    CustomUser,
    Customer,
    SalonManager,
    Stylist,
    WorkSamples,
)
from apps.articles.models import SalonStory
from apps.comments_scores_favories.models import Favorits
from apps.orders.models import Order, OrderDetail
from apps.salons.models import Salon
from apps.services.models import Services


class PublicSalonDetailExposureSecurityTests(TestCase):
    def _user(self, *, mobile, name="کاربر", family="تست"):
        return CustomUser.objects.create(
            mobile_number=mobile,
            name=name,
            family=family,
            is_active=True,
        )

    def _customer(self, *, mobile):
        return Customer.objects.create(
            user=self._user(mobile=mobile, name="مشتری", family="تست")
        )

    def _manager(self, *, mobile):
        return SalonManager.objects.create(
            user=self._user(mobile=mobile, name="مدیر", family="سالن"),
            is_active=True,
        )

    def _salon(self, *, mobile, name):
        return Salon.objects.create(
            salon_name=name,
            salon_manager=self._manager(mobile=mobile),
            is_active=True,
            address="تهران",
        )

    def _stylist(self, *, mobile):
        return Stylist.objects.create(
            user=self._user(mobile=mobile, name="متخصص", family="تست"),
            is_active=True,
            expert="مو",
            public_visibility=Stylist.PublicVisibility.SALON_ONLY,
        )

    def _service(self, *, name="خدمت تست"):
        return Services.objects.create(
            service_name=name,
            slug=name.replace(" ", "-"),
            is_active=True,
            is_platform_catalog=True,
            duration_minutes=30,
            base_price=100000,
        )

    def _attach_stylist_and_service(self, *, salon, stylist, service):
        salon.stylists.add(stylist)
        salon.services.add(service)
        service.stylists.add(stylist)

    def _order_detail(self, *, salon, customer, stylist, service):
        order = Order.objects.create(
            customer=customer,
            salon=salon,
            status="completed",
            is_finally=True,
            is_paid=True,
            selected_payment_method="pay_in_salon",
            total_amount=100000,
            register_date=timezone.localdate(),
        )
        return OrderDetail.objects.create(
            order=order,
            salon=salon,
            stylist=stylist,
            service=service,
            price=100000,
            date=timezone.localdate() + timedelta(days=1),
            time=time(10, 0),
            end_time=time(10, 30),
        )

    def _favorite_only_story(self, *, salon, title="استوری فقط علاقه‌مندان"):
        return SalonStory.objects.create(
            salon=salon,
            title=title,
            summary="محتوای محدود",
            status=SalonStory.Status.PUBLISHED,
            visibility=SalonStory.Visibility.FAVORITES_ONLY,
            published_at=timezone.now() - timedelta(hours=1),
            expires_at=timezone.now() + timedelta(days=1),
        )

    def test_anonymous_user_cannot_see_favorites_only_salon_story(self):
        salon = self._salon(mobile="09132000101", name="سالن تست")
        self._favorite_only_story(salon=salon, title="استوری محرمانه")

        response = self.client.get(salon.get_absolute_url())

        self.assertEqual(response.status_code, 200)

        titles = {item["title"] for item in response.context["salon_stories_payload"]}
        self.assertNotIn("استوری محرمانه", titles)

    def test_favorite_customer_can_see_favorites_only_salon_story(self):
        salon = self._salon(mobile="09132000102", name="سالن محبوب")
        story = self._favorite_only_story(salon=salon, title="استوری علاقه‌مند")
        customer = self._customer(mobile="09132000103")
        Favorits.objects.create(favorite_user=customer, salon=salon)

        self.client.force_login(customer.user)

        response = self.client.get(salon.get_absolute_url())

        self.assertEqual(response.status_code, 200)

        titles = {item["title"] for item in response.context["salon_stories_payload"]}
        self.assertIn(story.title, titles)

    def test_review_appointment_id_is_scoped_to_current_customer_and_salon(self):
        salon = self._salon(mobile="09132000104", name="سالن تست")
        stylist = self._stylist(mobile="09132000105")
        service = self._service(name="خدمت تست")
        self._attach_stylist_and_service(salon=salon, stylist=stylist, service=service)

        owner = self._customer(mobile="09132000106")
        attacker = self._customer(mobile="09132000107")
        foreign_detail = self._order_detail(
            salon=salon,
            customer=owner,
            stylist=stylist,
            service=service,
        )

        self.client.force_login(attacker.user)

        response = self.client.get(
            salon.get_absolute_url(),
            data={"appointment_id": str(foreign_detail.pk)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["review_appointment_id"], "")

    @override_settings(PUBLIC_SALON_DETAIL_QUERY_MAX_CHARS=20)
    def test_public_salon_detail_rejects_large_query_string(self):
        salon = self._salon(mobile="09132000108", name="سالن تست")

        response = self.client.get(
            salon.get_absolute_url(),
            data={"x": "a" * 100},
        )

        self.assertEqual(response.status_code, 400)

    def test_salon_detail_hides_generic_sample_bound_to_foreign_appointment(self):
        salon = self._salon(mobile="09132000109", name="سالن خودی")
        foreign_salon = self._salon(mobile="09132000110", name="سالن دیگر")
        stylist = self._stylist(mobile="09132000111")
        service = self._service(name="خدمت تست")

        self._attach_stylist_and_service(salon=salon, stylist=stylist, service=service)
        foreign_salon.stylists.add(stylist)
        foreign_salon.services.add(service)

        foreign_customer = self._customer(mobile="09132000112")
        foreign_detail = self._order_detail(
            salon=foreign_salon,
            customer=foreign_customer,
            stylist=stylist,
            service=service,
        )

        sample = WorkSamples.objects.create(
            stylist=stylist,
            service=service,
            sample_image="work_samples/foreign.jpg",
            salon=None,
            appointment=foreign_detail,
            is_active=True,
            is_public=True,
            review_status="published",
        )

        response = self.client.get(salon.get_absolute_url())

        self.assertEqual(response.status_code, 200)

        public_sample_ids = {
            item.pk
            for stylist_item in response.context["stylists"]
            for item in getattr(stylist_item, "public_work_samples", [])
        }
        self.assertNotIn(sample.pk, public_sample_ids)

    def test_stylist_profile_hides_identifiable_sample_without_valid_consent(self):
        salon = self._salon(mobile="09132000113", name="سالن تست")
        stylist = self._stylist(mobile="09132000114")
        service = self._service(name="خدمت تست")
        self._attach_stylist_and_service(salon=salon, stylist=stylist, service=service)

        sample = WorkSamples.objects.create(
            stylist=stylist,
            service=service,
            sample_image="work_samples/private.jpg",
            salon=salon,
            is_active=True,
            is_public=True,
            review_status="published",
            contains_identifiable_client=True,
            client_consent_status="missing",
        )

        response = self.client.get(
            reverse(
                "salons:stylist_profile_slug",
                kwargs={
                    "salon_slug": salon.slug,
                    "stylist_id": stylist.pk,
                },
            )
        )

        self.assertEqual(response.status_code, 200)

        portfolio_ids = {item.pk for item in response.context["portfolio_items"]}
        self.assertNotIn(sample.pk, portfolio_ids)
