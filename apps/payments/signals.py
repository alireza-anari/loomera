from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Wallet, Payment


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_wallet(sender, instance, created, **kwargs):
    """
    سیگنالی برای ساخت خودکار کیف پول هنگام ایجاد کاربر جدید
    """
    if created:
        Wallet.objects.create(user=instance)


# -----------------------------------------------------------------------------
@receiver(post_save, sender=Payment)
def top_up_wallet_on_successful_payment(sender, instance, created, **kwargs):
    """
    فقط پرداخت‌های موفقِ شارژ کیف پول باید موجودی کیف پول را افزایش دهند.
    پرداخت‌های مربوط به appointment نباید باعث شارژ کیف پول شوند.
    """
    if not created:
        return

    if not instance.is_finally or instance.state != Payment.State.SUCCESS:
        return

    if instance.purpose != Payment.Purpose.WALLET:
        return

    try:
        user_wallet = instance.customer.user.wallet
        user_wallet.deposit(
            amount=instance.amount,
            description=f"شارژ کیف پول از طریق پرداخت شماره {instance.ref_id}",
        )
    except Wallet.DoesNotExist:
        pass
