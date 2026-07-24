from django.core.exceptions import ValidationError


def require_salon_scope(salon, *, message="برای عملیات مالی، مجموعه باید مشخص باشد."):
    if salon is None:
        raise ValidationError(message)


def assert_wallet_request_belongs_to_salon(withdrawal_request, salon):
    require_salon_scope(salon)

    if withdrawal_request.salon_id != salon.id:
        raise ValidationError("این درخواست برداشت مربوط به این مجموعه نیست.")


def assert_wallet_transaction_belongs_to_salon(transaction, salon):
    require_salon_scope(salon)

    if transaction.salon_id != salon.id:
        raise ValidationError("این تراکنش مالی مربوط به این مجموعه نیست.")
