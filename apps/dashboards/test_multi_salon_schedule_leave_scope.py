from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class MultiSalonScheduleLeaveStaticGuards(unittest.TestCase):
    """
    این نسخه بدون Django، بدون دیتابیس، بدون GDAL و بدون SpatiaLite اجرا می‌شود.

    هدف:
    بررسی guardهای مهم چندسالنی از روی سورس کد، تا مطمئن شویم:
    - برنامه کاری و مرخصی salon-aware هستند.
    - تایید/رد مدیر با salon=salon محدود شده.
    - تایید برنامه فقط برای سالن همان درخواست StylistSchedule می‌سازد.
    - مرخصی تاییدشده StylistTimeOff سراسری نمی‌سازد.
    - ویرایش خدمات متخصص، خدمات سالن دیگر را حذف نمی‌کند.
    """

    def read_file(self, relative_path: str) -> str:
        path = PROJECT_ROOT / relative_path
        self.assertTrue(path.exists(), f"فایل پیدا نشد: {relative_path}")
        return path.read_text(encoding="utf-8")

    def test_staff_schedule_request_model_is_salon_aware(self):
        source = self.read_file("apps/stylists/models.py")

        self.assertIn(
            "class StaffScheduleRequest",
            source,
            "مدل StaffScheduleRequest باید برای درخواست برنامه کاری ساخته شده باشد.",
        )
        self.assertIn(
            "salon = models.ForeignKey(",
            source,
            "درخواست برنامه کاری باید فیلد salon داشته باشد.",
        )
        self.assertIn(
            'related_name="staff_schedule_requests"',
            source,
            "فیلد salon در StaffScheduleRequest باید related_name مناسب داشته باشد.",
        )
        self.assertIn(
            "stylist = models.ForeignKey(",
            source,
            "درخواست برنامه کاری باید به متخصص وصل باشد.",
        )
        self.assertIn(
            "created_schedule = models.ForeignKey(",
            source,
            "درخواست برنامه کاری باید شیفت ساخته‌شده بعد از تایید را نگه دارد.",
        )

    def test_schedule_request_services_exist(self):
        source = self.read_file("apps/stylists/dashboard_services.py")

        self.assertIn(
            "def validate_staff_schedule_request_window",
            source,
            "تابع validate_staff_schedule_request_window باید وجود داشته باشد.",
        )
        self.assertIn(
            "def create_schedule_request",
            source,
            "تابع create_schedule_request باید وجود داشته باشد.",
        )
        self.assertIn(
            "def review_schedule_request",
            source,
            "تابع review_schedule_request باید وجود داشته باشد.",
        )

    def test_create_schedule_request_must_save_active_salon(self):
        source = self.read_file("apps/stylists/dashboard_services.py")

        self.assertIn(
            "salon=salon",
            source,
            "create_schedule_request باید درخواست را با salon فعال ذخیره کند.",
        )
        self.assertIn(
            "status=StaffScheduleRequest.Status.PENDING",
            source,
            "درخواست برنامه کاری متخصص باید اول pending باشد و مستقیم شیفت نسازد.",
        )

    def test_review_schedule_request_creates_schedule_for_request_salon_only(self):
        source = self.read_file("apps/stylists/dashboard_services.py")

        self.assertIn(
            "StylistSchedule.objects.create(",
            source,
            "تایید برنامه باید StylistSchedule بسازد.",
        )
        self.assertIn(
            "salon=schedule_request.salon",
            source,
            "شیفت تاییدشده باید فقط برای سالن همان درخواست ساخته شود.",
        )
        self.assertIn(
            "stylist=schedule_request.stylist",
            source,
            "شیفت تاییدشده باید برای همان متخصص درخواست ساخته شود.",
        )
        self.assertIn(
            "service=schedule_request.service",
            source,
            "شیفت تاییدشده باید خدمت همان درخواست را استفاده کند.",
        )

    def test_schedule_request_validation_must_check_service_scope(self):
        source = self.read_file("apps/stylists/dashboard_services.py")

        self.assertIn(
            "service.stylists.filter(pk=stylist.pk).exists()",
            source,
            "خدمت انتخابی باید برای همان متخصص فعال باشد.",
        )
        self.assertIn(
            "service.services_of_salon.filter(pk=salon.pk).exists()",
            source,
            "خدمت انتخابی باید برای همان سالن فعال باشد.",
        )

    def test_schedule_request_validation_must_block_overlapping_pending_requests(self):
        source = self.read_file("apps/stylists/dashboard_services.py")

        self.assertIn(
            "pending_conflicts = StaffScheduleRequest.objects.filter(",
            source,
            "باید درخواست‌های برنامه کاری pending برای تداخل بررسی شوند.",
        )
        self.assertIn(
            "start_time__lt=end_time",
            source,
            "بررسی تداخل درخواست برنامه باید start_time__lt=end_time داشته باشد.",
        )
        self.assertIn(
            "end_time__gt=start_time",
            source,
            "بررسی تداخل درخواست برنامه باید end_time__gt=start_time داشته باشد.",
        )

    def test_leave_validation_must_filter_by_active_salon(self):
        source = self.read_file("apps/stylists/dashboard_services.py")

        self.assertIn(
            "leave_conflicts = StaffLeaveRequest.objects.filter(",
            source,
            "باید درخواست‌های مرخصی برای تداخل بررسی شوند.",
        )
        self.assertIn(
            "if salon is not None:",
            source,
            "اعتبارسنجی مرخصی باید salon-aware باشد.",
        )
        self.assertIn(
            "leave_conflicts = leave_conflicts.filter(salon=salon)",
            source,
            "مرخصی سالن A نباید ظرفیت سالن B را قفل کند.",
        )

    def test_create_leave_request_must_not_create_global_stylist_time_off(self):
        source = self.read_file("apps/stylists/dashboard_services.py")

        create_leave_index = source.find("def create_leave_request")
        self.assertNotEqual(
            create_leave_index,
            -1,
            "تابع create_leave_request پیدا نشد.",
        )

        review_leave_index = source.find("def review_leave_request")
        if review_leave_index == -1:
            section = source[create_leave_index:]
        else:
            section = source[create_leave_index:review_leave_index]

        self.assertNotIn(
            "StylistTimeOff.objects.create(",
            section,
            "create_leave_request نباید StylistTimeOff بسازد، چون StylistTimeOff فیلد salon ندارد و اثر سراسری روی همه سالن‌ها می‌گذارد.",
        )

    def test_review_leave_request_must_only_update_staff_leave_request(self):
        source = self.read_file("apps/stylists/dashboard_services.py")

        self.assertIn(
            "def review_leave_request",
            source,
            "تابع review_leave_request باید وجود داشته باشد.",
        )

        review_leave_index = source.find("def review_leave_request")
        section = source[review_leave_index:]

        self.assertIn(
            "leave_request.status",
            section,
            "review_leave_request باید وضعیت همان StaffLeaveRequest را تغییر دهد.",
        )
        self.assertIn(
            "leave_request.reviewed_by",
            section,
            "review_leave_request باید بررسی‌کننده را ثبت کند.",
        )
        self.assertNotIn(
            "StylistTimeOff.objects.create(",
            section,
            "تایید مرخصی سالن‌محور نباید StylistTimeOff سراسری بسازد.",
        )

    def test_manager_schedule_action_view_must_filter_by_manager_salon(self):
        source = self.read_file("apps/dashboards/views.py")

        self.assertIn(
            "class ManagerStaffScheduleRequestActionView",
            source,
            "View تایید/رد درخواست برنامه کاری مدیر باید وجود داشته باشد.",
        )
        self.assertIn(
            "pk=request_id",
            source,
            "درخواست برنامه کاری باید با request_id گرفته شود.",
        )
        self.assertIn(
            "salon=salon",
            source,
            "View مدیر باید درخواست برنامه کاری را با salon مدیر محدود کند.",
        )
        self.assertIn(
            "status=StaffScheduleRequest.Status.PENDING",
            source,
            "مدیر فقط باید درخواست‌های pending را تایید/رد کند.",
        )

    def test_manager_leave_action_view_must_filter_by_manager_salon(self):
        source = self.read_file("apps/dashboards/views.py")

        self.assertIn(
            "class ManagerStaffLeaveRequestActionView",
            source,
            "View تایید/رد درخواست مرخصی مدیر باید وجود داشته باشد.",
        )
        self.assertIn(
            "pk=request_id",
            source,
            "درخواست مرخصی باید با request_id گرفته شود.",
        )
        self.assertIn(
            "salon=salon",
            source,
            "View مدیر باید درخواست مرخصی را با salon مدیر محدود کند.",
        )
        self.assertIn(
            "status=StaffLeaveRequest.Status.PENDING",
            source,
            "مدیر فقط باید درخواست‌های مرخصی pending را تایید/رد کند.",
        )

    def test_scheduled_shifts_view_must_pass_schedule_and_leave_workspaces(self):
        source = self.read_file("apps/dashboards/views.py")

        self.assertIn(
            "_build_manager_schedule_requests(salon)",
            source,
            "ScheduledShiftsView باید درخواست‌های برنامه کاری همان سالن را به template بدهد.",
        )
        self.assertIn(
            '"schedule_request_workspace"',
            source,
            "context صفحه scheduled_shifts باید schedule_request_workspace داشته باشد.",
        )
        self.assertIn(
            "_build_manager_leave_requests(salon)",
            source,
            "ScheduledShiftsView باید درخواست‌های مرخصی همان سالن را به template بدهد.",
        )
        self.assertIn(
            '"leave_request_workspace"',
            source,
            "context صفحه scheduled_shifts باید leave_request_workspace داشته باشد.",
        )

    def test_stylist_schedule_view_must_filter_requests_by_active_salon(self):
        source = self.read_file("apps/dashboards/views.py")

        self.assertIn(
            "StaffScheduleRequest.objects.filter(",
            source,
            "StylistScheduleView باید درخواست‌های برنامه کاری متخصص را بخواند.",
        )
        self.assertIn(
            "stylist=stylist",
            source,
            "درخواست‌های برنامه کاری متخصص باید با stylist محدود شوند.",
        )
        self.assertIn(
            "salon=salon",
            source,
            "درخواست‌های برنامه کاری متخصص باید با سالن فعال محدود شوند.",
        )

    def test_edit_stylist_view_must_not_replace_all_services_globally(self):
        source = self.read_file("apps/dashboards/views.py")

        self.assertNotIn(
            "stylist.services_of_stylist.set(selected_services)",
            source,
            "ویرایش متخصص توسط مدیر یک سالن نباید کل services_of_stylist را set کند؛ این کار خدمات سالن‌های دیگر متخصص را حذف می‌کند.",
        )

    def test_scheduled_shifts_template_has_schedule_and_leave_request_sections(self):
        source = self.read_file("templates/dashboards/scheduled_shifts.html")

        self.assertIn(
            "scheduled-shifts-section-schedule-requests",
            source,
            "قالب scheduled_shifts باید سکشن درخواست برنامه کاری داشته باشد.",
        )
        self.assertIn(
            "schedule_request_workspace.pending",
            source,
            "قالب باید درخواست‌های برنامه کاری pending را نمایش دهد.",
        )
        self.assertIn(
            "scheduled-shifts-section-leave-requests",
            source,
            "قالب scheduled_shifts باید سکشن درخواست مرخصی داشته باشد.",
        )
        self.assertIn(
            "leave_request_workspace.pending",
            source,
            "قالب باید درخواست‌های مرخصی pending را نمایش دهد.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
