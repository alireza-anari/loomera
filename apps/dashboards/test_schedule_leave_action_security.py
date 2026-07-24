from __future__ import annotations

from datetime import time, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser, SalonManager, Stylist
from apps.salons.models import Salon, SalonOpeningHours
from apps.services.models import Services
from apps.stylists.models import (
    StaffLeaveRequest,
    StaffScheduleRequest,
    StylistSchedule,
    StylistTimeOff,
)


class ScheduleLeaveActionSecurityTests(TestCase):
    def setUp(self):
        self.onboarding_guard = patch(
            "apps.dashboards.views._redirect_to_required_onboarding",
            return_value=None,
        )
        self.onboarding_guard.start()
        self.addCleanup(self.onboarding_guard.stop)

    def _user(self, *, mobile, name="کاربر", family="تست"):
        return CustomUser.objects.create(
            mobile_number=mobile,
            name=name,
            family=family,
            is_active=True,
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

    def _stylist(self, *, mobile="09129000003"):
        return Stylist.objects.create(
            user=self._user(mobile=mobile, name="متخصص", family="تست"),
            is_active=True,
            expert="تست",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
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

    def _open_salon_for_date(self, salon, date_value):
        day_of_week = ((date_value.weekday() + 2) % 7) + 1
        return SalonOpeningHours.objects.create(
            salon=salon,
            day_of_week=day_of_week,
            open_time=time(9, 0),
            close_time=time(18, 0),
            is_closed=False,
        )

    def test_schedule_request_action_rejects_foreign_request(self):
        own_salon = self._salon(mobile="09129000101", name="سالن خودی")
        foreign_salon = self._salon(mobile="09129000102", name="سالن دیگر")
        stylist = self._stylist(mobile="09129000103")
        foreign_salon.stylists.add(stylist)

        schedule_request = StaffScheduleRequest.objects.create(
            salon=foreign_salon,
            stylist=stylist,
            date=timezone.localdate() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
            status=StaffScheduleRequest.Status.PENDING,
        )

        self.client.force_login(own_salon.salon_manager.user)

        with patch("apps.dashboards.views.review_schedule_request") as mocked:
            response = self.client.post(
                reverse(
                    "dashboards:staff_schedule_request_action",
                    kwargs={"request_id": schedule_request.pk},
                ),
                data={"action": "approve"},
            )

        self.assertEqual(response.status_code, 404)
        mocked.assert_not_called()

    def test_leave_request_action_rejects_invalid_action(self):
        salon = self._salon(mobile="09129000104", name="سالن تست")
        stylist = self._stylist(mobile="09129000105")
        salon.stylists.add(stylist)

        leave_request = StaffLeaveRequest.objects.create(
            salon=salon,
            stylist=stylist,
            date=timezone.localdate() + timedelta(days=1),
            status=StaffLeaveRequest.Status.PENDING,
            reason="تست",
        )

        self.client.force_login(salon.salon_manager.user)

        with patch("apps.dashboards.views.review_leave_request") as mocked:
            response = self.client.post(
                reverse(
                    "dashboards:staff_leave_request_action",
                    kwargs={"request_id": leave_request.pk},
                ),
                data={"action": "delete"},
            )

        self.assertEqual(response.status_code, 302)
        mocked.assert_not_called()

    @override_settings(DASHBOARD_SCHEDULE_POST_MAX_BYTES=20)
    def test_schedule_request_action_rejects_large_payload(self):
        salon = self._salon(mobile="09129000106", name="سالن تست")
        stylist = self._stylist(mobile="09129000107")
        salon.stylists.add(stylist)

        schedule_request = StaffScheduleRequest.objects.create(
            salon=salon,
            stylist=stylist,
            date=timezone.localdate() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
            status=StaffScheduleRequest.Status.PENDING,
        )

        self.client.force_login(salon.salon_manager.user)

        with patch("apps.dashboards.views.review_schedule_request") as mocked:
            response = self.client.post(
                reverse(
                    "dashboards:staff_schedule_request_action",
                    kwargs={"request_id": schedule_request.pk},
                ),
                data={"action": "approve", "review_note": "الف" * 100},
            )

        self.assertEqual(response.status_code, 302)
        mocked.assert_not_called()

    def test_edit_day_schedule_rejects_foreign_salon(self):
        own_salon = self._salon(mobile="09129000108", name="سالن خودی")
        foreign_salon = self._salon(mobile="09129000109", name="سالن دیگر")
        stylist = self._stylist(mobile="09129000110")
        foreign_salon.stylists.add(stylist)
        date_value = timezone.localdate() + timedelta(days=1)

        self.client.force_login(own_salon.salon_manager.user)

        response = self.client.get(
            reverse(
                "dashboards:edit_day_schedule",
                kwargs={
                    "stylist_pk": stylist.pk,
                    "salon_pk": foreign_salon.pk,
                    "date_iso": date_value.isoformat(),
                },
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_edit_day_schedule_rejects_invalid_service_for_stylist(self):
        salon = self._salon(mobile="09129000111", name="سالن تست")
        stylist = self._stylist(mobile="09129000112")
        service = self._service(name="خدمت سالن")
        invalid_service = self._service(name="خدمت نامعتبر")

        salon.stylists.add(stylist)
        salon.services.add(service)
        salon.services.add(invalid_service)
        service.stylists.add(stylist)

        date_value = timezone.localdate() + timedelta(days=1)
        self._open_salon_for_date(salon, date_value)

        self.client.force_login(salon.salon_manager.user)

        response = self.client.post(
            reverse(
                "dashboards:edit_day_schedule",
                kwargs={
                    "stylist_pk": stylist.pk,
                    "salon_pk": salon.pk,
                    "date_iso": date_value.isoformat(),
                },
            ),
            data={
                "shifts[0][start_time]": "10:00",
                "shifts[0][end_time]": "11:00",
                "shifts[0][service_id]": str(invalid_service.pk),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(StylistSchedule.objects.count(), 0)

    def test_delete_day_schedule_does_not_delete_global_timeoff(self):
        salon = self._salon(mobile="09129000113", name="سالن تست")
        stylist = self._stylist(mobile="09129000114")
        salon.stylists.add(stylist)

        date_value = timezone.localdate() + timedelta(days=1)

        StylistSchedule.objects.create(
            salon=salon,
            stylist=stylist,
            date=date_value,
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        StylistTimeOff.objects.create(
            stylist=stylist,
            date=date_value,
            reason="مرخصی گلوبال",
        )

        self.client.force_login(salon.salon_manager.user)

        response = self.client.post(
            reverse(
                "dashboards:delete_day_schedule",
                kwargs={
                    "stylist_id": stylist.pk,
                    "date_iso": date_value.isoformat(),
                },
            ),
            data={"salon_id": str(salon.pk)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(StylistSchedule.objects.count(), 0)
        self.assertEqual(StylistTimeOff.objects.count(), 1)
