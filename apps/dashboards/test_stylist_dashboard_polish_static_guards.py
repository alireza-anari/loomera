from pathlib import Path
import re
import unittest


BASE_DIR = Path(__file__).resolve().parents[2]
DASHBOARD_VIEWS = BASE_DIR / "apps" / "dashboards" / "views.py"
SALON_MODELS = BASE_DIR / "apps" / "salons" / "models.py"
TEMPLATES_DIR = BASE_DIR / "templates" / "dashboards"


def read(path: Path) -> str:
    assert path.exists(), f"فایل پیدا نشد: {path}"
    return path.read_text(encoding="utf-8")


def extract_class_block(source: str, class_name: str) -> str:
    pattern = rf"class\s+{re.escape(class_name)}\b.*?(?=\nclass\s+\w+|\Z)"
    match = re.search(pattern, source, flags=re.S)
    assert match, f"کلاس {class_name} در views.py پیدا نشد."
    return match.group(0)


def extract_function_block(source: str, function_name: str) -> str:
    pattern = rf"def\s+{re.escape(function_name)}\b.*?(?=\ndef\s+\w+|\nclass\s+\w+|\Z)"
    match = re.search(pattern, source, flags=re.S)
    assert match, f"تابع {function_name} پیدا نشد."
    return match.group(0)


class StylistDashboardPolishStaticGuards(unittest.TestCase):
    def setUp(self):
        self.views = read(DASHBOARD_VIEWS)
        self.models = read(SALON_MODELS)

    def test_stylist_dashboard_view_renders_stylist_template(self):
        block = extract_class_block(self.views, "StylistDashboardView")

        self.assertIn(
            '"dashboards/stylist_dashboard.html"',
            block,
            "StylistDashboardView باید قالب stylist_dashboard.html را رندر کند.",
        )
        self.assertNotIn(
            '"dashboards/salonManager_dashboard.html"',
            block,
            "StylistDashboardView نباید قالب داشبورد مدیر سالن را رندر کند.",
        )
        self.assertIn(
            '"stylist_home"',
            block,
            "StylistDashboardView باید context مخصوص stylist_home را برای قالب خانه متخصص بسازد.",
        )

    def test_stylist_home_payload_is_salon_scoped(self):
        block = extract_function_block(self.views, "_build_stylist_home_payload")

        required_fragments = [
            "stylist=stylist",
            "salon=salon",
            "date__gte=today",
            "services_of_salon=salon",
            "StaffLeaveRequest.objects.filter",
        ]

        for fragment in required_fragments:
            self.assertIn(
                fragment,
                block,
                f"_build_stylist_home_payload باید شامل {fragment} باشد.",
            )

    def test_create_own_booking_permission_exists_on_model(self):
        self.assertIn(
            "can_create_own_bookings",
            self.models,
            "مدل StaffDashboardPermission باید دسترسی مستقل can_create_own_bookings داشته باشد.",
        )
        self.assertRegex(
            self.models,
            r"can_create_own_bookings\s*=\s*models\.BooleanField\(\s*default=True",
            "can_create_own_bookings باید به صورت پیش‌فرض True باشد.",
        )

    def test_stylist_add_booking_uses_create_own_booking_permission(self):
        block = extract_class_block(self.views, "StylistAddBookingView")

        self.assertIn(
            'ctx.can("can_create_own_bookings", True)',
            block,
            "StylistAddBookingView باید از can_create_own_bookings برای ثبت نوبت استفاده کند.",
        )
        self.assertNotIn(
            'ctx.can("can_complete_appointments", True)',
            block,
            "ثبت نوبت متخصص نباید به can_complete_appointments وابسته باشد.",
        )

    def test_disable_membership_permissions_closes_create_booking_permission(self):
        self.assertIn(
            '"can_create_own_bookings"',
            self.views,
            "هنگام پایان همکاری باید can_create_own_bookings هم بسته شود.",
        )

    def test_stylist_overview_uses_current_salon_services(self):
        template = read(TEMPLATES_DIR / "stylist_overview.html")

        self.assertIn(
            "current_salon_services",
            template,
            "قالب پروفایل عضو تیم باید خدمات همین سالن را از current_salon_services بخواند.",
        )
        self.assertNotIn(
            "stylist.services_of_stylist.all",
            template,
            "قالب پروفایل عضو تیم نباید خدمات global متخصص را نمایش دهد.",
        )

    def test_stylist_overview_leave_is_staff_leave_request_scoped(self):
        block = extract_class_block(self.views, "StylistOverviewView")

        self.assertIn(
            "StaffLeaveRequest.objects.filter",
            block,
            "StylistOverviewView باید مرخصی‌ها را از StaffLeaveRequest سالن‌محور بخواند.",
        )
        self.assertIn(
            "salon=salon",
            block,
            "مرخصی‌های پروفایل عضو تیم باید با salon=salon محدود شوند.",
        )
        self.assertIn(
            "StaffLeaveRequest.Status.APPROVED",
            block,
            "در پروفایل عضو تیم فقط مرخصی تاییدشده باید نمایش داده شود.",
        )

    def test_specialist_templates_use_direct_sections_without_workspace_tabs(self):
        templates = [
            "stylist_dashboard.html",
            "stylist_appointments.html",
            "stylist_appointment_detail.html",
            "stylist_profile.html",
            "stylist_quick_links.html",
            "stylist_add_booking.html",
            "stylist_add_customer.html",
            "stylist_finance.html",
            "stylist_withdrawals.html",
            "stylist_add_schedule.html",
            "stylist_add_time_off.html",
            "stylist_content.html",
        ]

        for filename in templates:
            with self.subTest(template=filename):
                source = read(TEMPLATES_DIR / filename)

                self.assertIn(
                    "data-dashboard-workspace-root",
                    source,
                    f"{filename} باید workspace root داشته باشد.",
                )
                self.assertNotIn(
                    "data-dashboard-workspace-tabs-shell",
                    source,
                    f"{filename} نباید کار اصلی را پشت workspace tabs پنهان کند.",
                )
                self.assertNotIn(
                    "data-dashboard-workspace-tab",
                    source,
                    f"{filename} نباید برای جابه‌جایی بین کارهای اصلی tab button داشته باشد.",
                )
                self.assertIn(
                    "data-lm-direct-section",
                    source,
                    f"{filename} باید حداقل یک بخش اصلی مستقیم و همیشه قابل مشاهده داشته باشد.",
                )

    def test_specialist_templates_do_not_render_active_salon_selector_in_body(self):
        templates = [
            "stylist_dashboard.html",
            "stylist_appointments.html",
            "stylist_appointment_detail.html",
            "stylist_profile.html",
            "stylist_quick_links.html",
            "stylist_add_booking.html",
            "stylist_add_customer.html",
            "stylist_finance.html",
            "stylist_withdrawals.html",
            "stylist_add_schedule.html",
            "stylist_add_time_off.html",
            "stylist_content.html",
        ]

        forbidden_fragments = [
            "active_salon_selector",
            "change_active_salon",
            "set_active_salon",
            "انتخاب سالن فعال",
        ]

        for filename in templates:
            with self.subTest(template=filename):
                source = read(TEMPLATES_DIR / filename)
                for fragment in forbidden_fragments:
                    self.assertNotIn(
                        fragment,
                        source,
                        f"{filename} نباید انتخاب سالن فعال داخل بدنه صفحه داشته باشد.",
                    )

    def test_specialist_templates_use_jalali_filters_for_dated_lists(self):
        dated_templates = [
            "stylist_finance.html",
            "stylist_withdrawals.html",
            "stylist_content.html",
        ]

        for filename in dated_templates:
            with self.subTest(template=filename):
                source = read(TEMPLATES_DIR / filename)
                self.assertIn(
                    "{% load jalali_extras %}",
                    source,
                    f"{filename} باید jalali_extras را load کند.",
                )
                self.assertRegex(
                    source,
                    r"jalali_(date|datetime)",
                    f"{filename} باید تاریخ‌های لیستی را شمسی نمایش دهد.",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
