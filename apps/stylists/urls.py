from django.urls import path

from .views import stylist_services_api, StylistSchedulesAPI, SubmitProfessionalResumeView, SubmitStaffContentView, ReviewStaffContentSubmissionView

# -----------------------------------------------------------------------------
app_name = "stylists"
urlpatterns = [
    path(
        "api/stylist/<int:stylist_id>/",
        stylist_services_api,
        name="stylist_services_api",
    ),
    path("api/stylists/schedules/", StylistSchedulesAPI.as_view()),
    path("resume/submit/<int:salon_id>/", SubmitProfessionalResumeView.as_view(), name="submit_resume"),
    path("content/submit/<int:salon_id>/", SubmitStaffContentView.as_view(), name="submit_staff_content"),
    path("content/submissions/<int:submission_id>/review/", ReviewStaffContentSubmissionView.as_view(), name="review_staff_content_submission"),
]
