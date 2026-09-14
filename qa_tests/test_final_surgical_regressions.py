from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FinalSurgicalRegressionContracts(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_lm_qa_041_favorite_uses_post_and_csrf(self):
        source = self.read("static/js/pages/detail_salon.js")
        self.assertIn('method: "POST"', source)
        self.assertIn('"X-CSRFToken"', source)
        self.assertIn("new URLSearchParams({ salonId", source)
        self.assertNotIn("?salonId=${encodeURIComponent(salonId)}", source)

    def test_lm_qa_042_features_are_optional_in_onboarding_guard(self):
        source = self.read("apps/dashboards/views.py")
        block = source[source.index("def _get_required_onboarding_view_name"):source.index("def _redirect_to_required_onboarding")]
        self.assertNotIn("_is_step7_complete", block)
        self.assertIn("supplementary features are optional", block)

    def test_lm_qa_043_direct_add_is_invitation_only(self):
        source = self.read("apps/dashboards/views.py")
        block = source[source.index("class AddStylistView"):source.index("class EditStylistView")]
        self.assertIn("team-member-section-invites", block)
        get_block = block[block.index("    def get(self, request):"):block.index("    def post(self, request):")]
        post_block = block[block.index("    def post(self, request):"):]
        self.assertLess(get_block.index("return redirect(self._invite_url())"), get_block.index("salon = self._get_salon(request)"))
        self.assertLess(post_block.index("return redirect(self._invite_url())"), post_block.index("salon = self._get_salon(request)"))

    def test_lm_qa_044_manager_edit_does_not_save_global_profile(self):
        source = self.read("apps/dashboards/views.py")
        start = source.index("class EditStylistView")
        next_class = source.index("\nclass ", start + len("class EditStylistView"))
        block = source[start:next_class]
        self.assertIn('"personal_fields_locked": True', block)
        self.assertIn("self._lock_form_fields(user_form, profile_form, emergency_form)", block)
        self.assertNotIn("user_form.save()", block)
        self.assertNotIn("profile_form.save(commit=False)", block)
        self.assertNotIn("emergency_form.save(commit=False)", block)

    def test_lm_qa_045_unfiltered_team_does_not_force_active_only(self):
        source = self.read("apps/dashboards/views.py")
        marker = 'if applied_status == "all":'
        block = source[source.index(marker):source.index('elif applied_status == "active":', source.index(marker))]
        self.assertRegex(block, r'if applied_status == "all":\s+pass')
        self.assertNotIn("active_membership_ids", block)

    def test_lm_qa_046_quick_link_date_uses_jalali_datetime(self):
        source = self.read("templates/dashboards/quick_links/index.html")
        self.assertIn("created_at|jalali_datetime", source)
        self.assertNotIn('created_at|date:"Y/m/d H:i"', source)

    def test_lm_qa_047_card_first_slot_is_carried_into_datetime_step(self):
        view = self.read("apps/orders/views.py")
        template = self.read("templates/orders/select_stylists.html")
        select_js = self.read("static/js/select_stylist.js")
        datetime_js = self.read("static/js/select_datetime.js")
        self.assertIn('"first_slot": (best_available["first_slot"] if best_available else None)', view)
        self.assertIn("data-next-date", template)
        self.assertIn("firstAvailableDate", select_js)
        self.assertIn("selection?.firstAvailableDate", datetime_js)
        self.assertIn("minute <= currentTimeMinutes()", datetime_js)

    def test_lm_qa_048_manager_article_publish_action_survives_submit_feedback(self):
        source = self.read("templates/dashboards/content_hub.html")
        self.assertRegex(source, r'name="article_action" value="publish" data-lm-no-submit-feedback')
        magazine = self.read("templates/articles/magazine_home.html")
        self.assertIn("latest_articles", magazine)

    def test_lm_qa_049_manager_story_publish_action_survives_submit_feedback(self):
        source = self.read("templates/dashboards/content_hub.html")
        self.assertRegex(source, r'name="story_action" value="publish" data-lm-no-submit-feedback')
        detail = self.read("templates/pages/detail_salon.html")
        self.assertIn("salon_stories", detail)

    def test_lm_qa_050_customer_bell_is_not_rendered_for_manager_or_stylist(self):
        desktop = self.read("templates/partials/shell/desktop_site_header.html")
        mobile = self.read("templates/partials/shell/mobile_app_header.html")
        self.assertIn("user.customer_profile", desktop)
        self.assertIn("user.customer_profile", mobile)
        self.assertIn("dashboards:salon_manager_dashboard", desktop)
        self.assertIn("dashboards:stylist_dashboard", desktop)

    def test_lm_qa_051_specialist_permissions_are_backend_enforced_and_deny_by_default(self):
        dashboard = self.read("apps/dashboards/views.py")
        content = self.read("apps/dashboards/content_views.py")
        legacy = self.read("apps/stylists/views.py")
        self.assertIn('ctx.can("can_manage_own_schedule", False)', dashboard)
        self.assertIn('ctx.can("can_request_leave", False)', dashboard)
        self.assertIn("if permissions is None:\n            return False", content)
        self.assertIn("permissions is None or not permissions.can_submit_posts", legacy)
        self.assertIn("permissions is None or not permissions.can_submit_stories", legacy)

    def test_lm_qa_052_leave_review_actions_keep_submitter_value(self):
        source = self.read("templates/dashboards/scheduled_shifts.html")
        self.assertRegex(source, r'name="action" value="approve" data-lm-no-submit-feedback')
        self.assertRegex(source, r'name="action" value="reject" data-lm-no-submit-feedback')

    def test_lm_qa_053_story_suggestions_are_scoped_to_current_stylist(self):
        source = self.read("apps/dashboards/content_views.py")
        self.assertIn("salon: Salon, *, stylist: Stylist | None = None", source)
        self.assertIn("services = services.filter(stylists=stylist)", source)
        self.assertIn("if stylist is None and hasattr(salon, \"stylists\")", source)
        self.assertIn("salon, stylist=stylist", source)
        self.assertIn("scoped_services = scoped_services.filter(stylists=stylist)", source)

    def test_lm_qa_054_story_media_error_is_precise_and_not_duplicated(self):
        source = self.read("apps/dashboards/content_views.py")
        self.assertIn("برای ارسال استوری یک تصویر JPG/PNG/WebP یا ویدیوی MP4 انتخاب کن.", source)
        clean_block = source[source.index("    def clean(self):", source.index("class StylistDashboardContentSubmissionForm")):source.index("class ManagerContentHubView")]
        self.assertNotIn("StaffContentSubmission.SubmissionType.STORY,\n                StaffContentSubmission.SubmissionType.PORTFOLIO", clean_block)

    def test_lm_qa_055_submission_moderation_actions_keep_submitter_value(self):
        source = self.read("templates/dashboards/content_hub.html")
        for value in ("approve", "revision", "reject"):
            self.assertRegex(source, rf'name="submission_action" value="{value}" data-lm-no-submit-feedback')

    def test_lm_qa_056_manager_published_content_keeps_public_salon_render_path(self):
        source = self.read("templates/dashboards/content_hub.html")
        salon_view = self.read("apps/salons/views.py")
        detail = self.read("templates/pages/detail_salon.html")
        self.assertRegex(source, r'name="article_action" value="publish" data-lm-no-submit-feedback')
        self.assertRegex(source, r'name="story_action" value="publish" data-lm-no-submit-feedback')
        self.assertIn("salon_articles", salon_view)
        self.assertIn("salon_stories", salon_view)
        self.assertIn("articles/partials/salon_content_section.html", detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
