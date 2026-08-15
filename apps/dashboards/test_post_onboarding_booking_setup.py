from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point, Polygon
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import SalonManager
from apps.dashboards.readiness import build_salon_readiness_checklist
from apps.locations.models import Neighborhood
from apps.salons.models import Salon, SalonOpeningHours, SupplementaryInfoView


User = get_user_model()
ROOT = Path(__file__).resolve().parents[2]


class PostOnboardingBookingSetupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            mobile_number="09120001991",
            password="pass1234",
            name="Manager",
            family="Setup",
            email="manager-setup@example.com",
        )
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])

        self.manager = SalonManager.objects.create(
            user=self.user,
            is_active=True,
        )
        self.salon = Salon.objects.create(
            salon_name="Salon Setup",
            salon_manager=self.manager,
            mobile_phone="09121112222",
            landline_phone="02188776655",
            phone_number="09121112222",
            zone=1,
            address="تهران، زعفرانیه",
            address_plaque="10",
            address_unit="2",
            location=Point(51.305, 35.805),
            is_active=False,
        )
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
        self.salon.neighborhood = self.neighborhood
        self.salon.save(update_fields=["neighborhood"])

        for day in range(1, 8):
            SalonOpeningHours.objects.create(
                salon=self.salon,
                day_of_week=day,
                open_time="10:00",
                close_time="19:00",
                is_closed=False,
            )

        SupplementaryInfoView.objects.create(
            salon=self.salon,
            title="پارکینگ",
            description="پارکینگ دارد",
            icon_class="fa-solid fa-car",
            is_active=True,
        )

        self.client.force_login(self.user)

    def test_finishing_description_publishes_salon_without_booking_or_payout(self):
        self.assertFalse(self.salon.is_active)
        self.assertFalse(self.salon.payout_profile_complete)
        self.assertFalse(self.salon.services.exists())
        self.assertFalse(self.salon.stylists.exists())

        response = self.client.post(
            reverse("dashboards:salon_profile_creator_step8"),
            data={"description": "معرفی کوتاه مجموعه"},
        )

        self.salon.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.salon.is_active)
        self.assertEqual(
            response.url,
            f'{reverse("dashboards:salon_profile")}?setup=booking',
        )

    @override_settings(ONLINE_PAYMENT_ENABLED=False)
    def test_readiness_requires_one_service_not_three_and_ignores_finance_quality_blockers(self):
        readiness = build_salon_readiness_checklist(
            self.salon,
            facts={
                "active_services_count": 1,
                "priced_services_count": 1,
                "active_stylists_count": 0,
                "has_stylist_service_link": False,
                "schedule_exists": False,
                "has_bookable_path": False,
                "has_gallery": False,
            },
        )
        items = {item["key"]: item for item in readiness["items"]}

        self.assertTrue(items["services"]["is_done"])
        missing_keys = {item["key"] for item in readiness["missing_items"]}
        item_keys = {item["key"] for item in readiness["items"]}
        self.assertNotIn("payout", missing_keys)
        self.assertNotIn("payout", item_keys)
        self.assertNotIn("verification", missing_keys)
        self.assertNotIn("gallery", missing_keys)

    @override_settings(ONLINE_PAYMENT_ENABLED=True)
    def test_payout_can_be_surfaced_when_online_payment_is_enabled_without_blocking_booking(self):
        readiness = build_salon_readiness_checklist(self.salon)
        item_keys = {item["key"] for item in readiness["items"]}
        missing_keys = {item["key"] for item in readiness["missing_items"]}

        self.assertIn("payout", item_keys)
        self.assertNotIn("payout", missing_keys)

    def test_profile_exposes_three_clear_booking_setup_steps(self):
        self.salon.description = "معرفی مجموعه"
        self.salon.is_active = True
        self.salon.save(update_fields=["description", "is_active"])

        response = self.client.get(reverse("dashboards:salon_profile"))

        self.assertEqual(response.status_code, 200)
        workspace = response.context["salon_profile_workspace"]
        setup_items = workspace["booking_setup_items"]

        self.assertEqual(
            [item["key"] for item in setup_items],
            ["service", "team", "schedule"],
        )
        self.assertEqual(setup_items[0]["url"], reverse("dashboards:add_service"))
        self.assertEqual(setup_items[1]["url"], reverse("dashboards:add_stylist"))
        self.assertEqual(
            setup_items[2]["url"],
            reverse("dashboards:scheduled_shifts"),
        )
        self.assertFalse(workspace["booking_setup_complete"])


class PostOnboardingBookingSetupStaticTests(TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_profile_public_link_is_guarded_when_salon_is_inactive(self):
        template = self.read("templates/dashboards/salon_profile_view.html")
        hero = template.split('id="salon-profile-title"', 1)[1].split(
            'data-lm-task-tabs-anchor="salon-profile"', 1
        )[0]
        self.assertIn("{% if salon.is_active %}", hero)
        self.assertIn('href="#salon-profile-public-page"', hero)

    def test_profile_has_booking_setup_as_first_task(self):
        template = self.read("templates/dashboards/salon_profile_view.html")
        self.assertIn('data-lm-task-key="booking-setup"', template)
        self.assertIn('data-lm-task-label="شروع دریافت نوبت"', template)
        self.assertIn("سه قدم تا دریافت اولین نوبت", template)
        self.assertIn(
            "{% for item in salon_profile_workspace.booking_setup_items %}",
            template,
        )
        self.assertIn("{{ item.title }}", template)
        self.assertIn("{{ item.description }}", template)
        self.assertIn("{{ item.action_label }}", template)

    def test_dashboard_setup_does_not_require_finance_when_payments_are_off(self):
        source = self.read("apps/dashboards/home_components.py")
        self.assertIn('ONLINE_PAYMENT_ENABLED', source)
        self.assertIn('"is_done": description_length > 0', source)
        self.assertIn('"is_done": open_days_count > 0', source)

    def test_payout_save_actions_are_not_sticky_over_form_fields(self):
        template = self.read("templates/dashboards/payout_settings.html")
        payment = template.split('id="finance-payment"', 1)[1].split(
            'id="finance-rules"', 1
        )[0]
        rules = template.split('id="finance-rules"', 1)[1].split(
            'id="finance-history"', 1
        )[0]
        self.assertNotIn("lm-dashboard-sticky-action", payment)
        self.assertNotIn("lm-dashboard-sticky-action", rules)
        self.assertIn("ذخیره اطلاعات پرداخت", payment)
        self.assertIn("ذخیره قوانین مالی", rules)
