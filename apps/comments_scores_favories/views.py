from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Avg, Count
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.decorators.http import require_POST
from apps.accounts.models import Customer
from apps.salons.models import Salon
from apps.services.models import Services
from .forms import CommentScoringForm
from apps.orders.lifecycle import (
    find_reviewable_order_for_customer,
    mark_review_completed,
)
from .models import Comments, Favorits, Scoring
from apps.orders.models import OrderDetail
from django.contrib.auth.views import redirect_to_login
from django.conf import settings
from apps.main.ui_feedback import stash_form_errors


def _review_post_max_bytes():
    return max(
        int(getattr(settings, "CSF_REVIEW_POST_MAX_BYTES", 16 * 1024) or 1),
        1,
    )


def _review_comment_max_chars():
    return max(
        int(getattr(settings, "CSF_REVIEW_COMMENT_MAX_CHARS", 1000) or 1),
        1,
    )


def _review_post_payload_too_large(request):
    content_length = request.META.get("CONTENT_LENGTH")
    if not content_length:
        return False

    try:
        return int(content_length) > _review_post_max_bytes()
    except ValueError:
        return True


def _validated_salon_id(raw_salon_id):
    salon_id = str(raw_salon_id or "").strip()
    if not salon_id.isdigit():
        raise Http404("مجموعه موردنظر پیدا نشد.")
    return int(salon_id)


# -----------------------------------------------------------------------------------------------
class SalonCommentScoreView(View):
    def get(self, request, *args, **kwargs):
        salon_id = _validated_salon_id(request.GET.get("salon_id"))
        salon = get_object_or_404(Salon, id=salon_id, is_active=True)

        if not request.user.is_authenticated:
            messages.error(request, "برای نوشتن نظر و امتیاز ابتدا وارد شوید.")
            return redirect(salon.get_absolute_url())

        try:
            customer = Customer.objects.get(user=request.user)
        except Customer.DoesNotExist:
            messages.error(request, "شما به عنوان مشتری شناسایی نشده‌اید.")
            return redirect(salon.get_absolute_url())

        form = CommentScoringForm(salon=salon, customer=customer)
        return redirect(salon.get_absolute_url())

    def _get_customer_or_redirect(self, request, salon):
        if not request.user.is_authenticated:
            messages.error(request, "برای نوشتن نظر و امتیاز ابتدا وارد شوید.")
            return None, redirect(salon.get_absolute_url())

        try:
            customer = Customer.objects.get(user=request.user)
        except Customer.DoesNotExist:
            messages.error(request, "شما به عنوان مشتری شناسایی نشده‌اید.")
            return None, redirect(salon.get_absolute_url())

        return customer, None

    def _is_reviewable_appointment(self, appointment):
        order = appointment.order

        order_completed = bool(getattr(order, "service_completed_at", None))

        detail_completed = False
        try:
            detail_completed = (
                appointment.lifecycle_status
                == OrderDetail.ServiceLifecycleStatus.COMPLETED
            )
        except Exception:
            detail_completed = False

        return order_completed or detail_completed

    def _get_owned_reviewable_appointment(self, *, appointment_id, customer, salon):
        appointment = get_object_or_404(
            OrderDetail.objects.select_related(
                "order",
                "order__customer",
                "salon",
                "service",
                "stylist",
                "stylist__user",
            ),
            pk=appointment_id,
            order__customer=customer,
            salon=salon,
        )

        if not self._is_reviewable_appointment(appointment):
            return appointment, False

        return appointment, True

    def _upsert_comment_and_score(
        self, *, salon, customer, stylist, service, comment_text, score
    ):
        """
        قبلاً update_or_create مستقیم روی Comments باعث MultipleObjectsReturned می‌شد،
        چون ترکیب salon/comment_user/stylist/service در دیتابیس unique نیست.
        این نسخه اگر رکورد قبلی وجود داشته باشد آخرین رکورد را آپدیت می‌کند،
        و اگر نباشد رکورد جدید می‌سازد.
        """
        comment_obj = (
            Comments.objects.filter(
                salon=salon,
                comment_user=customer,
                stylist=stylist,
                service=service,
            )
            .order_by("-id")
            .first()
        )

        if comment_obj:
            comment_obj.comment_text = comment_text
            comment_obj.is_active = False
            comment_obj.save(update_fields=["comment_text", "is_active"])
        else:
            comment_obj = Comments.objects.create(
                salon=salon,
                comment_user=customer,
                stylist=stylist,
                service=service,
                comment_text=comment_text,
                is_active=False,
            )

        Scoring.objects.update_or_create(
            comment=comment_obj,
            defaults={
                "score": score,
                "scoring_user": customer,
                "salon": salon,
                "stylist": stylist,
                "service": service,
            },
        )

        return comment_obj

    def post(self, request, *args, **kwargs):
        if _review_post_payload_too_large(request):
            return HttpResponse("حجم اطلاعات دیدگاه بیش از حد مجاز است.", status=413)

        salon_id = _validated_salon_id(request.GET.get("salon_id"))
        salon = get_object_or_404(Salon, id=salon_id, is_active=True)

        customer, redirect_response = self._get_customer_or_redirect(request, salon)
        if redirect_response is not None:
            return redirect_response

        appointment_id = (request.POST.get("appointment_id") or "").strip()

        form = CommentScoringForm(request.POST, salon=salon, customer=customer)

        if not form.is_valid():
            stash_form_errors(request, form)
            messages.error(
                request,
                "اطلاعات دیدگاه نیاز به اصلاح دارد. موارد مشخص‌شده را بررسی کنید.",
            )
            return redirect(salon.get_absolute_url())

        comment_text = (form.cleaned_data.get("comment_text") or "").strip()
        score = form.cleaned_data.get("score")

        if len(comment_text) > _review_comment_max_chars():
            messages.error(
                request,
                "متن نظر بیش از حد مجاز است.",
            )
            return redirect(salon.get_absolute_url())

        if score not in {1, 2, 3, 4, 5}:
            messages.error(
                request,
                "امتیاز واردشده معتبر نیست.",
            )
            return redirect(salon.get_absolute_url())

        if not comment_text:
            messages.error(request, "متن نظر الزامی است.")
            return redirect(salon.get_absolute_url())

        linked_order = None

        if appointment_id:
            appointment, is_reviewable = self._get_owned_reviewable_appointment(
                appointment_id=appointment_id,
                customer=customer,
                salon=salon,
            )

            if not is_reviewable:
                messages.error(
                    request,
                    "ثبت دیدگاه فقط پس از پایان خدمت امکان‌پذیر است.",
                )
                return redirect(salon.get_absolute_url())

            # وقتی appointment_id داریم، به stylist/service ارسالی از POST اعتماد نمی‌کنیم.
            stylist = appointment.stylist
            service = appointment.service
            linked_order = appointment.order

        else:
            stylist = form.cleaned_data.get("stylist")
            service = form.cleaned_data.get("service")

            linked_order = find_reviewable_order_for_customer(
                customer=customer,
                salon=salon,
                stylist=stylist,
                service=service,
                appointment_id=None,
            )

            if linked_order is None:
                messages.error(
                    request,
                    "ثبت دیدگاه فقط پس از پایان خدمت امکان‌پذیر است.",
                )
                return redirect(salon.get_absolute_url())

        if stylist is None or service is None:
            messages.error(request, "برای ثبت دیدگاه، خدمت و متخصص معتبر نیست.")
            return redirect(salon.get_absolute_url())

        self._upsert_comment_and_score(
            salon=salon,
            customer=customer,
            stylist=stylist,
            service=service,
            comment_text=comment_text,
            score=score,
        )

        if linked_order is not None:
            mark_review_completed(linked_order)

        messages.success(
            request,
            "نظر و امتیاز شما با موفقیت ثبت شد. نظر شما پس از تایید نمایش داده خواهد شد.",
        )
        return redirect(salon.get_absolute_url())


# -----------------------------------------------------------------------------------------------
def addScore(request):
    serviceId = request.GET.get("serviceId")
    score = request.GET.get("score")

    service = Services.objects.get(id=serviceId)

    Scoring.objects.create(service=service, scoring_user=request.user, score=score)
    return HttpResponse("امتیاز شما با موفقیت ثبت شد ")


# --------------------------------------------------------------------------------
@require_POST
def addFavorite(request):
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if not request.user.is_authenticated:
        if is_ajax:
            return JsonResponse(
                {
                    "ok": False,
                    "message": "ابتدا وارد حساب کاربری شوید.",
                },
                status=401,
                json_dumps_params={"ensure_ascii": False},
            )

        messages.error(
            request, "برای افزودن به علاقه‌مندی‌ها ابتدا وارد حساب شوید.", "danger"
        )
        return redirect_to_login(request.get_full_path(), login_url="accounts:login")

    salon_id = request.POST.get("salonId") or request.POST.get("salon_id") or ""

    if not str(salon_id).isdigit():
        message = "شناسه مجموعه برای علاقه‌مندی معتبر نیست."
        if is_ajax:
            return JsonResponse(
                {"ok": False, "message": message},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        messages.error(request, message, "danger")
        return redirect(request.META.get("HTTP_REFERER") or "search:search_page")

    salon = Salon.objects.filter(id=salon_id, is_active=True).first()
    if not salon:
        message = "مجموعه موردنظر پیدا نشد یا فعال نیست."
        if is_ajax:
            return JsonResponse(
                {"ok": False, "message": message},
                status=404,
                json_dumps_params={"ensure_ascii": False},
            )

        messages.error(request, message, "danger")
        return redirect(request.META.get("HTTP_REFERER") or "search:search_page")

    customer = Customer.objects.filter(user=request.user).first()
    if not customer:
        message = "برای استفاده از علاقه‌مندی‌ها باید با حساب مشتری وارد شوید."
        if is_ajax:
            return JsonResponse(
                {"ok": False, "message": message},
                status=403,
                json_dumps_params={"ensure_ascii": False},
            )

        messages.error(request, message, "danger")
        return redirect("accounts:customer_panel")

    favorite = Favorits.objects.filter(favorite_user=customer, salon=salon).first()

    if favorite:
        favorite.delete()
        message = "حذف شد"
        is_favorite = False
        action = "removed"
    else:
        Favorits.objects.create(salon=salon, favorite_user=customer)
        message = "اضافه شد"
        is_favorite = True
        action = "added"

    if is_ajax:
        return JsonResponse(
            {
                "ok": True,
                "message": message,
                "action": action,
                "is_favorite": is_favorite,
            },
            json_dumps_params={"ensure_ascii": False},
        )

    messages.success(request, message)
    return redirect(request.META.get("HTTP_REFERER") or "csf:favorite_salons")


# ----------------------------------------------------------------------------------------------------
def get_favorite_salons(request):
    if not request.user.is_authenticated:
        messages.error(request, "ابتدا وارد حساب کاربری شوید.", "danger")
        return redirect("accounts:login")

    if not hasattr(request.user, "customer_profile"):
        messages.error(
            request,
            "برای مشاهده علاقه‌مندی‌ها ابتدا پروفایل مشتری خود را تکمیل کنید.",
            "danger",
        )
        return redirect("accounts:customer_panel")

    customer = request.user.customer_profile

    favorite_salon_ids = Favorits.objects.filter(
        favorite_user=customer,
        salon__is_active=True,
        salon__isnull=False,
    ).values_list("salon_id", flat=True)

    salons_qs = (
        Salon.objects.filter(
            id__in=favorite_salon_ids,
            is_active=True,
        )
        .annotate(
            avg_score=Avg("scoring_salon__score"),
            num_scores=Count("scoring_salon", distinct=True),
        )
        .distinct()
    )

    return render(request, "csf/partials/favorite_salons.html", {"salons": salons_qs})


# -----------------------------------------------------------------------------------------------------
@login_required
@require_POST
def approve_comment(request, comment_id, customer_id):
    salon_manager = getattr(request.user, "salon_manager_profile", None)
    if salon_manager is None:
        return JsonResponse(
            {"success": False, "error": "access_denied"},
            status=403,
        )

    comment = get_object_or_404(
        Comments.objects.select_related("salon", "comment_user", "approved_user"),
        id=comment_id,
        comment_user_id=customer_id,
        salon__salon_manager=salon_manager,
        salon__is_active=True,
    )

    if not comment.is_active or comment.approved_user_id != request.user.id:
        comment.is_active = True
        comment.approved_user = request.user
        comment.save(update_fields=["is_active", "approved_user"])

    return JsonResponse({"success": True})
