from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from apps.accounts.models import Customer, WorkSamples, Stylist, CustomUser
from apps.salons.models import Salon
from apps.services.models import Services


# -----------------------------------------------------------------------------------------------------
class Comments(models.Model):
    comment_user = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="comments_user",
        verbose_name="کاربر نظر دهنده",
        null=True,
        blank=True,
    )
    approved_user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="approved_user",
        verbose_name="کاربر تایید کننده",
        null=True,
        blank=True,
    )
    service = models.ForeignKey(
        Services,
        on_delete=models.CASCADE,
        related_name="comment_services",
        verbose_name="خدمات",
        null=True,
        blank=True,
    )
    salon = models.ForeignKey(
        Salon,
        on_delete=models.CASCADE,
        related_name="comments_salon",
        verbose_name="سالن",
        null=True,
        blank=True,
    )
    stylist = models.ForeignKey(
        Stylist,
        on_delete=models.CASCADE,
        related_name="comments_stylist",
        verbose_name=" آرایشگر",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=False, verbose_name="وضعیت")
    register_date = models.DateField(auto_now_add=True, verbose_name="زمان درج")
    comment_text = models.TextField(verbose_name="متن", null=True, blank=True)

    def __str__(self):
        return f"{self.comment_user} "

    def get_fullName(self):
        return self.comment_user.get_fullName() if self.comment_user else None

    class Meta:
        verbose_name = "نظر"
        verbose_name_plural = "نظرات"
        db_table = "c_comments"


# -----------------------------------------------------------------------------------------------------
class Scoring(models.Model):
    comment = models.OneToOneField(
        Comments,
        on_delete=models.CASCADE,
        related_name="scoring",
        verbose_name="نظر مربوطه",
        null=True,
        blank=True,
    )
    scoring_user = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="scoring_user",
        verbose_name="امتیازدهنده",
        null=True,
        blank=True,
    )
    service = models.ForeignKey(
        Services,
        on_delete=models.CASCADE,
        related_name="scoring_services",
        verbose_name="خدمات",
        null=True,
    )
    salon = models.ForeignKey(
        Salon,
        on_delete=models.CASCADE,
        related_name="scoring_salon",
        verbose_name="سالن",
        null=True,
    )
    stylist = models.ForeignKey(
        Stylist,
        on_delete=models.CASCADE,
        related_name="scoring_stylist",
        verbose_name=" آرایشگر",
        null=True,
    )
    register_date = models.DateField(auto_now_add=True, verbose_name="زمان درج")
    score = models.SmallIntegerField(
        verbose_name="امتیاز", validators=[MinValueValidator(0), MaxValueValidator(5)]
    )

    def __str__(self):
        return f"{self.scoring_user}"

    class Meta:
        verbose_name = "امتیاز"
        verbose_name_plural = "امتیازات"
        db_table = "c_scoring"


# -----------------------------------------------------------------------------------------------------
class Favorits(models.Model):
    favorite_user = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="favorite_user",
        verbose_name="کاربر",
    )
    service = models.ForeignKey(
        Services,
        on_delete=models.CASCADE,
        related_name="favorite_services",
        verbose_name="خدمات",
        null=True,
    )
    salon = models.ForeignKey(
        Salon,
        on_delete=models.CASCADE,
        related_name="favorite_salon",
        verbose_name="سالن",
        null=True,
    )
    stylist = models.ForeignKey(
        Stylist,
        on_delete=models.CASCADE,
        related_name="favorite_stylist",
        verbose_name=" آرایشگر",
        null=True,
    )
    register_date = models.DateField(auto_now_add=True, verbose_name="زمان درج")

    def __str__(self):
        return f"{self.favorite_user}"

    class Meta:
        verbose_name = "علاقه مندی"
        verbose_name_plural = "علاقه مندی ها "
        db_table = "c_favorits"


# ------------------------------------------------------------------------------------------------------
class WorkSampleLike(models.Model):
    user = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
    )
    sample = models.ForeignKey(WorkSamples, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("user", "sample")
