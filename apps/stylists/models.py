from django.db import models
from django.utils import timezone

from apps.salons.models import Salon
from apps.services.models import Services


# --------------------------------------------------------------------------------------------------------------------------------
class StylistSchedule(models.Model):
    stylist = models.ForeignKey(
        "accounts.Stylist",
        on_delete=models.CASCADE,
        related_name="stylist_schedules",
        verbose_name="آرایشگر",
    )
    salon = models.ForeignKey(
        Salon,
        on_delete=models.CASCADE,
        related_name="salon_schedules",
        verbose_name="سالن",
    )
    date = models.DateField(verbose_name="تاریخ ")
    service = models.ForeignKey(
        Services,
        on_delete=models.CASCADE,
        related_name="service_schedules",
        verbose_name="خدمت",
        null=True,
        blank=True,
    )
    start_time = models.TimeField(verbose_name="زمان شروع")
    end_time = models.TimeField(verbose_name="زمان پایان")

    class Meta:
        verbose_name = "برنامه آرایشگر"
        verbose_name_plural = "برنامه‌های آرایشگران"
        unique_together = ("stylist", "date", "start_time")

    def __str__(self):
        return (
            f"{self.stylist} - {self.salon} - {self.service} - {self.start_time}-{self.end_time}"
        )


# -----------------------------------------------------------------------------------------------------------------------------------
class StylistTimeOff(models.Model):
    stylist = models.ForeignKey(
        "accounts.Stylist",
        on_delete=models.CASCADE,
        related_name="time_offs",
        verbose_name="آرایشگر",
    )
    date = models.DateField(verbose_name="تاریخ تعطیلی")
    start_time = models.TimeField(null=True, blank=True, verbose_name="زمان شروع تعطیلی")
    end_time = models.TimeField(null=True, blank=True, verbose_name="زمان پایان تعطیلی")
    reason = models.CharField(max_length=255, null=True, blank=True, verbose_name="دلیل")

    class Meta:
        verbose_name = "تعطیلی آرایشگر"
        verbose_name_plural = "تعطیلی‌های آرایشگر"
        unique_together = ("stylist", "date", "start_time")

    def __str__(self):
        if self.start_time and self.end_time:
            return (
                f"{self.stylist} - تعطیلی در {self.date} از {self.start_time} تا {self.end_time}"
            )
        else:
            return f"{self.stylist} - تعطیلی در تاریخ {self.date}"


# --------------------------------------------------------------------------------------------------------------------------------
class StaffLeaveRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار بررسی"
        APPROVED = "approved", "تأیید شده"
        REJECTED = "rejected", "رد شده"
        CANCELLED = "cancelled", "لغو شده"

    salon = models.ForeignKey(
        Salon,
        on_delete=models.CASCADE,
        related_name="staff_leave_requests",
        verbose_name="سالن",
    )
    stylist = models.ForeignKey(
        "accounts.Stylist",
        on_delete=models.CASCADE,
        related_name="leave_requests",
        verbose_name="آرایشگر",
    )
    date = models.DateField(verbose_name="تاریخ مرخصی")
    start_time = models.TimeField(null=True, blank=True, verbose_name="ساعت شروع")
    end_time = models.TimeField(null=True, blank=True, verbose_name="ساعت پایان")
    reason = models.TextField(blank=True, default="", verbose_name="دلیل")
    status = models.CharField(
        max_length=64,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name="وضعیت",
    )
    reviewed_by = models.ForeignKey(
        "accounts.CustomUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_staff_leave_requests",
        verbose_name="بررسی‌کننده",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان بررسی")
    review_note = models.TextField(blank=True, default="", verbose_name="یادداشت بررسی")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        verbose_name = "درخواست مرخصی آرایشگر"
        verbose_name_plural = "درخواست‌های مرخصی آرایشگران"
        indexes = [
            models.Index(fields=["salon", "stylist", "status"], name="staff_leave_lookup_idx"),
            models.Index(fields=["stylist", "date"], name="staff_leave_date_idx"),
        ]

    def __str__(self):
        return f"{self.stylist} / {self.date} / {self.status}"


# --------------------------------------------------------------------------------------------------------------------------------
class ProfessionalResumeSubmission(models.Model):
    class Status(models.TextChoices):
        SENT = "sent", "ارسال شده"
        VIEWED = "viewed", "مشاهده شده"
        INVITED = "invited", "دعوت به همکاری"
        REJECTED = "rejected", "رد شده"
        SAVED = "saved", "ذخیره شده"
        CANCELLED = "cancelled", "لغو شده"

    stylist = models.ForeignKey(
        "accounts.Stylist",
        on_delete=models.CASCADE,
        related_name="resume_submissions",
        verbose_name="آرایشگر",
    )
    salon = models.ForeignKey(
        Salon,
        on_delete=models.CASCADE,
        related_name="received_resume_submissions",
        verbose_name="سالن",
    )
    message = models.TextField(blank=True, default="", verbose_name="پیام آرایشگر")
    status = models.CharField(
        max_length=64,
        choices=Status.choices,
        default=Status.SENT,
        db_index=True,
        verbose_name="وضعیت",
    )
    resume_snapshot = models.JSONField(default=dict, blank=True, verbose_name="اسنپ‌شات رزومه")
    viewed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان مشاهده")
    responded_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان پاسخ")
    response_note = models.TextField(blank=True, default="", verbose_name="یادداشت پاسخ سالن")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="زمان ارسال")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["stylist", "status"], name="resume_sub_sty_stat_idx"),
            models.Index(fields=["salon", "status"], name="resume_sub_sal_stat_idx"),
        ]
        verbose_name = "ارسال رزومه آرایشگر"
        verbose_name_plural = "ارسال‌های رزومه آرایشگران"

    def __str__(self):
        return f"{self.stylist} -> {self.salon} / {self.status}"


# --------------------------------------------------------------------------------------------------------------------------------
class JobDetails(models.Model):
    stylist = models.ForeignKey(
        "accounts.Stylist",
        on_delete=models.CASCADE,
        related_name="job_details",
        verbose_name="آرایشگر",
    )
    salon = models.ForeignKey(
        Salon,
        on_delete=models.CASCADE,
        related_name="salon_job_details",
        verbose_name="سالن",
    )
    start_date = models.DateField(default=timezone.now, verbose_name="تاریخ شروع")
    end_date = models.DateField(verbose_name="تاریخ پایان", null=True, blank=True)
    employment_type = models.CharField(
        max_length=255, verbose_name="نوع استخدام", null=True, blank=True
    )

    class Meta:
        verbose_name = "جزئیات شغلی"
        verbose_name_plural = "جزئیات شغلی"

    def __str__(self):
        return f"{self.stylist} - {self.salon} "


# --------------------------------------------------------------------------------------------------------------------------------
class EmergencyInfo(models.Model):
    stylist = models.ForeignKey(
        "accounts.Stylist",
        on_delete=models.CASCADE,
        related_name="emergency_info",
        verbose_name="آرایشگر",
    )
    emergency_contact = models.CharField(max_length=255, verbose_name="شماره تماس اضطراری")
    relationship = models.CharField(max_length=255, verbose_name="نسبت با آرایشگر")
    full_name = models.CharField(
        max_length=255, verbose_name="نام و نام خانوادگی  ", null=True, blank=True
    )

    class Meta:
        verbose_name = "اطلاعات اضطراری"
        verbose_name_plural = "اطلاعات اضطراری"

    def __str__(self):
        return f"{self.stylist}  - {self.emergency_contact}"


# ---------------------------------------------------------------------------------------------------------------------------------
class StaffScheduleRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار بررسی"
        APPROVED = "approved", "تأیید شده"
        REJECTED = "rejected", "رد شده"
        CANCELLED = "cancelled", "لغو شده"

    salon = models.ForeignKey(
        Salon,
        on_delete=models.CASCADE,
        related_name="staff_schedule_requests",
        verbose_name="سالن",
    )
    stylist = models.ForeignKey(
        "accounts.Stylist",
        on_delete=models.CASCADE,
        related_name="schedule_requests",
        verbose_name="متخصص",
    )
    service = models.ForeignKey(
        Services,
        on_delete=models.SET_NULL,
        related_name="schedule_requests",
        null=True,
        blank=True,
        verbose_name="خدمت",
    )
    date = models.DateField(verbose_name="تاریخ برنامه")
    start_time = models.TimeField(verbose_name="ساعت شروع")
    end_time = models.TimeField(verbose_name="ساعت پایان")
    note = models.TextField(blank=True, default="", verbose_name="توضیح متخصص")
    status = models.CharField(
        max_length=64,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name="وضعیت",
    )
    reviewed_by = models.ForeignKey(
        "accounts.CustomUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_staff_schedule_requests",
        verbose_name="بررسی‌کننده",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان بررسی")
    review_note = models.TextField(blank=True, default="", verbose_name="یادداشت مدیر")
    created_schedule = models.ForeignKey(
        "stylists.StylistSchedule",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_requests",
        verbose_name="برنامه ساخته‌شده",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    class Meta:
        verbose_name = "درخواست برنامه کاری متخصص"
        verbose_name_plural = "درخواست‌های برنامه کاری متخصصان"
        indexes = [
            models.Index(
                fields=["salon", "stylist", "status"],
                name="staff_sched_req_lookup_idx",
            ),
            models.Index(
                fields=["stylist", "date"],
                name="staff_sched_req_date_idx",
            ),
            models.Index(
                fields=["salon", "status", "date"],
                name="staff_sched_req_queue_idx",
            ),
        ]

    def __str__(self):
        return f"{self.stylist} / {self.salon} / {self.date} / {self.status}"
