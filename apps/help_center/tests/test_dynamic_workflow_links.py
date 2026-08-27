from django.test import SimpleTestCase
from django.urls import reverse

from apps.help_center.services import _build_guide, _page_route_context


class DynamicWorkflowLinkTests(SimpleTestCase):
    def _group(self, *, audience="customer", steps=None):
        return [{
            "article_key": "test.workflow",
            "title": "راهنمای تست",
            "audience": audience,
            "steps": steps or [],
            "chunks": [],
        }]

    def test_resolves_real_current_appointment_context(self):
        path = reverse("orders:appointment_detail", kwargs={"pk": 42})
        context = _page_route_context(path, "")
        self.assertEqual(context["route_name"], "orders:appointment_detail")
        self.assertEqual(context["kwargs"]["pk"], 42)

    def test_customer_gets_direct_reschedule_link_for_current_appointment(self):
        path = reverse("orders:appointment_detail", kwargs={"pk": 42})
        groups = self._group(steps=[{
            "title": "تغییر زمان",
            "body": "زمان جدید را انتخاب کن.",
            "route_name": "orders:appointments",
            "dynamic_route_name": "orders:reschedule",
            "dynamic_kwargs": {"pk": ["pk"]},
            "context_route_names": ["orders:appointment_detail"],
            "dynamic_link_label": "تغییر زمان همین نوبت",
        }])
        guide = _build_guide(
            groups,
            requester_role="customer",
            page_path=path,
        )
        step = guide["steps"][0]
        self.assertTrue(step["contextual"])
        self.assertTrue(step["url"].endswith("/reschedule/42/"))
        self.assertEqual(step["link_label"], "تغییر زمان همین نوبت")

    def test_unrelated_page_never_reuses_an_id(self):
        path = reverse("help_center:article", kwargs={"slug": "anything"})
        groups = self._group(steps=[{
            "title": "تغییر زمان",
            "body": "زمان جدید را انتخاب کن.",
            "route_name": "orders:appointments",
            "dynamic_route_name": "orders:reschedule",
            "dynamic_kwargs": {"pk": ["pk"]},
            "context_route_names": ["orders:appointment_detail"],
        }])
        guide = _build_guide(
            groups,
            requester_role="customer",
            page_path=path,
        )
        step = guide["steps"][0]
        self.assertFalse(step["contextual"])
        self.assertTrue(step["url"].endswith("/appointments/"))

    def test_cross_role_never_exposes_dynamic_manager_url(self):
        path = reverse(
            "dashboards:appointment_detail",
            kwargs={"salon_id": 3, "appointment_id": 8},
        )
        groups = self._group(
            audience="manager",
            steps=[{
                "title": "مواد مصرفی",
                "body": "مواد همین نوبت را بررسی کن.",
                "dynamic_route_name": "dashboards:appointment_material_usage",
                "dynamic_kwargs": {
                    "salon_id": ["salon_id"],
                    "appointment_id": ["appointment_id"],
                },
                "context_route_names": ["dashboards:appointment_detail"],
            }],
        )
        guide = _build_guide(
            groups,
            requester_role="stylist",
            page_path=path,
        )
        step = guide["steps"][0]
        self.assertFalse(guide["role_matches"])
        self.assertEqual(step["url"], "")
        self.assertFalse(step["contextual"])

    def test_manager_material_link_uses_both_real_url_kwargs(self):
        path = reverse(
            "dashboards:appointment_detail",
            kwargs={"salon_id": 3, "appointment_id": 8},
        )
        groups = self._group(
            audience="manager",
            steps=[{
                "title": "مواد مصرفی",
                "body": "مواد همین نوبت را بررسی کن.",
                "dynamic_route_name": "dashboards:appointment_material_usage",
                "dynamic_kwargs": {
                    "salon_id": ["salon_id"],
                    "appointment_id": ["appointment_id"],
                },
                "context_route_names": ["dashboards:appointment_detail"],
                "dynamic_link_label": "مواد مصرفی همین نوبت",
            }],
        )
        guide = _build_guide(
            groups,
            requester_role="manager",
            page_path=path,
        )
        step = guide["steps"][0]
        self.assertTrue(step["contextual"])
        self.assertIn("/calendar/salon/3/appointment/8/materials/", step["url"])


def test_contextual_step_can_become_current_page_without_redundant_action(self):
    path = reverse("orders:appointment_detail", kwargs={"pk": 42})
    groups = self._group(steps=[{
        "title": "باز کردن نوبت‌های من",
        "body": "نوبت را پیدا کن.",
        "route_name": "orders:appointments",
        "dynamic_route_name": "orders:appointment_detail",
        "dynamic_kwargs": {"pk": ["pk"]},
        "context_route_names": ["orders:appointment_detail"],
        "dynamic_title": "جزئیات همین نوبت",
        "dynamic_body": "الان همین نوبت باز است.",
        "current_page_when_contextual": True,
        "hide_action_when_contextual": True,
        "dynamic_badge_label": "صفحه فعلی",
    }])
    guide = _build_guide(
        groups,
        requester_role="customer",
        page_path=path,
    )
    step = guide["steps"][0]
    self.assertTrue(step["contextual"])
    self.assertTrue(step["current_page"])
    self.assertEqual(step["badge_label"], "صفحه فعلی")
    self.assertEqual(step["title"], "جزئیات همین نوبت")
    self.assertEqual(step["body"], "الان همین نوبت باز است.")
    self.assertEqual(step["url"], "")
