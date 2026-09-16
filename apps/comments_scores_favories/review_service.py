from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.models import Customer
from .models import Comments, Scoring


class DuplicateReviewError(ValidationError):
    pass


@transaction.atomic
def create_customer_review_once(*, customer, salon, stylist, service, comment_text, score):
    """Create one review per customer/salon/stylist/service tuple.

    Locking the customer serializes concurrent submissions for the same account so
    two entry points cannot both pass the existence check and create duplicates.
    Historical duplicate rows are left untouched; this function only prevents new
    duplicates and therefore requires no destructive data migration.
    """
    Customer.objects.select_for_update().get(pk=customer.pk)

    if Comments.objects.filter(
        comment_user=customer,
        salon=salon,
        stylist=stylist,
        service=service,
    ).exists():
        raise DuplicateReviewError("برای این خدمت و متخصص قبلاً دیدگاه ثبت کرده‌اید.")

    comment = Comments.objects.create(
        comment_user=customer,
        salon=salon,
        stylist=stylist,
        service=service,
        comment_text=comment_text,
        is_active=False,
    )
    Scoring.objects.create(
        comment=comment,
        scoring_user=customer,
        salon=salon,
        stylist=stylist,
        service=service,
        score=score,
    )
    return comment
