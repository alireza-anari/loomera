from django.test import SimpleTestCase

from apps.help_center.services import _build_guide


class GuidedWorkflowTests(SimpleTestCase):
    def test_builds_clickable_stylist_workflow_for_stylist(self):
        groups = [{
            "article_key": "stylist.leave.request",
            "title": "درخواست مرخصی توسط متخصص",
            "audience": "stylist",
            "steps": [
                {
                    "title": "برنامه و مرخصی من",
                    "body": "صفحه برنامه را باز کن.",
                    "route_name": "dashboards:stylist_schedule",
                    "link_label": "باز کردن برنامه کاری",
                },
                {
                    "title": "درخواست مرخصی",
                    "body": "فرم را کامل کن.",
                    "route_name": "dashboards:stylist_add_time_off",
                    "link_label": "باز کردن فرم",
                },
            ],
            "chunks": [],
        }]
        guide = _build_guide(groups, requester_role="stylist")
        self.assertTrue(guide["role_matches"])
        self.assertEqual(len(guide["steps"]), 2)
        self.assertTrue(guide["steps"][0]["url"].endswith("/stylist/schedule/"))
        self.assertTrue(guide["steps"][1]["url"].endswith("/stylist/time-off/add/"))

    def test_cross_role_workflow_does_not_expose_inaccessible_action_url(self):
        groups = [{
            "article_key": "manager.team.add-stylist",
            "title": "افزودن متخصص",
            "audience": "manager",
            "steps": [{
                "title": "اعضای تیم",
                "body": "اعضای تیم را باز کن.",
                "route_name": "dashboards:team_member",
            }],
            "chunks": [],
        }]
        guide = _build_guide(groups, requester_role="stylist")
        self.assertFalse(guide["role_matches"])
        self.assertEqual(guide["steps"][0]["url"], "")

    def test_near_tie_does_not_become_deterministic_workflow(self):
        groups = [
            {
                "article_key": "customer.booking.flow",
                "title": "رزرو نوبت",
                "audience": "customer",
                "score": 48.1,
                "steps": [
                    {
                        "title": "انتخاب زمان",
                        "body": "یک زمان آزاد انتخاب کن.",
                    }
                ],
                "chunks": [],
            },
            {
                "article_key": "customer.booking.reschedule",
                "title": "تغییر زمان نوبت",
                "audience": "customer",
                "score": 47.9,
                "steps": [
                    {
                        "title": "زمان جدید",
                        "body": "یک زمان جدید انتخاب کن.",
                    }
                ],
                "chunks": [],
            },
        ]

        guide = _build_guide(groups, requester_role="customer")

        self.assertIsNone(guide)

