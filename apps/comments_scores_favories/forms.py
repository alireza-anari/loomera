from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Stylist
from apps.orders.models import OrderDetail
from apps.services.models import Services

from .models import Comments, Scoring


# ---------------------------------------------------------------------------------
class CommentsForm(forms.ModelForm):
    class Meta:
        model = Comments
        fields = ["comment_text"]
        widgets = {
            "comment_text": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "نظر خود را بنویسید...",
                }
            ),
        }
        labels = {
            "comment_text": "نظر",
        }


# ---------------------------------------------------------------------------------
class ScoringForm(forms.ModelForm):
    class Meta:
        model = Scoring
        fields = ["score"]
        widgets = {
            "score": forms.RadioSelect(
                attrs={"class": "rating-input"},
                choices=[(1, "1"), (2, "2"), (3, "3"), (4, "4"), (5, "5")],
            ),
        }
        labels = {
            "score": "امتیاز",
        }


# ---------------------------------------------------------------------------------
class CommentScoringForm(forms.Form):
    comment_text = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "دیدگاه خود را بنویسید...",
            }
        ),
        required=False,
        label="دیدگاه",
    )
    score = forms.IntegerField(
        min_value=1,
        max_value=5,
        widget=forms.RadioSelect(
            attrs={"class": "rating-input"},
            choices=[(1, "1"), (2, "2"), (3, "3"), (4, "4"), (5, "5")],
        ),
        label="امتیاز",
    )
    stylist = forms.ModelChoiceField(
        queryset=Stylist.objects.none(),
        required=False,
        label="متخصص",
        widget=forms.Select(attrs={"class": "form-control", "id": "stylist_select"}),
    )
    service = forms.ModelChoiceField(
        queryset=Services.objects.none(),
        required=False,
        label="خدمت",
        widget=forms.Select(attrs={"class": "form-control", "id": "service_select"}),
    )

    def __init__(self, *args, **kwargs):
        self.salon = kwargs.pop("salon", None)
        self.customer = kwargs.pop("customer", None)
        super().__init__(*args, **kwargs)

        self.eligible_order_details = OrderDetail.objects.none()

        if not self.salon or not self.customer:
            self.fields["stylist"].queryset = Stylist.objects.none()
            self.fields["service"].queryset = Services.objects.none()
            return

        today = timezone.localdate()
        self.eligible_order_details = (
            OrderDetail.objects.filter(
                order__customer=self.customer,
                salon=self.salon,
                order__service_completed_at__isnull=False,
            )
            .exclude(order__status="cancelled")
            .select_related("stylist", "service")
        )

        eligible_stylist_ids = self.eligible_order_details.values_list(
            "stylist_id", flat=True
        ).distinct()
        eligible_service_ids = self.eligible_order_details.values_list(
            "service_id", flat=True
        ).distinct()

        self.fields["stylist"].queryset = Stylist.objects.filter(
            pk__in=eligible_stylist_ids,
            is_active=True,
        ).distinct()
        self.fields["service"].queryset = Services.objects.filter(
            id__in=eligible_service_ids,
            is_active=True,
        ).distinct()

    def clean(self):
        cleaned_data = super().clean()
        stylist = cleaned_data.get("stylist")
        service = cleaned_data.get("service")

        if not self.customer or not self.salon:
            raise ValidationError("برای ثبت دیدگاه باید به‌عنوان مشتری وارد شوید.")

        eligible_qs = self.eligible_order_details
        if not eligible_qs.exists():
            raise ValidationError(
                "فقط بعد از دریافت خدمت در این مجموعه می‌توانید دیدگاه ثبت کنید."
            )

        if stylist and not eligible_qs.filter(stylist=stylist).exists():
            self.add_error(
                "stylist", "فقط متخصصانی که نزد آن‌ها خدمت گرفته‌اید قابل انتخاب هستند."
            )

        if service and not eligible_qs.filter(service=service).exists():
            self.add_error(
                "service", "فقط خدماتی که قبلاً دریافت کرده‌اید قابل انتخاب هستند."
            )

        if (
            stylist
            and service
            and not eligible_qs.filter(stylist=stylist, service=service).exists()
        ):
            raise ValidationError(
                "این ترکیب خدمت و متخصص در سوابق شما برای این مجموعه ثبت نشده است."
            )

        return cleaned_data


# ---------------------------------------------------------------------------------
