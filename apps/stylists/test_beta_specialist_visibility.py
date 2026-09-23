"""Regression coverage for independent salon membership and resume visibility."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Stylist, WorkSamples
from apps.orders.views import _public_booking_stylist_queryset
from apps.salons.models import SalonMembership, SalonMembershipStatus
from apps.stylists.profile_services import can_show_stylist_on_salon_profile
from tests_stage1_helpers import Stage1DomainFactoryMixin


class BetaSpecialistVisibilityTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.salon = self.make_salon(manager=self.make_salon_manager())
        self.stylist = self.make_stylist(
            public_visibility=Stylist.PublicVisibility.RESUME_ONLY,
            resume_headline="Private resume heading",
        )
        self.salon.stylists.add(self.stylist)
        self.membership = SalonMembership.objects.create(
            salon=self.salon,
            stylist=self.stylist,
            status=SalonMembershipStatus.ACTIVE,
            show_on_salon_profile=True,
        )

    def test_resume_only_member_appears_in_salon_and_booking_not_resume(self):
        access = can_show_stylist_on_salon_profile(
            salon=self.salon, stylist=self.stylist
        )
        self.assertTrue(access.allowed)
        self.assertTrue(
            _public_booking_stylist_queryset(self.salon)
            .filter(pk=self.stylist.pk)
            .exists()
        )

        detail = self.client.get(self.salon.get_absolute_url())
        self.assertEqual(detail.status_code, 200)
        matching = [s for s in detail.context["stylists"] if s.pk == self.stylist.pk]
        self.assertEqual(len(matching), 1)
        self.assertFalse(matching[0].salon_profile_url)

        profile = self.client.get(
            reverse(
                "salons:stylist_profile_slug",
                args=[self.salon.slug, self.stylist.pk],
            )
        )
        self.assertEqual(profile.status_code, 404)

        listing = self.client.get(
            reverse(
                "api:v1:public_salon_stylists", kwargs={"salon_slug": self.salon.slug}
            )
        )
        self.assertEqual(listing.status_code, 200)
        data = {item["id"]: item for item in listing.json()["data"]}
        self.assertIn(self.stylist.pk, data)
        self.assertNotIn("Private resume heading", str(data[self.stylist.pk]))

    def test_paused_or_hidden_membership_does_not_appear(self):
        for status, allowed_display in (
            (SalonMembershipStatus.PAUSED, True),
            (SalonMembershipStatus.ACTIVE, False),
        ):
            self.membership.status = status
            self.membership.show_on_salon_profile = allowed_display
            self.membership.save(update_fields=["status", "show_on_salon_profile"])
            self.assertFalse(
                can_show_stylist_on_salon_profile(
                    salon=self.salon, stylist=self.stylist
                ).allowed
            )
            if status == SalonMembershipStatus.PAUSED:
                self.assertFalse(
                    _public_booking_stylist_queryset(self.salon)
                    .filter(pk=self.stylist.pk)
                    .exists()
                )

    def test_hidden_resume_member_is_bookable_without_public_profile(self):
        self.stylist.public_visibility = Stylist.PublicVisibility.HIDDEN
        self.stylist.resume_headline = "PRIVATE_HIDDEN_RESUME_HEADLINE"
        self.stylist.resume_summary = "PRIVATE_HIDDEN_RESUME_SUMMARY"
        self.stylist.save(
            update_fields=[
                "public_visibility",
                "resume_headline",
                "resume_summary",
            ]
        )
        WorkSamples.objects.create(
            stylist=self.stylist,
            sample_image="work_samples/PRIVATE_HIDDEN_RESUME_SAMPLE.jpg",
            salon=self.salon,
            is_active=True,
            is_public=True,
            review_status="published",
        )

        # وضعیت رزومه نباید متخصص فعال را از رزرو سالن حذف کند.
        self.assertTrue(
            _public_booking_stylist_queryset(self.salon)
            .filter(pk=self.stylist.pk)
            .exists()
        )

        salon_response = self.client.get(self.salon.get_absolute_url())
        self.assertEqual(salon_response.status_code, 200)

        matching = [
            item
            for item in salon_response.context["stylists"]
            if item.pk == self.stylist.pk
        ]
        self.assertEqual(len(matching), 1)
        self.assertFalse(matching[0].salon_profile_url)
        self.assertEqual(matching[0].public_work_samples, [])

        # هیچ‌کدام از دو آدرس عمومی نباید رزومه مخفی را نمایش دهند.
        for url in (
            reverse(
                "salons:stylist_profile_slug",
                args=[self.salon.slug, self.stylist.pk],
            ),
            reverse(
                "salons:stylist_profile",
                args=[self.salon.pk, self.stylist.pk],
            ),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 404)

        # متن رزومه نباید از طریق صفحه سالن یا API عمومی منتشر شود.
        api_response = self.client.get(
            reverse(
                "api:v1:public_salon_stylists",
                kwargs={"salon_slug": self.salon.slug},
            )
        )
        self.assertEqual(api_response.status_code, 200)

        api_items = {item["id"]: item for item in api_response.json()["data"]}
        self.assertIn(self.stylist.pk, api_items)

        for private_text in (
            "PRIVATE_HIDDEN_RESUME_HEADLINE",
            "PRIVATE_HIDDEN_RESUME_SUMMARY",
            "PRIVATE_HIDDEN_RESUME_SAMPLE",
        ):
            self.assertNotIn(private_text, salon_response.content.decode("utf-8"))
            self.assertNotIn(private_text, api_response.content.decode("utf-8"))
