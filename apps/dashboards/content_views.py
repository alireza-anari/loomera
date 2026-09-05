from __future__ import annotations

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views import View
from django.http import Http404
from apps.articles.forms import (
    validate_article_cover_image_upload,
    validate_staff_content_media_upload,
)

from apps.articles.models import (
    Article,
    ArticleTag,
    ContentModerationEvent,
    SalonStory,
    SalonStoryItem,
    StaffContentSubmission,
)
from apps.dashboards.layout import build_dashboard_context
from apps.notifications.models import (
    NotificationAudienceRole,
    NotificationCategory,
    NotificationChannel,
    NotificationPriority,
)
from apps.notifications.services import create_notification
from apps.salons.membership import get_active_salon_for_stylist
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus
from apps.services.models import GroupServices, Services
from apps.accounts.models import Stylist

INPUT_CLASS = "w-full rounded-2xl border border-loomera-borderSoft bg-white px-4 py-3 text-sm font-bold text-loomera-textPrimary outline-none transition focus:border-loomera-primary/40 focus:ring-4 focus:ring-loomera-primary/10"
TEXTAREA_CLASS = INPUT_CLASS + " min-h-[9rem] leading-7"
CHECK_CLASS = "h-5 w-5 rounded border-loomera-borderSoft text-loomera-primary focus:ring-loomera-primary/30"

CONSENT_STATUS_CHOICES = (
    ("not_required", "مشتری قابل تشخیص نیست / رضایت لازم نیست"),
    ("obtained", "رضایت مشتری دریافت شده است"),
    ("needs_blur", "فقط با محو کردن چهره یا مشخصات قابل انتشار است"),
    ("pending", "رضایت در حال پیگیری است"),
    ("not_obtained", "رضایت دریافت نشده؛ منتشر نشود"),
)


def _tag_slug(title: str) -> str:
    base = slugify(title or "tag", allow_unicode=True)[:100] or "tag"
    candidate = base
    suffix = 1
    while ArticleTag.objects.filter(slug=candidate).exists():
        suffix += 1
        candidate = f"{base}-{suffix}"[:115]
    return candidate


STAFF_SUBMISSION_META_MARKER = "\n\nگزینه‌های پیشنهادی برای مدیر:"
STAFF_SUBMISSION_META_TITLES = (
    "گزینه‌های پیشنهادی برای مدیر:",
    "برچسب‌های مرتبط:",
    "برچسب‌های جدید:",
    "خدمات مرتبط:",
    "گروه‌های خدمت:",
    "نمایش پیشنهادی:",
    "نوع دکمه استوری:",
    "متن دکمه:",
    "لینک دکمه:",
)


def _public_submission_body(value: str) -> str:
    """Return only the user-facing part of a staff submission.

    The dashboard stores suggestion notes after a Persian marker so managers can
    review tags/services/CTA before publishing. Public article/story pages must
    never show those internal review notes.
    """
    text = (value or "").strip()
    if not text:
        return ""
    if STAFF_SUBMISSION_META_MARKER in text:
        text = text.split(STAFF_SUBMISSION_META_MARKER, 1)[0].strip()
    cleaned_lines = []
    for line in text.splitlines():
        normalized = line.strip()
        if any(
            normalized.startswith(prefix) for prefix in STAFF_SUBMISSION_META_TITLES
        ):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _summary_from_text(value: str, length: int = 220) -> str:
    text = " ".join(_public_submission_body(value).split())
    return text[:length]


def _attach_new_tags(article: Article, raw_tags: str) -> None:
    for title in [
        part.strip()
        for part in (raw_tags or "").replace("،", ",").split(",")
        if part.strip()
    ]:
        tag, _ = ArticleTag.objects.get_or_create(
            title=title[:80],
            defaults={"slug": _tag_slug(title), "is_active": True},
        )
        article.tags.add(tag)


def _build_story_link_suggestions(salon: Salon):
    suggestions = []
    try:
        if getattr(salon, "salon_slug", ""):
            suggestions.append(
                {
                    "label": "صفحه مجموعه",
                    "url": reverse(
                        "salons:detail_salon_slug",
                        kwargs={"salon_slug": salon.salon_slug},
                    ),
                }
            )
        elif getattr(salon, "pk", None):
            suggestions.append(
                {
                    "label": "صفحه مجموعه",
                    "url": reverse(
                        "salons:detail_salon", kwargs={"salon_id": salon.pk}
                    ),
                }
            )
    except Exception:
        suggestions.append(
            {"label": "صفحه مجموعه", "url": f"/detail_salon/{salon.pk}/"}
        )
    try:
        services = salon.services.all().distinct().order_by("service_name")[:10]
    except Exception:
        try:
            services = (
                Services.objects.filter(services_of_salon=salon)
                .distinct()
                .order_by("service_name")[:10]
            )
        except Exception:
            services = []
    service_ids = []
    for service in services:
        service_ids.append(getattr(service, "pk", None))
        suggestions.append(
            {
                "label": f"خدمت: {service.service_name}",
                "url": f"/search/?q={service.service_name}",
            }
        )
    try:
        groups = (
            GroupServices.objects.filter(
                services_of_group__in=[sid for sid in service_ids if sid]
            )
            .distinct()
            .order_by("group_title")[:8]
        )
    except Exception:
        groups = []
    for group in groups:
        suggestions.append(
            {
                "label": f"گروه خدمت: {group.group_title}",
                "url": f"/search/?q={group.group_title}",
            }
        )
    stylists = []
    if hasattr(salon, "stylists"):
        try:
            # Stylist.Meta ordering in older data can contain the invalid path ``user.id`` or ``id``.
            # Always override ordering here so the content dashboard never crashes while
            # building story link suggestions.
            stylists = salon.stylists.all().order_by("user_id")[:6]
        except Exception:
            stylists = []
    for stylist in stylists:
        try:
            label_name = (
                stylist.get_fullName()
                if hasattr(stylist, "get_fullName")
                else str(stylist)
            )
            suggestions.append(
                {
                    "label": f"متخصص: {label_name}",
                    "url": reverse(
                        "salons:stylist_profile_slug",
                        kwargs={
                            "salon_slug": salon.salon_slug,
                            "stylist_id": stylist.pk,
                        },
                    ),
                }
            )
        except Exception:
            suggestions.append(
                {
                    "label": f"متخصص: {getattr(stylist, 'display_name', str(stylist))}",
                    "url": f"/detail_salon/{salon.pk}/stylists/{stylist.pk}/",
                }
            )
    return suggestions


def _apply_dashboard_widgets(form: forms.Form) -> forms.Form:
    for name, field in form.fields.items():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault("class", CHECK_CLASS)
        elif isinstance(widget, forms.Textarea):
            widget.attrs.setdefault("class", TEXTAREA_CLASS)
        elif isinstance(widget, forms.CheckboxSelectMultiple):
            widget.attrs.setdefault("class", "space-y-2")
        elif isinstance(widget, (forms.FileInput, forms.ClearableFileInput)):
            widget.attrs.setdefault(
                "class",
                "block w-full rounded-2xl border border-dashed border-loomera-borderSoft bg-loomera-bgSubtle px-4 py-3 text-sm text-loomera-textSecondary file:ml-4 file:rounded-full file:border-0 file:bg-loomera-primary file:px-4 file:py-2 file:text-xs file:font-black file:text-white",
            )
        else:
            widget.attrs.setdefault("class", INPUT_CLASS)
    return form


def _raw_upload_content_type(files, field_name, *, prefix=None):
    if not files:
        return ""

    field_names = []
    if prefix:
        field_names.append(f"{prefix}-{field_name}")
    field_names.append(field_name)

    for candidate in field_names:
        uploaded_file = files.get(candidate)
        if uploaded_file:
            return getattr(uploaded_file, "content_type", "") or ""

    return ""


def _manager_salon(user):
    return (
        Salon.objects.select_related("salon_manager__user")
        .filter(salon_manager__user=user)
        .first()
    )


def _unique_article_slug(title: str) -> str:
    base = slugify(title or "مقاله", allow_unicode=True)[:190] or "article"
    candidate = base
    suffix = 1
    while Article.objects.filter(slug=candidate).exists():
        suffix += 1
        candidate = f"{base}-{suffix}"[:220]
    return candidate


def _record_content_event(
    target,
    *,
    event_type: str,
    actor,
    old_status: str = "",
    new_status: str = "",
    note: str = "",
):
    try:
        ContentModerationEvent.objects.create(
            target_content_type=ContentType.objects.get_for_model(
                target, for_concrete_model=False
            ),
            target_object_id=target.pk,
            event_type=event_type,
            actor=actor,
            old_status=old_status or "",
            new_status=new_status or getattr(target, "status", ""),
            note=note or "",
            metadata={"source": "dashboard"},
        )
    except Exception:
        pass


def _notify_content_event(
    *,
    salon,
    actor,
    event_type: str,
    title: str,
    body: str,
    target,
    action_url: str,
    include_admins: bool = True,
    stylist=None,
):
    recipients = []
    seen_user_ids = set()

    def add_recipient(user, role):
        if not user or getattr(user, "pk", None) in seen_user_ids:
            return
        seen_user_ids.add(user.pk)
        recipients.append(
            {
                "user": user,
                "audience_role": role,
                "channels": [NotificationChannel.DASHBOARD],
            }
        )

    manager_user = getattr(getattr(salon, "salon_manager", None), "user", None)
    add_recipient(manager_user, NotificationAudienceRole.MANAGER)
    if stylist and getattr(stylist, "user", None):
        add_recipient(stylist.user, NotificationAudienceRole.STYLIST)
    if include_admins:
        User = get_user_model()
        admin_q = (
            Q(is_superuser=True)
            | Q(is_admin=True)
            | Q(platform_admin_roles__isnull=False)
        )
        for admin in (
            User.objects.filter(is_active=True).filter(admin_q).distinct()[:10]
        ):
            add_recipient(admin, NotificationAudienceRole.ADMIN)
    if not recipients:
        return None
    return create_notification(
        event_type=event_type,
        title=title,
        body=body,
        recipients=recipients,
        category=NotificationCategory.CONTENT,
        priority=NotificationPriority.NORMAL,
        action_url=action_url,
        icon="fa-regular fa-newspaper",
        actor=actor,
        salon=salon,
        related_object=target,
        metadata={
            "source": "dashboard_content",
            "salon_id": getattr(salon, "pk", None),
        },
    )


class ManagerArticleForm(forms.ModelForm):
    client_consent_status = forms.ChoiceField(
        choices=CONSENT_STATUS_CHOICES, required=False, label="وضعیت رضایت مشتری"
    )
    new_tags = forms.CharField(
        required=False,
        label="برچسب‌های جدید",
        help_text="اگر برچسب موردنظر در لیست نیست، چند برچسب را با ویرگول جدا کن؛ مثل رنگ مو، مراقبت پوست",
    )

    class Meta:
        model = Article
        fields = [
            "title",
            "summary",
            "content",
            "cover_image",
            "content_type",
            "category",
            "tags",
            "visibility",
            "related_services",
            "related_service_groups",
            "contains_identifiable_client",
            "client_consent_status",
            "manager_approved_responsibility",
        ]
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3}),
            "content": forms.Textarea(attrs={"rows": 8}),
        }

    def __init__(self, *args, salon=None, **kwargs):
        files = kwargs.get("files")
        if files is None and len(args) > 1:
            files = args[1]

        prefix = kwargs.get("prefix")
        self._raw_cover_image_content_type = _raw_upload_content_type(
            files,
            "cover_image",
            prefix=prefix,
        )

        super().__init__(*args, **kwargs)
        if salon is not None:
            self.fields["related_services"].queryset = (
                salon.services.all().distinct().order_by("service_name")
            )
        self.fields["tags"].required = False
        self.fields["tags"].queryset = ArticleTag.objects.all().order_by("title")
        self.fields["tags"].widget = forms.CheckboxSelectMultiple()
        self.fields["tags"].help_text = (
            "برچسب‌های مرتبط را با کلیک انتخاب کن. اگر برچسب موردنظرت نبود، در فیلد برچسب‌های جدید بنویس."
        )
        self.fields["category"].required = False
        self.fields["category"].help_text = (
            "اختیاری است؛ اگر دسته مرتبط داری انتخاب کن تا مقاله بهتر در مجله فهرست شود."
        )
        self.fields["related_services"].required = False
        self.fields["related_services"].widget = forms.CheckboxSelectMultiple()
        self.fields["related_services"].help_text = (
            "اختیاری است؛ خدمات مرتبط باعث می‌شود کاربر راحت‌تر به رزرو برسد."
        )
        self.fields["related_service_groups"].required = False
        self.fields["related_service_groups"].widget = forms.CheckboxSelectMultiple()
        self.fields["related_service_groups"].help_text = (
            "اختیاری است؛ گروه خدمت مرتبط را در صورت وجود انتخاب کن."
        )
        if salon is not None:
            self.fields["related_service_groups"].queryset = (
                GroupServices.objects.filter(services_of_group__in=salon.services.all())
                .distinct()
                .order_by("group_title")
            )
        self.fields["title"].help_text = (
            "عنوان واضح و کوتاه بنویس؛ این عنوان در مجله و SEO دیده می‌شود."
        )
        self.fields["summary"].help_text = "خلاصه کوتاه ۱ تا ۲ جمله‌ای برای کارت مقاله."
        self.fields["content"].help_text = (
            "متن اصلی مقاله را کامل، خوانا و بدون اطلاعات حساس مشتری وارد کن."
        )
        self.fields["cover_image"].help_text = (
            "اختیاری است، ولی برای نمایش حرفه‌ای در مجله توصیه می‌شود."
        )
        self.fields["content_type"].help_text = (
            "نوع محتوا را انتخاب کن تا مقاله در بخش درست مجله نمایش داده شود."
        )
        self.fields["visibility"].help_text = (
            "عمومی یعنی در مجله و صفحه مجموعه قابل مشاهده باشد."
        )
        self.fields["contains_identifiable_client"].help_text = (
            "اگر تصویر، نام یا نشانه قابل تشخیص مشتری وجود دارد این گزینه را فعال کن."
        )
        self.fields["client_consent_status"].help_text = (
            "یکی از گزینه‌ها را انتخاب کن؛ اگر مشتری در تصویر یا متن قابل شناسایی است، بدون رضایت یا محو کردن مشخصات منتشر نکن."
        )
        self.fields["manager_approved_responsibility"].help_text = (
            "برای انتشار باید تأیید کنی که حق انتشار و رضایت‌های لازم را داری."
        )
        _apply_dashboard_widgets(self)

        self.fields["cover_image"].widget.attrs.update(
            {"accept": "image/jpeg,image/png,image/webp"}
        )

    def clean_cover_image(self):
        cover_image = self.cleaned_data.get("cover_image")
        return validate_article_cover_image_upload(
            cover_image,
            declared_content_type=self._raw_cover_image_content_type or None,
        )

    def clean(self):
        cleaned = super().clean()
        action = self.data.get("article_action") or "draft"
        is_published_edit = bool(
            getattr(self.instance, "pk", None)
            and getattr(self.instance, "status", "") == Article.Status.PUBLISHED
        )
        if (action == "publish" or is_published_edit) and not cleaned.get(
            "manager_approved_responsibility"
        ):
            self.add_error(
                "manager_approved_responsibility",
                "برای انتشار یا ویرایش محتوای منتشرشده باید مسئولیت و مجوز انتشار را تأیید کنید.",
            )
        if cleaned.get("contains_identifiable_client") and cleaned.get(
            "client_consent_status"
        ) in {"", "not_required"}:
            self.add_error(
                "client_consent_status",
                "برای محتوای دارای هویت قابل تشخیص مشتری، وضعیت رضایت مشتری را مشخص کنید.",
            )
        return cleaned


class ManagerStoryForm(forms.ModelForm):
    client_consent_status = forms.ChoiceField(
        choices=CONSENT_STATUS_CHOICES, required=False, label="وضعیت رضایت مشتری"
    )

    class Meta:
        model = SalonStory
        fields = [
            "title",
            "summary",
            "cover_image",
            "visibility",
            "cta_type",
            "cta_label",
            "cta_url",
            "related_article",
            "related_service",
            "related_service_group",
            "stylist",
            "contains_identifiable_client",
            "client_consent_status",
            "manager_approved_responsibility",
        ]
        widgets = {"summary": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, salon=None, **kwargs):
        files = kwargs.get("files")
        if files is None and len(args) > 1:
            files = args[1]

        prefix = kwargs.get("prefix")
        self._raw_cover_image_content_type = _raw_upload_content_type(
            files,
            "cover_image",
            prefix=prefix,
        )

        super().__init__(*args, **kwargs)
        if salon is not None:
            self.fields["related_article"].queryset = Article.objects.filter(
                author_salon=salon
            ).order_by("-created_at")
            self.fields["related_service"].queryset = (
                salon.services.all().distinct().order_by("service_name")
            )
        if salon is not None:
            self.fields["related_service_group"].queryset = (
                GroupServices.objects.filter(services_of_group__in=salon.services.all())
                .distinct()
                .order_by("group_title")
            )
            if "stylist" in self.fields:
                self.fields["stylist"].queryset = salon.stylists.all().order_by(
                    "user_id"
                )
        for name in [
            "related_article",
            "related_service",
            "related_service_group",
            "stylist",
            "cta_label",
            "cta_url",
        ]:
            self.fields[name].required = False
        self.fields["title"].help_text = (
            "عنوان کوتاه استوری؛ در حلقه استوری‌ها نمایش داده می‌شود."
        )
        self.fields["summary"].help_text = "توضیح کوتاه یا کپشن اسلاید اول."
        self.fields["cover_image"].help_text = (
            "برای انتشار استوری بهتر است کاور انتخاب شود؛ همین تصویر اسلاید اول می‌شود."
        )
        self.fields["visibility"].help_text = (
            "مشخص کن استوری برای همه یا فقط علاقه‌مندان مجموعه نمایش داده شود."
        )
        self.fields["cta_type"].help_text = (
            "نوع مقصد دکمه استوری را انتخاب کن؛ پایین فرم چند پیشنهاد لینک آماده برای مجموعه، خدمت و متخصص می‌بینی."
        )
        self.fields["cta_label"].help_text = (
            "اختیاری؛ متن دکمه مثل «رزرو وقت» یا «مطالعه مقاله»."
        )
        self.fields["cta_url"].help_text = (
            "اگر لینک پیشنهادی مناسب نیست، لینک سفارشی را اینجا وارد کن. برای مجموعه/خدمت/مقاله بهتر است از فیلدهای مرتبط استفاده شود."
        )
        self.fields["related_article"].help_text = (
            "اختیاری؛ اگر استوری به مقاله‌ای وصل است انتخاب کن."
        )
        self.fields["related_service"].help_text = (
            "اختیاری؛ اگر استوری برای خدمت خاصی است انتخاب کن."
        )
        self.fields["related_service_group"].help_text = (
            "اختیاری؛ گروه خدمت مرتبط با استوری."
        )
        self.fields["contains_identifiable_client"].help_text = (
            "اگر چهره/نام/نشانه مشتری مشخص است این گزینه را فعال کن."
        )
        self.fields["client_consent_status"].help_text = (
            "یکی از گزینه‌ها را انتخاب کن؛ اگر چهره یا نام مشتری مشخص است، وضعیت رضایت باید شفاف باشد."
        )
        self.fields["manager_approved_responsibility"].help_text = (
            "برای انتشار باید مسئولیت و مجوز انتشار را تأیید کنی."
        )
        _apply_dashboard_widgets(self)

        self.fields["cover_image"].widget.attrs.update(
            {"accept": "image/jpeg,image/png,image/webp"}
        )

    def clean_cover_image(self):
        cover_image = self.cleaned_data.get("cover_image")
        return validate_article_cover_image_upload(
            cover_image,
            declared_content_type=self._raw_cover_image_content_type or None,
        )

    def clean(self):
        cleaned = super().clean()
        action = self.data.get("story_action") or "draft"
        is_published_edit = bool(
            getattr(self.instance, "pk", None)
            and getattr(self.instance, "status", "") == SalonStory.Status.PUBLISHED
        )
        if (action == "publish" or is_published_edit) and not cleaned.get(
            "manager_approved_responsibility"
        ):
            self.add_error(
                "manager_approved_responsibility",
                "برای انتشار یا ویرایش استوری منتشرشده باید مسئولیت و مجوز انتشار را تأیید کنید.",
            )
        if cleaned.get("contains_identifiable_client") and cleaned.get(
            "client_consent_status"
        ) in {"", "not_required"}:
            self.add_error(
                "client_consent_status",
                "برای محتوای دارای هویت قابل تشخیص مشتری، وضعیت رضایت مشتری را مشخص کنید.",
            )
        return cleaned


class StylistDashboardContentSubmissionForm(forms.ModelForm):
    client_consent_status = forms.ChoiceField(
        choices=CONSENT_STATUS_CHOICES, required=False, label="وضعیت رضایت مشتری"
    )
    new_tags = forms.CharField(
        required=False,
        label="برچسب‌های جدید پیشنهادی",
        help_text="اگر برچسب آماده در لیست نبود، چند برچسب را با ویرگول جدا کن؛ مثل رنگ مو، مراقبت پوست",
    )
    suggested_tags = forms.ModelMultipleChoiceField(
        queryset=ArticleTag.objects.none(),
        required=False,
        label="برچسب‌های مرتبط پیشنهادی",
        help_text="اختیاری؛ برچسب‌های آماده را با کلیک انتخاب کن.",
    )
    suggested_services = forms.ModelMultipleChoiceField(
        queryset=Services.objects.none(),
        required=False,
        label="خدمات مرتبط پیشنهادی",
        help_text="اختیاری؛ خدماتی که این محتوا به آن‌ها مربوط است.",
    )
    suggested_service_groups = forms.ModelMultipleChoiceField(
        queryset=GroupServices.objects.none(),
        required=False,
        label="گروه‌های خدمت پیشنهادی",
        help_text="اختیاری؛ گروه‌های مرتبط را انتخاب کن.",
    )
    visibility = forms.ChoiceField(
        choices=Article.Visibility.choices, required=False, label="نمایش پیشنهادی"
    )
    cta_type = forms.ChoiceField(
        choices=SalonStory.CTAType.choices, required=False, label="نوع دکمه استوری"
    )
    cta_label = forms.CharField(required=False, label="متن دکمه استوری")
    cta_url = forms.CharField(required=False, label="لینک پیشنهادی استوری")

    class Meta:
        model = StaffContentSubmission
        fields = [
            "submission_type",
            "title",
            "body",
            "media",
            "contains_identifiable_client",
            "client_consent_status",
            "professional_confirmed_responsibility",
        ]
        widgets = {"body": forms.Textarea(attrs={"rows": 7})}

    def __init__(self, *args, submission_type=None, salon=None, **kwargs):
        files = kwargs.get("files")
        if files is None and len(args) > 1:
            files = args[1]

        prefix = kwargs.get("prefix")
        self._raw_media_content_type = _raw_upload_content_type(
            files,
            "media",
            prefix=prefix,
        )

        super().__init__(*args, **kwargs)
        self.submission_type = submission_type
        if submission_type:
            self.fields["submission_type"].initial = submission_type
            self.fields["submission_type"].widget = forms.HiddenInput()
        self.fields["suggested_tags"].queryset = ArticleTag.objects.all().order_by(
            "title"
        )
        if salon is not None:
            self.fields["suggested_services"].queryset = (
                salon.services.all().distinct().order_by("service_name")
            )
            self.fields["suggested_service_groups"].queryset = (
                GroupServices.objects.filter(services_of_group__in=salon.services.all())
                .distinct()
                .order_by("group_title")
            )
        self.fields["submission_type"].help_text = (
            "نوع محتوایی که می‌فرستی را انتخاب کن: مقاله، استوری یا نمونه‌کار."
        )
        self.fields["title"].required = True
        self.fields["title"].help_text = (
            "عنوان کوتاه و قابل فهم بنویس تا مدیر مجموعه سریع موضوع را بفهمد."
        )
        self.fields["body"].help_text = (
            "متن یا کپشن پیشنهادی را کامل وارد کن؛ مدیر مجموعه قبل از انتشار می‌تواند آن را ویرایش کند."
        )
        self.fields["suggested_tags"].widget = forms.CheckboxSelectMultiple()
        self.fields["suggested_services"].widget = forms.CheckboxSelectMultiple()
        self.fields["suggested_service_groups"].widget = forms.CheckboxSelectMultiple()
        if submission_type == StaffContentSubmission.SubmissionType.STORY:
            self.fields["body"].label = "کپشن یا توضیح استوری"
            self.fields["body"].help_text = (
                "متن کوتاه و قابل نمایش روی استوری بنویس؛ لینک یا دکمه پیشنهادی را هم در فیلدهای پایین مشخص کن."
            )
            self.fields["media"].required = True
            self.fields["media"].help_text = "برای استوری، تصویر یا ویدیو الزامی است."
            self.fields["visibility"].choices = SalonStory.Visibility.choices
        elif submission_type == StaffContentSubmission.SubmissionType.ARTICLE:
            self.fields["body"].label = "متن مقاله پیشنهادی"
            self.fields["body"].help_text = (
                "متن مقاله را کامل و قابل انتشار بنویس؛ مدیر مجموعه می‌تواند قبل از انتشار ویرایش کند."
            )
            self.fields["media"].help_text = "اختیاری؛ تصویر شاخص پیشنهادی مقاله."
            self.fields["visibility"].choices = Article.Visibility.choices
            for extra_name in ["cta_type", "cta_label", "cta_url"]:
                self.fields[extra_name].widget = forms.HiddenInput()
        else:
            self.fields["media"].help_text = (
                "اختیاری، ولی برای استوری و نمونه‌کار بهتر است تصویر/ویدیو پیوست شود."
            )
        self.fields["contains_identifiable_client"].help_text = (
            "اگر چهره، نام یا نشانه مشتری مشخص است این گزینه را فعال کن."
        )
        self.fields["client_consent_status"].help_text = (
            "یکی از گزینه‌ها را انتخاب کن؛ اگر مشتری قابل شناسایی است، رضایت یا نیاز به محو کردن مشخصات را مشخص کن."
        )
        self.fields["professional_confirmed_responsibility"].help_text = (
            "تأیید کن محتوا متعلق به توست و اجازه انتشار آن را داری."
        )
        _apply_dashboard_widgets(self)
        self.fields["media"].widget.attrs.update(
            {"accept": "image/jpeg,image/png,image/webp,video/mp4"}
        )

    def clean_media(self):
        media = self.cleaned_data.get("media")
        return validate_staff_content_media_upload(
            media,
            declared_content_type=self._raw_media_content_type or None,
        )

    def apply_metadata_to_submission(
        self, submission: StaffContentSubmission
    ) -> StaffContentSubmission:
        body = (
            (self.cleaned_data.get("body") or "")
            .split("\n\nگزینه‌های پیشنهادی برای مدیر:")[0]
            .strip()
        )
        lines = []
        selected_tags = self.cleaned_data.get("suggested_tags")
        if selected_tags:
            lines.append(
                "برچسب‌های مرتبط: "
                + "، ".join(getattr(item, "title", str(item)) for item in selected_tags)
            )
        tags = (self.cleaned_data.get("new_tags") or "").strip()
        if tags:
            lines.append(f"برچسب‌های جدید: {tags}")
        services = self.cleaned_data.get("suggested_services")
        if services:
            lines.append("خدمات مرتبط: " + "، ".join(str(item) for item in services))
        groups = self.cleaned_data.get("suggested_service_groups")
        if groups:
            lines.append("گروه‌های خدمت: " + "، ".join(str(item) for item in groups))
        visibility = self.cleaned_data.get("visibility")
        if visibility:
            lines.append(f"نمایش پیشنهادی: {visibility}")
        if self.cleaned_data.get("cta_type"):
            lines.append(f"نوع دکمه استوری: {self.cleaned_data.get('cta_type')}")
        if self.cleaned_data.get("cta_label"):
            lines.append(f"متن دکمه: {self.cleaned_data.get('cta_label')}")
        if self.cleaned_data.get("cta_url"):
            lines.append(f"لینک دکمه: {self.cleaned_data.get('cta_url')}")
        submission.body = body + (
            ("\n\nگزینه‌های پیشنهادی برای مدیر:\n" + "\n".join(lines)) if lines else ""
        )
        return submission

    def clean(self):
        cleaned = super().clean()
        submission_type = cleaned.get("submission_type")
        body = (cleaned.get("body") or "").strip()
        media = cleaned.get("media")
        if (
            submission_type
            in {
                StaffContentSubmission.SubmissionType.STORY,
                StaffContentSubmission.SubmissionType.PORTFOLIO,
            }
            and not media
        ):
            self.add_error(
                "media", "برای استوری یا نمونه‌کار، یک تصویر یا فایل محتوا اضافه کن."
            )
        if (
            submission_type == StaffContentSubmission.SubmissionType.ARTICLE
            and len(body) < 80
        ):
            self.add_error(
                "body",
                "برای مقاله پیشنهادی، متن باید کامل‌تر باشد؛ حداقل چند جمله توضیح وارد کن.",
            )
        if not cleaned.get("professional_confirmed_responsibility"):
            self.add_error(
                "professional_confirmed_responsibility",
                "برای ارسال محتوا باید مسئولیت اصالت و مجوز انتشار را تأیید کنید.",
            )
        if cleaned.get("contains_identifiable_client") and cleaned.get(
            "client_consent_status"
        ) in {"", "not_required"}:
            self.add_error(
                "client_consent_status",
                "برای محتوای دارای هویت قابل تشخیص مشتری، وضعیت رضایت مشتری را مشخص کنید.",
            )
        return cleaned


class ManagerContentHubView(LoginRequiredMixin, View):
    template_name = "dashboards/content_hub.html"

    def _context(self, request, *, article_form=None, story_form=None):
        salon = _manager_salon(request.user)
        if salon is None:
            messages.error(
                request, "برای مدیریت محتوا ابتدا پروفایل مجموعه را تکمیل کنید."
            )
            return None
        article_form = article_form or ManagerArticleForm(prefix="article", salon=salon)
        story_form = story_form or ManagerStoryForm(prefix="story", salon=salon)
        recent_articles = list(
            Article.objects.filter(author_salon=salon).order_by("-created_at")[:8]
        )
        recent_stories = list(
            SalonStory.objects.filter(salon=salon).order_by("-created_at")[:8]
        )
        article_edit_forms = [
            (
                item,
                ManagerArticleForm(
                    prefix=f"article_edit_{item.pk}", salon=salon, instance=item
                ),
            )
            for item in recent_articles
        ]
        story_edit_forms = [
            (
                item,
                ManagerStoryForm(
                    prefix=f"story_edit_{item.pk}", salon=salon, instance=item
                ),
            )
            for item in recent_stories
        ]
        ctx = build_dashboard_context(
            request.user,
            sidebar_active="content",
            page_title="محتوای مجموعه",
            request_path=request.path,
        )
        ctx.update(
            {
                "salon": salon,
                "article_form": article_form,
                "story_form": story_form,
                "recent_articles": recent_articles,
                "recent_stories": recent_stories,
                "article_edit_forms": article_edit_forms,
                "story_edit_forms": story_edit_forms,
                "story_link_suggestions": _build_story_link_suggestions(salon),
                "article_tag_options": article_form.fields["tags"].queryset,
                "article_service_options": article_form.fields[
                    "related_services"
                ].queryset,
                "article_service_group_options": article_form.fields[
                    "related_service_groups"
                ].queryset,
                "staff_submissions": StaffContentSubmission.objects.filter(salon=salon)
                .select_related("stylist__user")
                .order_by("-created_at")[:12],
                "nav_active": "content",
                "sidebar_active": "content",
            }
        )
        return ctx

    def get(self, request, *args, **kwargs):
        ctx = self._context(request)
        if ctx is None:
            return redirect("dashboards:salon_manager_dashboard")
        return render(request, self.template_name, ctx)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        salon = _manager_salon(request.user)
        if salon is None:
            messages.error(
                request, "برای مدیریت محتوا ابتدا پروفایل مجموعه را تکمیل کنید."
            )
            return redirect("dashboards:salon_manager_dashboard")

        form_type = request.POST.get("form_type")
        if form_type == "article":
            form = ManagerArticleForm(
                request.POST, request.FILES, prefix="article", salon=salon
            )
            if form.is_valid():
                article = form.save(commit=False)
                article.author_user = request.user
                article.author_salon = salon
                article.slug = _unique_article_slug(article.title)
                action = request.POST.get("article_action") or "draft"
                article.status = (
                    Article.Status.PUBLISHED
                    if action == "publish"
                    else Article.Status.DRAFT
                )
                article.manager_approved_by = (
                    request.user if article.manager_approved_responsibility else None
                )
                article.manager_approved_at = (
                    timezone.now() if article.manager_approved_responsibility else None
                )
                article.manager_terms_version = (
                    "dashboard-qa-v1" if article.manager_approved_responsibility else ""
                )
                article.save()
                form.save_m2m()
                _attach_new_tags(article, form.cleaned_data.get("new_tags", ""))
                _record_content_event(
                    article,
                    event_type="published" if action == "publish" else "draft_saved",
                    actor=request.user,
                    new_status=article.status,
                )
                _notify_content_event(
                    salon=salon,
                    actor=request.user,
                    event_type=(
                        "content_article_published"
                        if action == "publish"
                        else "content_article_draft_saved"
                    ),
                    title=(
                        "مقاله مجموعه منتشر شد"
                        if action == "publish"
                        else "پیش‌نویس مقاله ذخیره شد"
                    ),
                    body=f"مقاله «{article.title}» برای مجموعه {salon.salon_name} ثبت شد.",
                    target=article,
                    action_url=reverse("dashboards:content_hub"),
                    include_admins=action == "publish",
                )
                messages.success(
                    request,
                    (
                        "مقاله با موفقیت ثبت شد."
                        if action == "draft"
                        else "مقاله منتشر شد و اعلان محتوا ثبت شد."
                    ),
                )
                return redirect("dashboards:content_hub")
            ctx = self._context(request, article_form=form)
            return render(request, self.template_name, ctx)

        if form_type == "story":
            form = ManagerStoryForm(
                request.POST, request.FILES, prefix="story", salon=salon
            )
            if form.is_valid():
                story = form.save(commit=False)
                story.salon = salon
                action = request.POST.get("story_action") or "draft"
                story.status = (
                    SalonStory.Status.PUBLISHED
                    if action == "publish"
                    else SalonStory.Status.DRAFT
                )
                story.manager_approved_by = (
                    request.user if story.manager_approved_responsibility else None
                )
                story.manager_approved_at = (
                    timezone.now() if story.manager_approved_responsibility else None
                )
                story.manager_terms_version = (
                    "dashboard-qa-v1" if story.manager_approved_responsibility else ""
                )
                story.save()
                if story.cover_image and not story.items.exists():
                    SalonStoryItem.objects.create(
                        story=story,
                        image=story.cover_image.name,
                        caption=story.summary[:260],
                        sort_order=1,
                    )
                _record_content_event(
                    story,
                    event_type="published" if action == "publish" else "draft_saved",
                    actor=request.user,
                    new_status=story.status,
                )
                _notify_content_event(
                    salon=salon,
                    actor=request.user,
                    event_type=(
                        "content_story_published"
                        if action == "publish"
                        else "content_story_draft_saved"
                    ),
                    title=(
                        "استوری مجموعه منتشر شد"
                        if action == "publish"
                        else "پیش‌نویس استوری ذخیره شد"
                    ),
                    body=f"استوری «{story.title}» برای مجموعه {salon.salon_name} ثبت شد.",
                    target=story,
                    action_url=reverse("dashboards:content_hub"),
                    include_admins=action == "publish",
                )
                messages.success(
                    request,
                    (
                        "استوری با موفقیت ثبت شد."
                        if action == "draft"
                        else "استوری منتشر شد و اعلان محتوا ثبت شد."
                    ),
                )
                return redirect("dashboards:content_hub")
            ctx = self._context(request, story_form=form)
            return render(request, self.template_name, ctx)

        if form_type == "article_edit":
            article_id = request.POST.get("article_id")
            article = Article.objects.filter(pk=article_id, author_salon=salon).first()
            if article is None:
                messages.error(request, "مقاله پیدا نشد یا متعلق به این مجموعه نیست.")
                return redirect("dashboards:content_hub")
            form = ManagerArticleForm(
                request.POST,
                request.FILES,
                prefix=f"article_edit_{article.pk}",
                salon=salon,
                instance=article,
            )
            if form.is_valid():
                updated = form.save(commit=False)
                action = request.POST.get("article_action") or "save"
                if action == "publish":
                    updated.status = Article.Status.PUBLISHED
                    updated.manager_approved_by = (
                        request.user
                        if updated.manager_approved_responsibility
                        else None
                    )
                    updated.manager_approved_at = (
                        timezone.now()
                        if updated.manager_approved_responsibility
                        else updated.manager_approved_at
                    )
                    updated.manager_terms_version = (
                        "dashboard-qa-v1"
                        if updated.manager_approved_responsibility
                        else updated.manager_terms_version
                    )
                elif action == "archive":
                    updated.status = Article.Status.ARCHIVED
                updated.save()
                form.save_m2m()
                _attach_new_tags(updated, form.cleaned_data.get("new_tags", ""))
                _record_content_event(
                    updated,
                    event_type=f"article_{action}",
                    actor=request.user,
                    old_status=article.status,
                    new_status=updated.status,
                )
                messages.success(request, "تغییرات مقاله ذخیره شد.")
                return redirect("dashboards:content_hub")
            ctx = self._context(request)
            if ctx is not None:
                ctx["article_edit_errors"] = {str(article.pk): form}
                return render(request, self.template_name, ctx)
            return redirect("dashboards:content_hub")

        if form_type == "story_edit":
            story_id = request.POST.get("story_id")
            story = SalonStory.objects.filter(pk=story_id, salon=salon).first()
            if story is None:
                messages.error(request, "استوری پیدا نشد یا متعلق به این مجموعه نیست.")
                return redirect("dashboards:content_hub")
            form = ManagerStoryForm(
                request.POST,
                request.FILES,
                prefix=f"story_edit_{story.pk}",
                salon=salon,
                instance=story,
            )
            if form.is_valid():
                updated = form.save(commit=False)
                action = request.POST.get("story_action") or "save"
                if action == "publish":
                    updated.status = SalonStory.Status.PUBLISHED
                    updated.manager_approved_by = (
                        request.user
                        if updated.manager_approved_responsibility
                        else None
                    )
                    updated.manager_approved_at = (
                        timezone.now()
                        if updated.manager_approved_responsibility
                        else updated.manager_approved_at
                    )
                    updated.manager_terms_version = (
                        "dashboard-qa-v1"
                        if updated.manager_approved_responsibility
                        else updated.manager_terms_version
                    )
                elif action == "archive":
                    updated.status = SalonStory.Status.ARCHIVED
                updated.save()
                if updated.cover_image and not updated.items.exists():
                    SalonStoryItem.objects.create(
                        story=updated,
                        image=updated.cover_image.name,
                        caption=updated.summary[:260],
                        sort_order=1,
                    )
                _record_content_event(
                    updated,
                    event_type=f"story_{action}",
                    actor=request.user,
                    old_status=story.status,
                    new_status=updated.status,
                )
                messages.success(request, "تغییرات استوری ذخیره شد.")
                return redirect("dashboards:content_hub")
            ctx = self._context(request)
            if ctx is not None:
                ctx["story_edit_errors"] = {str(story.pk): form}
                return render(request, self.template_name, ctx)
            return redirect("dashboards:content_hub")

        if form_type == "submission_action":
            submission_id = request.POST.get("submission_id")
            action = request.POST.get("submission_action")
            note = (request.POST.get("review_note") or "").strip()
            submission = (
                StaffContentSubmission.objects.filter(pk=submission_id, salon=salon)
                .select_related("stylist__user")
                .first()
            )
            if submission is None:
                messages.error(
                    request, "محتوای پیشنهادی پیدا نشد یا متعلق به این مجموعه نیست."
                )
                return redirect("dashboards:content_hub")
            old_status = submission.status
            manager_title = (request.POST.get("manager_title") or "").strip()
            manager_body = (request.POST.get("manager_body") or "").strip()
            if manager_title:
                submission.title = manager_title[:255]
            if manager_body:
                submission.body = manager_body

            published_target = None
            if action == "approve":
                public_body = _public_submission_body(submission.body)
                if not submission.title or not public_body:
                    messages.error(
                        request,
                        "برای تأیید و انتشار، عنوان و متن محتوا باید کامل باشد.",
                    )
                    return redirect("dashboards:content_hub")
                submission.status = StaffContentSubmission.Status.PUBLISHED
                success_message = "محتوای پیشنهادی پس از تأیید مدیر منتشر شد."
                if (
                    submission.submission_type
                    == StaffContentSubmission.SubmissionType.ARTICLE
                ):
                    published_target = Article.objects.create(
                        title=submission.title,
                        slug=_unique_article_slug(submission.title),
                        summary=_summary_from_text(public_body),
                        content=public_body,
                        cover_image=submission.media if submission.media else None,
                        author_user=getattr(submission.stylist, "user", None),
                        author_stylist=submission.stylist,
                        author_salon=salon,
                        status=Article.Status.PUBLISHED,
                        visibility=Article.Visibility.PUBLIC,
                        contains_identifiable_client=submission.contains_identifiable_client,
                        client_consent_status=submission.client_consent_status
                        or "not_required",
                        manager_approved_responsibility=True,
                        manager_approved_by=request.user,
                        manager_approved_at=timezone.now(),
                        manager_terms_version="dashboard-qa-v1",
                        professional_confirmed_responsibility=submission.professional_confirmed_responsibility,
                        professional_confirmed_at=submission.professional_confirmed_at,
                    )
                elif (
                    submission.submission_type
                    == StaffContentSubmission.SubmissionType.STORY
                ):
                    published_target = SalonStory.objects.create(
                        salon=salon,
                        stylist=submission.stylist,
                        title=submission.title[:140],
                        summary=_summary_from_text(public_body),
                        cover_image=submission.media if submission.media else None,
                        status=SalonStory.Status.PUBLISHED,
                        visibility=SalonStory.Visibility.PUBLIC,
                        contains_identifiable_client=submission.contains_identifiable_client,
                        client_consent_status=submission.client_consent_status
                        or "not_required",
                        manager_approved_responsibility=True,
                        manager_approved_by=request.user,
                        manager_approved_at=timezone.now(),
                        manager_terms_version="dashboard-qa-v1",
                        professional_confirmed_responsibility=submission.professional_confirmed_responsibility,
                        professional_confirmed_at=submission.professional_confirmed_at,
                    )
                    if submission.media:
                        SalonStoryItem.objects.create(
                            story=published_target,
                            image=submission.media.name,
                            caption=_summary_from_text(public_body, 260),
                            sort_order=1,
                        )
                if published_target is not None:
                    submission.target_content_type = ContentType.objects.get_for_model(
                        published_target, for_concrete_model=False
                    )
                    submission.target_object_id = published_target.pk
            elif action == "revision":
                submission.status = StaffContentSubmission.Status.NEEDS_REVISION
                success_message = "درخواست اصلاح برای متخصص ثبت شد."
                if not note:
                    messages.error(
                        request, "برای درخواست اصلاح، توضیح اصلاحات را بنویس."
                    )
                    return redirect("dashboards:content_hub")
            elif action == "reject":
                submission.status = StaffContentSubmission.Status.REJECTED
                success_message = "محتوای پیشنهادی رد شد."
                if not note:
                    messages.error(request, "برای رد محتوا، دلیل رد شدن را بنویس.")
                    return redirect("dashboards:content_hub")
            else:
                messages.error(request, "عملیات محتوای پیشنهادی نامعتبر است.")
                return redirect("dashboards:content_hub")
            submission.review_note = note
            submission.reviewed_by = request.user
            submission.reviewed_at = timezone.now()
            submission.save(
                update_fields=[
                    "title",
                    "body",
                    "status",
                    "review_note",
                    "reviewed_by",
                    "reviewed_at",
                    "target_content_type",
                    "target_object_id",
                    "updated_at",
                ]
            )
            _record_content_event(
                submission,
                event_type=f"staff_content_{action}",
                actor=request.user,
                old_status=old_status,
                new_status=submission.status,
                note=note,
            )
            _notify_content_event(
                salon=salon,
                stylist=submission.stylist,
                actor=request.user,
                event_type=f"staff_content_{action}",
                title="نتیجه بررسی محتوای پیشنهادی",
                body=f"وضعیت محتوای «{submission.title or submission.get_submission_type_display()}» به «{submission.get_status_display()}» تغییر کرد.",
                target=submission,
                action_url=reverse("dashboards:stylist_content"),
                include_admins=False,
            )
            messages.success(request, success_message)
            return redirect("dashboards:content_hub")

        messages.error(request, "فرم محتوا نامعتبر است.")
        return redirect("dashboards:content_hub")


def get_current_stylist_or_404(request):
    return get_object_or_404(
        Stylist.objects.select_related("user"),
        user=request.user,
    )


def get_stylist_owned_article_or_404(request, article_id):
    stylist = get_current_stylist_or_404(request)

    return get_object_or_404(
        Article.objects.select_related(
            "author_user",
            "author_stylist",
            "author_salon",
            "category",
        ),
        pk=article_id,
        author_stylist=stylist,
        author_salon__isnull=True,
    )


class StylistContentHubView(LoginRequiredMixin, View):
    template_name = "dashboards/stylist_content.html"

    EDITABLE_STATUSES = {
        StaffContentSubmission.Status.PENDING_REVIEW,
        StaffContentSubmission.Status.NEEDS_REVISION,
        StaffContentSubmission.Status.REJECTED,
        StaffContentSubmission.Status.DRAFT,
    }

    PROTECTED_ACTIONS = {
        "update",
        "edit",
        "delete",
        "archive",
        "publish",
        "unpublish",
        "restore",
    }

    def _get_objects(self, request):
        stylist = getattr(request.user, "stylist", None)
        if stylist is None:
            return None, None

        salon = get_active_salon_for_stylist(request.user, request=request)

        if salon is None:
            membership = (
                SalonMembership.objects.filter(
                    stylist=stylist,
                    status=SalonMembershipStatus.ACTIVE,
                )
                .select_related("salon")
                .order_by("salon__salon_name", "id")
                .first()
            )
            salon = (
                membership.salon
                if membership
                else stylist.stylists_of_salon.order_by("salon_name", "id").first()
            )

        return stylist, salon

    def _get_editable_submission_or_404(self, *, submission_id, stylist, salon):
        """
        فقط محتوای پیشنهادی خود همین متخصص در همین مجموعه قابل ویرایش است.
        اگر کاربر id مربوط به مقاله/محتوای مجموعه یا متخصص دیگر را بفرستد، 404 می‌گیرد.
        """
        if not submission_id:
            raise Http404("درخواست محتوای موردنظر پیدا نشد.")

        return get_object_or_404(
            StaffContentSubmission.objects.select_related("stylist", "salon"),
            pk=submission_id,
            stylist=stylist,
            salon=salon,
        )

    def _reject_foreign_object_mutation_attempt(self, request, *, form_type):
        """
        تست F3-P6 با article_id/id/pk/action=update به همین endpoint می‌زند.
        این endpoint فقط برای StaffContentSubmission متخصص است، نه Article مجموعه.
        پس هر تلاش برای mutation آبجکت خارجی باید قبل از bind شدن فرم 404 شود.
        """
        if form_type == "submission_edit":
            return

        action = (request.POST.get("action") or "").strip().lower()
        object_id = (
            request.POST.get("article_id")
            or request.POST.get("submission_id")
            or request.POST.get("id")
            or request.POST.get("pk")
        )

        if object_id and action in self.PROTECTED_ACTIONS:
            raise Http404("محتوای موردنظر پیدا نشد.")

        # اگر بدون form_type معتبر ولی همراه object id ارسال شود، مشکوک است.
        if object_id and form_type not in {"article", "story", "submission_edit"}:
            raise Http404("محتوای موردنظر پیدا نشد.")

    def _context(self, request, *, form=None):
        stylist, salon = self._get_objects(request)

        if stylist is None or salon is None:
            messages.error(
                request, "برای ارسال محتوا باید به یک مجموعه فعال متصل باشید."
            )
            return None

        article_form = (
            form
            if getattr(form, "submission_kind", "") == "article"
            else StylistDashboardContentSubmissionForm(
                submission_type=StaffContentSubmission.SubmissionType.ARTICLE,
                salon=salon,
            )
        )

        story_form = (
            form
            if getattr(form, "submission_kind", "") == "story"
            else StylistDashboardContentSubmissionForm(
                submission_type=StaffContentSubmission.SubmissionType.STORY,
                salon=salon,
            )
        )

        submissions_qs = StaffContentSubmission.objects.filter(
            stylist=stylist,
            salon=salon,
        )
        status_counts = {
            "total": submissions_qs.count(),
            "pending": submissions_qs.filter(status=StaffContentSubmission.Status.PENDING_REVIEW).count(),
            "revision": submissions_qs.filter(status__in=[StaffContentSubmission.Status.NEEDS_REVISION, StaffContentSubmission.Status.REJECTED]).count(),
            "published": submissions_qs.filter(status__in=[StaffContentSubmission.Status.APPROVED, StaffContentSubmission.Status.PUBLISHED]).count(),
        }
        submissions = list(submissions_qs.order_by("-created_at")[:24])

        submission_edit_forms = [
            (
                item,
                StylistDashboardContentSubmissionForm(
                    prefix=f"submission_edit_{item.pk}",
                    instance=item,
                    submission_type=item.submission_type,
                    salon=salon,
                ),
            )
            for item in submissions
            if item.status in self.EDITABLE_STATUSES
        ]

        ctx = build_dashboard_context(
            request.user,
            sidebar_active="my_content",
            page_title="محتوای من",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )

        ctx.update(
            {
                "stylist_obj": stylist,
                "stylist_salon": salon,
                "article_form": article_form,
                "story_form": story_form,
                "submissions": submissions,
                "submission_edit_forms": submission_edit_forms,
                "stylist_content_summary": status_counts,
                "stylist_tag_options": ArticleTag.objects.all().order_by("title"),
                "stylist_article_service_options": article_form.fields[
                    "suggested_services"
                ].queryset,
                "stylist_article_service_group_options": article_form.fields[
                    "suggested_service_groups"
                ].queryset,
                "stylist_story_service_options": story_form.fields[
                    "suggested_services"
                ].queryset,
                "stylist_story_service_group_options": story_form.fields[
                    "suggested_service_groups"
                ].queryset,
                "story_link_suggestions": _build_story_link_suggestions(salon),
            }
        )

        return ctx

    def get(self, request, *args, **kwargs):
        ctx = self._context(request)

        if ctx is None:
            return redirect("dashboards:stylist_dashboard")

        return render(request, self.template_name, ctx)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        stylist, salon = self._get_objects(request)

        if stylist is None or salon is None:
            messages.error(
                request, "برای ارسال محتوا باید به یک مجموعه فعال متصل باشید."
            )
            return redirect("dashboards:stylist_dashboard")

        form_type = (request.POST.get("form_type") or "").strip()

        # Guard اصلی برای F3:
        # اگر متخصص article_id/id/pk مربوط به مقاله مجموعه را به این endpoint بفرستد،
        # دیگر فرم bind و render نمی‌شود و پاسخ 404 می‌گیرد.
        self._reject_foreign_object_mutation_attempt(request, form_type=form_type)

        if form_type == "submission_edit":
            submission_id = request.POST.get("submission_id")

            submission = self._get_editable_submission_or_404(
                submission_id=submission_id,
                stylist=stylist,
                salon=salon,
            )

            if submission.status not in self.EDITABLE_STATUSES:
                messages.error(
                    request,
                    "این محتوا بعد از تأیید یا انتشار قابل ویرایش نیست؛ برای تغییر با مدیر مجموعه هماهنگ کن.",
                )
                return redirect("dashboards:stylist_content")

            form = StylistDashboardContentSubmissionForm(
                request.POST,
                request.FILES,
                prefix=f"submission_edit_{submission.pk}",
                instance=submission,
                submission_type=submission.submission_type,
                salon=salon,
            )

            if form.is_valid():
                updated = form.save(commit=False)
                updated = form.apply_metadata_to_submission(updated)

                old_status = updated.status
                updated.status = StaffContentSubmission.Status.PENDING_REVIEW
                updated.professional_confirmed_at = timezone.now()
                updated.save()

                _record_content_event(
                    updated,
                    event_type="staff_content_updated",
                    actor=request.user,
                    old_status=old_status,
                    new_status=updated.status,
                )

                _notify_content_event(
                    salon=salon,
                    stylist=stylist,
                    actor=request.user,
                    event_type="staff_content_updated",
                    title="محتوای پیشنهادی متخصص ویرایش شد",
                    body=(
                        f"{stylist.get_fullName()} محتوای "
                        f"«{updated.title or updated.get_submission_type_display()}» "
                        "را دوباره برای بررسی ارسال کرد."
                    ),
                    target=updated,
                    action_url=reverse("dashboards:content_hub"),
                    include_admins=False,
                )

                messages.success(
                    request,
                    "تغییرات محتوا ذخیره و دوباره برای بررسی ارسال شد.",
                )
                return redirect("dashboards:stylist_content")

            form.submission_kind = (
                "story"
                if submission.submission_type
                == StaffContentSubmission.SubmissionType.STORY
                else "article"
            )

            messages.error(
                request,
                "ویرایش محتوا کامل نیست. خطاهای مشخص‌شده را اصلاح کن.",
            )

            ctx = self._context(request, form=form)

            if ctx is None:
                return redirect("dashboards:stylist_dashboard")

            return render(request, self.template_name, ctx)

        submission_type = (
            StaffContentSubmission.SubmissionType.STORY
            if form_type == "story"
            else StaffContentSubmission.SubmissionType.ARTICLE
        )

        form = StylistDashboardContentSubmissionForm(
            request.POST,
            request.FILES,
            submission_type=submission_type,
            salon=salon,
        )

        form.submission_kind = (
            "story"
            if submission_type == StaffContentSubmission.SubmissionType.STORY
            else "article"
        )

        if form.is_valid():
            submission = form.save(commit=False)
            submission = form.apply_metadata_to_submission(submission)

            submission.salon = salon
            submission.stylist = stylist
            submission.status = StaffContentSubmission.Status.PENDING_REVIEW
            submission.professional_confirmed_at = timezone.now()
            submission.save()

            _record_content_event(
                submission,
                event_type="submitted",
                actor=request.user,
                new_status=submission.status,
            )

            _notify_content_event(
                salon=salon,
                stylist=stylist,
                actor=request.user,
                event_type="staff_content_submitted",
                title="محتوای پیشنهادی متخصص ثبت شد",
                body=(
                    f"{stylist.get_fullName()} محتوای "
                    f"«{submission.title or submission.get_submission_type_display()}» "
                    "را برای بررسی ارسال کرد."
                ),
                target=submission,
                action_url=reverse("dashboards:content_hub"),
                include_admins=False,
            )

            messages.success(request, "محتوای شما برای بررسی مدیر مجموعه ارسال شد.")
            return redirect("dashboards:stylist_content")

        messages.error(
            request,
            "فرم محتوا کامل نیست. خطاهای مشخص‌شده را اصلاح کن و دوباره ارسال کن.",
        )

        ctx = self._context(request, form=form)

        if ctx is None:
            return redirect("dashboards:stylist_dashboard")

        return render(request, self.template_name, ctx)
