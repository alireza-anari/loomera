from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from tests_stage1_helpers import Stage1DomainFactoryMixin

from apps.orders.booking_utils import resolve_booking_sequence


class BookingQARegressionTests(Stage1DomainFactoryMixin, TestCase):
    def _context(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)
        stylist = self.make_stylist()
        service = self.make_service()
        self.connect_service(salon=salon, stylist=stylist, service=service)
        return salon, stylist, service

    def _selection(self, stylist, service):
        return [{
            "serviceId": service.pk,
            "requestedStylistId": str(stylist.user_id),
            "stylistId": str(stylist.user_id),
            "resolvedStylistId": str(stylist.user_id),
        }]

    def _datetime_selection(self, stylist, service):
        date_value = timezone.localdate() + timedelta(days=2)
        return {
            f"{stylist.user_id}_{service.pk}": {
                "date": date_value.isoformat(),
                "time": "10:00",
            }
        }

    def test_inactive_service_is_rejected_before_commit_validation(self):
        salon, stylist, service = self._context()
        service.is_active = False
        service.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            resolve_booking_sequence(
                salon=salon,
                stylist_selections=self._selection(stylist, service),
                datetime_selections=self._datetime_selection(stylist, service),
            )

    def test_inactive_specialist_is_rejected_before_commit_validation(self):
        salon, stylist, service = self._context()
        stylist.is_active = False
        stylist.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            resolve_booking_sequence(
                salon=salon,
                stylist_selections=self._selection(stylist, service),
                datetime_selections=self._datetime_selection(stylist, service),
            )
