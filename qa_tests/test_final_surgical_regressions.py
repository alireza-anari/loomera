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

    def test_lm_qa_045_unfiltered_team_keeps_historical_members_visible(self):
        source = self.read("apps/dashboards/views.py")
        queryset_block = source[source.index("def _build_team_member_stylists_queryset"):source.index("class TeamMemberView")]
        self.assertIn("Q(stylists_of_salon=salon) | Q(salon_memberships__salon=salon)", queryset_block)
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
        self.assertIn("getJalaliMonthForIsoDate(state.currentDate)", datetime_js)
        self.assertIn("await loadAvailabilityForMonth(targetMonth.year, targetMonth.month)", datetime_js)
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

    def test_lm_qa_050_customer_shell_is_not_rendered_for_manager_or_stylist(self):
        desktop = self.read("templates/partials/shell/desktop_site_header.html")
        mobile = self.read("templates/partials/shell/mobile_app_header.html")
        base = self.read("templates/base.html")
        customer_nav = self.read("templates/partials/shell/customer_mobile_nav.html")
        self.assertLess(desktop.index("user.salon_manager_profile"), desktop.index("user.customer_profile"))
        self.assertLess(desktop.index("user.stylist"), desktop.index("user.customer_profile"))
        self.assertLess(mobile.index("user.salon_manager_profile"), mobile.index("user.customer_profile"))
        self.assertLess(mobile.index("user.stylist"), mobile.index("user.customer_profile"))
        self.assertIn("not request.user.salon_manager_profile and not request.user.stylist", base)
        self.assertLess(customer_nav.index("request.user.salon_manager_profile"), customer_nav.index("request.user.customer_profile"))

    def test_lm_qa_051_specialist_permissions_mean_direct_action_not_total_denial(self):
        dashboard = self.read("apps/dashboards/views.py")
        content = self.read("apps/dashboards/content_views.py")
        legacy = self.read("apps/stylists/views.py")
        self.assertIn('direct_allowed = ctx.can("can_manage_own_schedule", False)', dashboard)
        self.assertIn('direct_allowed = ctx.can("can_request_leave", False)', dashboard)
        self.assertIn('direct_allowed = ctx.can("can_create_own_bookings", True)', dashboard)
        self.assertIn('status="confirmed" if direct_allowed else "pending"', dashboard)
        self.assertIn("_can_publish_directly", content)
        self.assertIn("Permission flags control direct publication vs manager review", content)
        self.assertIn("Submission itself is always available for an active membership", content)
        self.assertNotIn("دسترسی ارسال مقاله برای شما فعال نیست", legacy)
        self.assertNotIn("دسترسی ارسال استوری برای شما فعال نیست", legacy)

    def test_lm_qa_052_leave_review_actions_keep_submitter_value(self):
        source = self.read("templates/dashboards/scheduled_shifts.html")
        self.assertRegex(source, r'name="action" value="approve" data-lm-no-submit-feedback')
        self.assertRegex(source, r'name="action" value="reject" data-lm-no-submit-feedback')

    def test_lm_qa_053_story_suggestions_are_scoped_and_target_prefixed_field(self):
        source = self.read("apps/dashboards/content_views.py")
        template = self.read("templates/dashboards/stylist_content.html")
        self.assertIn("salon: Salon, *, stylist: Stylist | None = None", source)
        self.assertIn("services = services.filter(stylists=stylist)", source)
        self.assertIn('if stylist is None and hasattr(salon, "stylists")', source)
        self.assertIn("salon, stylist=stylist", source)
        self.assertIn("scoped_services = scoped_services.filter(stylists=stylist)", source)
        self.assertIn('prefix="story"', source)
        self.assertIn('data-copy-to="{{ story_form.cta_url.id_for_label }}"', template)
        self.assertIn("document.getElementById(button.dataset.copyTo)", template)

    def test_lm_qa_054_story_media_error_is_precise_prefixed_and_visible(self):
        source = self.read("apps/dashboards/content_views.py")
        template = self.read("templates/dashboards/stylist_content.html")
        self.assertIn("برای ارسال استوری یک تصویر JPG/PNG/WebP یا ویدیوی MP4 انتخاب کن.", source)
        self.assertIn('prefix="story"', source)
        self.assertIn("story_form.media.id_for_label", template)
        self.assertIn("story_form.non_field_errors", template)
        self.assertIn("text-rose-700", template)
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

    def test_manual_retest_ui_contracts_for_team_magazine_and_salon_content(self):
        team = self.read("templates/dashboards/team_member.html")
        article_detail = self.read("templates/articles/article_detail.html")
        magazine = self.read("templates/articles/magazine_home.html")
        salon_detail = self.read("templates/pages/detail_salon.html")
        salon_content = self.read("templates/articles/partials/salon_content_section.html")
        self.assertIn('href="#team-member-section-invites" data-open-team-invite', team)
        self.assertIn('{% block js %}', team)
        self.assertNotIn('{% block title %}تیم\n<script>', team)
        self.assertIn("[overflow-wrap:anywhere]", article_detail)
        self.assertIn("magazine_stories", magazine)
        self.assertIn('name="q"', magazine)
        self.assertIn('name="category"', magazine)
        self.assertIn('name="sort"', magazine)
        self.assertIn('href="#salon-content"', salon_detail)
        self.assertIn('id="salon-content"', salon_content)
        self.assertIn("مقاله‌های مجموعه", salon_content)

    def test_manual_retest_team_invite_is_local_and_integrity_controlled(self):
        source = self.read("apps/dashboards/views.py")
        team = self.read("templates/dashboards/team_member.html")
        helper = source[source.index("def _create_manager_stylist_invite(request):"):source.index("def _cancel_manager_stylist_invite", source.index("def _create_manager_stylist_invite(request):"))]
        invite_view = source[source.index("class ManagerCreateStylistInviteView"):source.index("class ManagerCancelStylistInviteView")]
        self.assertIn('mobile = normalize_mobile(request.POST.get("mobile_number") or "")[:32]', helper)
        self.assertIn('role_title = (request.POST.get("role_title") or "").strip()[:128]', helper)
        self.assertIn('invited_email = (getattr(user, "email", "") or "")[:254]', helper)
        self.assertIn("except IntegrityError:", invite_view)
        self.assertIn('href="#team-member-section-invites" data-open-team-invite', team)
        self.assertIn("event.preventDefault()", team)


if __name__ == "__main__":
    unittest.main(verbosity=2)
