from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point, Polygon
from django.http import HttpResponse
from django.test import TestCase
from django.urls import path, reverse

from loomera import urls as project_urls

from apps.accounts.models import SalonManager
from apps.dashboards.views import (
    _get_required_onboarding_view_name,
    _is_step1_complete,
    _is_step2_complete,
    _is_step3_complete,
    _is_step7_complete,
    _is_step8_complete,
)
from apps.locations.models import Neighborhood
from apps.salons.models import Salon, SalonOpeningHours, SupplementaryInfoView


User = get_user_model()


def _support_stub(request):
    return HttpResponse("support")


if not any(getattr(pattern, "name", None) == "support" for pattern in project_urls.urlpatterns):
    project_urls.urlpatterns.append(path("support/", _support_stub, name="support"))


class Stage2SalonSetupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            mobile_number="09120001001",
            password="pass1234",
            name="Manager",
            family="One",
            email="manager1@example.com",
        )
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        self.manager = SalonManager.objects.create(user=self.user, is_active=True)
        self.salon = Salon.objects.create(
            salon_name="",
            salon_manager=self.manager,
            is_active=False,
        )
        self.client.raise_request_exception = False
        self.client.force_login(self.user)

        self.neighborhood = Neighborhood.objects.create(
            name="زعفرانیه",
            polygon=Polygon(
                (
                    (51.30, 35.80),
                    (51.31, 35.80),
                    (51.31, 35.81),
                    (51.30, 35.81),
                    (51.30, 35.80),
                )
            ),
        )

    def _complete_step1(self):
        self.salon.salon_name = "Salon Alpha"
        self.salon.mobile_phone = "09121112222"
        self.salon.landline_phone = "02118877665"
        self.salon.phone_number = self.salon.mobile_phone
        self.salon.save(
            update_fields=[
                "salon_name",
                "mobile_phone",
                "landline_phone",
                "phone_number",
            ]
        )

    def _complete_step2(self):
        self._complete_step1()
        self.salon.zone = 1
        self.salon.neighborhood = self.neighborhood
        self.salon.address = "تهران، زعفرانیه"
        self.salon.address_plaque = "10"
        self.salon.address_unit = "2"
        self.salon.location = Point(51.305, 35.805)
        self.salon.save(
            update_fields=[
                "zone",
                "neighborhood",
                "address",
                "address_plaque",
                "address_unit",
                "location",
            ]
        )

    def _complete_step3(self):
        self._complete_step2()
        SalonOpeningHours.objects.filter(salon=self.salon).delete()
        for day in range(1, 8):
            SalonOpeningHours.objects.create(
                salon=self.salon,
                day_of_week=day,
                open_time="10:00",
                close_time="19:00",
                is_closed=False,
            )

    def _complete_step7(self):
        self._complete_step3()
        SupplementaryInfoView.objects.create(
            salon=self.salon,
            title="جای پارک",
            description="پارکینگ دارد",
            icon_class="fa-solid fa-car",
            is_active=True,
        )

    def test_onboarding_completion_helpers_follow_real_setup_dependencies(self):
        self.assertFalse(_is_step1_complete(self.salon))
        self.assertEqual(
            _get_required_onboarding_view_name(self.user),
            "dashboards:salon_profile_creator_step1",
        )

        self._complete_step1()
        self.assertTrue(_is_step1_complete(self.salon))
        self.assertFalse(_is_step2_complete(self.salon))
        self.assertEqual(
            _get_required_onboarding_view_name(self.user),
            "dashboards:salon_profile_creator_step2",
        )

        self._complete_step2()
        self.assertTrue(_is_step2_complete(self.salon))
        self.assertFalse(_is_step3_complete(self.salon))
        self.assertEqual(
            _get_required_onboarding_view_name(self.user),
            "dashboards:salon_profile_creator_step3",
        )

        self._complete_step3()
        self.assertTrue(_is_step3_complete(self.salon))
        self.assertFalse(_is_step7_complete(self.salon))
        self.assertEqual(
            _get_required_onboarding_view_name(self.user),
            "dashboards:salon_profile_creator_step7",
        )

        self._complete_step7()
        self.assertTrue(_is_step7_complete(self.salon))
        self.assertFalse(_is_step8_complete(self.salon))
        self.assertEqual(
            _get_required_onboarding_view_name(self.user),
            "dashboards:salon_profile_creator_step8",
        )

    def test_step1_post_should_save_basic_salon_profile(self):
        response = self.client.post(
            reverse("dashboards:salon_profile_creator_step1"),
            data={
                "salon_name": "Salon Beta",
                "mobile_phone": "09123456789",
                "landline_phone": "02112345678",
            },
        )
        self.salon.refresh_from_db()
        self.assertNotEqual(response.status_code, 500)
        self.assertEqual(self.salon.salon_name, "Salon Beta")
        self.assertEqual(self.salon.mobile_phone, "09123456789")
        self.assertEqual(self.salon.landline_phone, "02112345678")
        self.assertEqual(self.salon.phone_number, "09123456789")
        self.assertNotEqual(response.url, reverse("dashboards:online_booking"))

    def test_step2_post_should_save_address_and_map_location(self):
        self._complete_step1()
        response = self.client.post(
            reverse("dashboards:salon_profile_creator_step2"),
            data={
                "zone": 1,
                "neighborhood": self.neighborhood.pk,
                "address": "تهران، زعفرانیه",
                "address_plaque": "12",
                "address_unit": "3",
                "latitude": "35.805",
                "longitude": "51.305",
            },
        )
        self.salon.refresh_from_db()
        self.assertNotEqual(response.status_code, 500)
        self.assertEqual(self.salon.zone, 1)
        self.assertEqual(self.salon.neighborhood_id, self.neighborhood.pk)
        self.assertEqual(self.salon.address, "تهران، زعفرانیه")
        self.assertEqual(self.salon.address_plaque, "12")
        self.assertEqual(self.salon.address_unit, "3")
        self.assertIsNotNone(self.salon.location)
        self.assertNotEqual(response.url, reverse("dashboards:online_booking"))

    def test_step3_post_should_create_full_weekly_opening_hours(self):
        self._complete_step2()
        payload = {}
        for day in range(1, 8):
            payload[f"day_{day}_active"] = "on"
            payload[f"day_{day}_open_time"] = "10:00"
            payload[f"day_{day}_close_time"] = "19:00"

        response = self.client.post(
            reverse("dashboards:salon_profile_creator_step3"),
            data=payload,
        )
        self.assertNotEqual(response.status_code, 500)
        self.assertEqual(SalonOpeningHours.objects.filter(salon=self.salon).count(), 7)
        self.assertNotEqual(response.url, reverse("dashboards:online_booking"))

    def test_step8_post_should_save_long_description(self):
        self._complete_step7()
        description = ("توضیح سالن " * 25).strip()
        response = self.client.post(
            reverse("dashboards:salon_profile_creator_step8"),
            data={"description": description},
        )
        self.salon.refresh_from_db()
        self.assertNotEqual(response.status_code, 500)
        self.assertEqual((self.salon.description or "").strip(), description)
        self.assertTrue(_is_step8_complete(self.salon))
        self.assertNotEqual(response.url, reverse("dashboards:online_booking"))

    def test_payout_settings_post_should_save_finance_and_cancellation_policy(self):
        self._complete_step7()
        self.salon.description = "توضیح سالن " * 25
        self.salon.save(update_fields=["description"])

        response = self.client.post(
            reverse("dashboards:payout_settings"),
            data={
                "payout_account_holder_name": "مدیر سالن آلفا",
                "payout_iban": "IR820540102680020817909002",
                "payout_bank_name": "ملت",
                "payout_contact_mobile": "09121234567",
                "cancellation_window_hours": 12,
                "cancellation_refund_percent": 80,
                "payout_delay_days": 2,
                "cancellation_policy_note": "لغو تا ۱۲ ساعت قبل با ۸۰ درصد بازگشت به کیف پول.",
            },
        )
        self.salon.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.salon.payout_account_holder_name, "مدیر سالن آلفا")
        self.assertEqual(self.salon.payout_iban, "IR820540102680020817909002")
        self.assertEqual(self.salon.payout_contact_mobile, "09121234567")
        self.assertEqual(self.salon.cancellation_window_hours, 12)
        self.assertEqual(self.salon.cancellation_refund_percent, 80)
        self.assertEqual(self.salon.payout_delay_days, 2)
