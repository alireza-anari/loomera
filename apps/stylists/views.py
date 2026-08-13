from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from apps.accounts.models import Stylist
from apps.services.models import Services
from apps.stylists.models import StylistSchedule, ProfessionalResumeSubmission
from khayyam import JalaliDate
from django.views import View
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus
from apps.stylists.profile_services import build_resume_snapshot
from apps.notifications.models import (
    NotificationAudienceRole,
    NotificationCategory,
    NotificationChannel,
    NotificationPriority,
)
from apps.notifications.services import create_notification


# ---------------------------------------------------------------------------------
def stylist_services_api(request, stylist_id):
    stylist = get_object_or_404(Stylist, user_id=stylist_id)
    services = Services.objects.filter(stylists=stylist, is_active=True)
    data = [{"id": service.id, "name": service.service_name} for service in services]
    return JsonResponse(data, safe=False)


# -----------------------------------------------------------------------------------
class StylistSchedulesAPI(APIView):
    def get(self, request):
        salon_id = request.GET.get("salon_id")
        stylist_ids = request.GET.get("stylist_ids", "").split(",")
        month_jalali = int(request.GET.get("month"))
        year_jalali = int(request.GET.get("year"))

        # تبدیل ماه شمسی به میلادی برای query
        start_jalali = JalaliDate(year_jalali, month_jalali, 1)
        end_jalali = JalaliDate(year_jalali, month_jalali, start_jalali.days_in_month())

        start_gregorian = start_jalali.todate()
        end_gregorian = end_jalali.todate()

        # دریافت schedule ها
        schedules = (
            StylistSchedule.objects.filter(
                salon_id=salon_id,
                stylist_id__in=stylist_ids,
                date__range=[start_gregorian, end_gregorian],
            )
            .select_related("stylist")
            .order_by("date", "start_time")
        )

        # سازماندهی داده
        result = {}
        for schedule in schedules:
            stylist_id = str(schedule.stylist_id)
            date_str = schedule.date.strftime("%Y-%m-%d")  # میلادی

            if stylist_id not in result:
                result[stylist_id] = {}
            if date_str not in result[stylist_id]:
                result[stylist_id][date_str] = []

            result[stylist_id][date_str].append(
                {
                    "start_time": schedule.start_time.strftime("%H:%M"),
                    "end_time": schedule.end_time.strftime("%H:%M"),
                }
            )

        return Response({"schedules": result})


class SubmitProfessionalResumeView(LoginRequiredMixin, View):
    """Create a resume submission from the authenticated stylist to a salon.

    This is a backend-safe endpoint for the future hiring flow. It keeps a
    snapshot of the resume at send time so later profile edits do not rewrite
    what the salon originally received.
    """

    def post(self, request, salon_id):
        if not hasattr(request.user, "stylist"):
            return HttpResponseForbidden("فقط متخصصها می‌توانند رزومه ارسال کنند.")

        stylist = request.user.stylist
        salon = get_object_or_404(Salon, pk=salon_id, is_active=True)
        message = (request.POST.get("message") or "").strip()[:2000]

        submission = ProfessionalResumeSubmission.objects.create(
            stylist=stylist,
            salon=salon,
            message=message,
            resume_snapshot=build_resume_snapshot(stylist, salon=salon),
        )

        membership = SalonMembership.objects.filter(salon=salon, stylist=stylist).first()
        if membership and membership.status == SalonMembershipStatus.ACTIVE:
            messages.info(request, "شما هم‌اکنون عضو فعال این مجموعه هستید.")
            return redirect(
                request.POST.get("next") or salon.get_absolute_url()
            )

        membership_metadata = {
            "source": "professional_resume_submission",
            "requested_by_stylist": True,
            "request_message": message,
            "resume_submission_id": submission.pk,
            "requested_at": timezone.now().isoformat(),
        }

        if membership:
            membership.status = SalonMembershipStatus.PENDING_ACCEPTANCE
            membership.invited_phone = stylist.user.mobile_number or membership.invited_phone
            membership.invited_email = stylist.user.email or membership.invited_email
            membership.role_title = membership.role_title or "متخصص"
            membership.invited_by = None
            membership.accepted_at = None
            membership.ended_at = None
            membership.expires_at = timezone.now() + timedelta(days=14)
            merged_metadata = dict(membership.metadata or {})
            merged_metadata.update(membership_metadata)
            membership.metadata = merged_metadata
            membership.save(
                update_fields=[
                    "status",
                    "invited_phone",
                    "invited_email",
                    "role_title",
                    "invited_by",
                    "accepted_at",
                    "ended_at",
                    "expires_at",
                    "metadata",
                    "updated_at",
                ]
            )
        else:
            membership = SalonMembership.objects.create(
                salon=salon,
                stylist=stylist,
                invited_phone=stylist.user.mobile_number or "",
                invited_email=stylist.user.email or "",
                role_title="متخصص",
                status=SalonMembershipStatus.PENDING_ACCEPTANCE,
                expires_at=timezone.now() + timedelta(days=14),
                show_on_salon_profile=True,
                metadata=membership_metadata,
            )

        manager_user = getattr(getattr(salon, "salon_manager", None), "user", None)
        if manager_user:
            create_notification(
                event_type="stylist_membership_requested",
                category=NotificationCategory.STAFF,
                priority=NotificationPriority.HIGH,
                title="درخواست همکاری متخصص",
                body=f"{stylist.get_fullName()} برای همکاری با {salon.salon_name} درخواست ارسال کرد.",
                action_url=reverse("dashboards:team_member"),
                icon="fa-solid fa-user-plus",
                recipients=[
                    {
                        "user": manager_user,
                        "audience_role": NotificationAudienceRole.MANAGER,
                        "channels": [NotificationChannel.DASHBOARD],
                    }
                ],
                actor=request.user,
                salon=salon,
                related_object=membership,
                metadata={
                    "membership_id": membership.pk,
                    "resume_submission_id": submission.pk,
                    "stylist_id": stylist.user_id,
                    "salon_id": salon.pk,
                },
                dedupe_key=f"stylist_membership_requested:{membership.pk}",
            )

        messages.success(request, "درخواست همکاری شما برای مدیر مجموعه ارسال شد.")
        return redirect(
            request.POST.get("next") or salon.get_absolute_url()
        )


from apps.articles.forms import StaffContentSubmissionForm
from apps.articles.models import StaffContentSubmission
from apps.articles.services import (
    approve_staff_submission,
    reject_staff_submission,
    request_staff_submission_revision,
    submit_staff_content,
)


class SubmitStaffContentView(LoginRequiredMixin, View):
    """Backend endpoint for stylist-created content suggestions.

    The UI can post to this endpoint later without changing current templates.
    The submission is always scoped to an active salon membership and remains
    pending until the salon manager approves it.
    """

    def post(self, request, salon_id):
        if not hasattr(request.user, "stylist"):
            return HttpResponseForbidden("فقط متخصصها می‌توانند محتوا پیشنهاد دهند.")

        stylist = request.user.stylist
        salon = get_object_or_404(Salon, pk=salon_id, is_active=True)
        membership = (
            SalonMembership.objects.filter(
                salon=salon,
                stylist=stylist,
                status=SalonMembership.Status.ACTIVE,
            )
            .select_related("dashboard_permissions")
            .first()
        )
        if membership is None:
            return HttpResponseForbidden("عضویت فعال در این مجموعه پیدا نشد.")

        permissions = getattr(membership, "dashboard_permissions", None)
        submission_type = request.POST.get("submission_type")
        if (
            submission_type == StaffContentSubmission.SubmissionType.ARTICLE
            and permissions
            and not permissions.can_submit_posts
        ):
            return HttpResponseForbidden("دسترسی ارسال مقاله برای شما فعال نیست.")
        if (
            submission_type == StaffContentSubmission.SubmissionType.STORY
            and permissions
            and not permissions.can_submit_stories
        ):
            return HttpResponseForbidden("دسترسی ارسال استوری برای شما فعال نیست.")

        form = StaffContentSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.salon = salon
            submission.stylist = stylist
            submission.status = StaffContentSubmission.Status.DRAFT
            submission.save()
            submit_staff_content(submission, actor=request.user)
            messages.success(request, "محتوای شما برای بررسی مدیر مجموعه ارسال شد.")
        else:
            messages.error(
                request, "ارسال محتوا با خطا مواجه شد. لطفاً اطلاعات را بررسی کنید."
            )
        return redirect(
            request.POST.get("next") or reverse("dashboards:stylist_quick_links")
        )


class ReviewStaffContentSubmissionView(LoginRequiredMixin, View):
    """Salon manager endpoint for approving/rejecting stylist content submissions."""

    def post(self, request, submission_id):
        if not hasattr(request.user, "salon_manager_profile"):
            return HttpResponseForbidden("فقط مدیر مجموعه می‌تواند محتوا را بررسی کند.")

        manager = request.user.salon_manager_profile
        submission = get_object_or_404(
            StaffContentSubmission.objects.select_related("salon", "stylist"),
            pk=submission_id,
            salon__manager=manager,
        )
        action = request.POST.get("action")
        note = (request.POST.get("note") or "").strip()[:2000]
        if action == "approve":
            approve_staff_submission(submission, actor=request.user, note=note)
            messages.success(request, "محتوای پیشنهادی تأیید شد.")
        elif action == "needs_revision":
            request_staff_submission_revision(submission, actor=request.user, note=note)
            messages.info(request, "محتوا برای اصلاح به متخصص برگشت داده شد.")
        elif action == "reject":
            reject_staff_submission(submission, actor=request.user, note=note)
            messages.warning(request, "محتوای پیشنهادی رد شد.")
        else:
            messages.error(request, "عملیات نامعتبر است.")
        return redirect(
            request.POST.get("next") or reverse("dashboards:workspace_settings")
        )
