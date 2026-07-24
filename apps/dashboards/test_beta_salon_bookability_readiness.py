from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Stylist
from apps.dashboards.readiness import build_salon_readiness_checklist
from tests_stage1_helpers import Stage1DomainFactoryMixin


class BetaSalonBookabilityReadinessTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(manager=self.manager)
        self.future_date = timezone.localdate() + timedelta(days=1)
        self.past_date = timezone.localdate() - timedelta(days=1)

    @staticmethod
    def _item(readiness, key):
        return next(item for item in readiness["items"] if item["key"] == key)

    def test_different_stylists_for_service_and_schedule_are_not_bookable(self):
        service_stylist = self.make_stylist()
        scheduled_stylist = self.make_stylist()
        service = self.make_service()

        self.connect_service(
            salon=self.salon,
            stylist=service_stylist,
            service=service,
        )

        self.salon.stylists.add(scheduled_stylist)
        self.add_schedule(
            stylist=scheduled_stylist,
            salon=self.salon,
            service=service,
            date_value=self.future_date,
            start=timezone.datetime.strptime("10:00", "%H:%M").time(),
            end=timezone.datetime.strptime("12:00", "%H:%M").time(),
        )

        readiness = build_salon_readiness_checklist(self.salon)

        self.assertTrue(self._item(readiness, "stylist_services")["is_done"])
        self.assertTrue(self._item(readiness, "schedule")["is_done"])
        self.assertFalse(self._item(readiness, "bookable_path")["is_done"])
        self.assertFalse(readiness["has_bookable_path"])

    def test_same_stylist_with_linked_service_and_specific_schedule_is_bookable(self):
        stylist = self.make_stylist()
        service = self.make_service()

        self.connect_service(
            salon=self.salon,
            stylist=stylist,
            service=service,
        )
        self.add_schedule(
            stylist=stylist,
            salon=self.salon,
            service=service,
            date_value=self.future_date,
            start=timezone.datetime.strptime("10:00", "%H:%M").time(),
            end=timezone.datetime.strptime("12:00", "%H:%M").time(),
        )

        readiness = build_salon_readiness_checklist(self.salon)

        self.assertTrue(self._item(readiness, "bookable_path")["is_done"])
        self.assertTrue(readiness["has_bookable_path"])

    def test_general_schedule_is_valid_for_a_linked_bookable_service(self):
        stylist = self.make_stylist()
        service = self.make_service()

        self.connect_service(
            salon=self.salon,
            stylist=stylist,
            service=service,
        )
        self.add_schedule(
            stylist=stylist,
            salon=self.salon,
            service=None,
            date_value=self.future_date,
            start=timezone.datetime.strptime("13:00", "%H:%M").time(),
            end=timezone.datetime.strptime("15:00", "%H:%M").time(),
        )

        readiness = build_salon_readiness_checklist(self.salon)

        self.assertTrue(self._item(readiness, "bookable_path")["is_done"])

    def test_past_schedule_does_not_make_salon_bookable(self):
        stylist = self.make_stylist()
        service = self.make_service()

        self.connect_service(
            salon=self.salon,
            stylist=stylist,
            service=service,
        )
        self.add_schedule(
            stylist=stylist,
            salon=self.salon,
            service=service,
            date_value=self.past_date,
            start=timezone.datetime.strptime("10:00", "%H:%M").time(),
            end=timezone.datetime.strptime("12:00", "%H:%M").time(),
        )

        readiness = build_salon_readiness_checklist(self.salon)

        self.assertFalse(self._item(readiness, "schedule")["is_done"])
        self.assertFalse(self._item(readiness, "bookable_path")["is_done"])

    def test_hidden_stylist_does_not_make_public_booking_path_ready(self):
        stylist = self.make_stylist(public_visibility=Stylist.PublicVisibility.HIDDEN)
        service = self.make_service()

        self.connect_service(
            salon=self.salon,
            stylist=stylist,
            service=service,
        )
        self.add_schedule(
            stylist=stylist,
            salon=self.salon,
            service=service,
            date_value=self.future_date,
            start=timezone.datetime.strptime("10:00", "%H:%M").time(),
            end=timezone.datetime.strptime("12:00", "%H:%M").time(),
        )

        readiness = build_salon_readiness_checklist(self.salon)

        self.assertFalse(self._item(readiness, "schedule")["is_done"])
        self.assertFalse(self._item(readiness, "bookable_path")["is_done"])
