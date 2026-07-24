from django.db import models
from django.utils import timezone
from django.db import models, transaction
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import CheckConstraint, Q, F, Sum, Value
from django.db.models.functions import Coalesce
from apps.accounts.models import Customer
from apps.orders.models import Order


def _user_label(user):
    return (
        getattr(user, "username", None)
        or getattr(user, "mobile_number", None)
        or getattr(user, "name", None)
        or str(user)
    )


# ------------------------------------------------------------------------------------------------------
class Payment(models.Model):
    class Provider(models.TextChoices):
        ZARINPAL = "zarinpal", "زرین‌پال"
        ZIBAL = "zibal", "زیبال"
        WALLET = "wallet", "کیف پول"
        MANUAL = "manual", "دستی"
        MOCK = "mock", "شبیه‌ساز"

    class Purpose(models.TextChoices):
        WALLET = "wallet", "کیف پول"
        APPOINTMENT = "appointment", "رزرو"

    class State(models.TextChoices):
        INITIATED = "initiated", "شروع شده"
        PENDING = "pending", "در انتظار پرداخت"
        SUCCESS = "success", "موفق"
        FAILED = "failed", "ناموفق"
        CANCELLED = "cancelled", "لغو شده"

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="payment_order",
        verbose_name="سفارش",
        null=True,
        blank=True,
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="payment_customer",
        verbose_name="مشتری",
    )
    register_date = models.DateTimeField(
        default=timezone.now, verbose_name="زمان پرداخت "
    )
    update_date = models.DateTimeField(auto_now=True, verbose_name="زمان ویرایش پرداخت")
    amount = models.DecimalField(
        verbose_name="مبلغ پرداخت", max_digits=10, decimal_places=0
    )
    is_finally = models.BooleanField(verbose_name="وضعیت پرداخت", default=False)
    provider = models.CharField(
        max_length=20,
        choices=Provider.choices,
        default=Provider.ZARINPAL,
        verbose_name="ارائه‌دهنده پرداخت",
    )
    purpose = models.CharField(
        max_length=20,
        choices=Purpose.choices,
        default=Purpose.WALLET,
        verbose_name="کاربری پرداخت",
    )
    state = models.CharField(
        max_length=20,
        choices=State.choices,
        default=State.INITIATED,
        verbose_name="وضعیت چرخه پرداخت",
    )
    description = models.TextField(verbose_name="توضیحات پرداخت")
    status_code = models.IntegerField(verbose_name="کد وضعیت", null=True, blank=True)
    ref_id = models.CharField(
        max_length=50,
        verbose_name="شناسه نهایی پرداخت",
        null=True,
        blank=True,
        unique=True,
    )
    gateway_track_id = models.CharField(
        max_length=80,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="شناسه رهگیری درگاه",
    )
    callback_token = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="توکن بازگشت",
    )
    idempotency_key = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        verbose_name="کلید idempotency",
    )
    sandbox_mode = models.BooleanField(default=True, verbose_name="حالت تست")
    verified_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان تایید")
    meta = models.JSONField(default=dict, blank=True, verbose_name="فراداده پرداخت")

    def __str__(self):
        return f"{self.order}\t {self.customer}\t{self.ref_id}"

    class Meta:
        verbose_name = "پرداخت"
        verbose_name_plural = "پرداخت ها"

    def mark_success(self, *, ref_id=None, track_id=None, status_code=100, meta=None):
        self.is_finally = True
        self.state = self.State.SUCCESS
        self.status_code = status_code
        if ref_id:
            self.ref_id = str(ref_id)
        if track_id:
            self.gateway_track_id = str(track_id)
        if meta:
            self.meta = {**(self.meta or {}), **meta}
        self.verified_at = timezone.now()
        self.save()

    def mark_pending(self, *, status_code=None, meta=None):
        self.is_finally = False
        self.state = self.State.PENDING
        self.status_code = status_code

        if meta:
            self.meta = {
                **(self.meta or {}),
                **meta,
            }

        self.save(
            update_fields=[
                "is_finally",
                "state",
                "status_code",
                "meta",
            ]
        )

    def mark_failure(self, *, state=None, status_code=None, meta=None):
        self.is_finally = False
        self.state = state or self.State.FAILED
        self.status_code = status_code
        if meta:
            self.meta = {**(self.meta or {}), **meta}
        self.save(
            update_fields=[
                "is_finally",
                "state",
                "status_code",
                "meta",
            ]
        )


# --------------------------------------------------------------------------------------------------------
class Wallet(models.Model):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet",
        verbose_name="کاربر",
    )

    balance = models.DecimalField(
        verbose_name="موجودی",
        max_digits=10,
        decimal_places=0,
        default=0,
    )

    class Meta:
        verbose_name = "کیف پول"
        verbose_name_plural = "کیف پول‌ها"
        constraints = [
            CheckConstraint(check=Q(balance__gte=0), name="balance_gte_zero")
        ]

    def __str__(self):
        return f"کیف پول کاربر: {self.user.name} - موجودی: {self.balance}"

    def deposit(self, amount: int, description: str, transaction_type=None, order=None):

        if amount <= 0:
            raise ValidationError("مبلغ واریز باید مثبت باشد.")

        with transaction.atomic():
            # قفل کردن رکورد برای جلوگیری از race condition
            _wallet = Wallet.objects.select_for_update().get(pk=self.pk)

            # استفاده از F() expression برای آپدیت امن در دیتابیس
            _wallet.balance = F("balance") + amount
            _wallet.save()
            _wallet.refresh_from_db()

            # ثبت رکورد تراکنش
            WalletTransaction.objects.create(
                wallet=_wallet,
                transaction_type=transaction_type
                or WalletTransaction.TransactionType.DEPOSIT,
                amount=amount,
                running_balance=_wallet.balance,  # موجودی پس از آپدیت
                description=description,
                order=order,
            )

        # رفرش کردن آبجکت فعلی برای نمایش موجودی جدید
        self.refresh_from_db()

    def withdraw(
        self, amount: int, description: str, transaction_type=None, order=None
    ):
        """
        متد امن برای برداشت وجه از کیف پول
        """
        if amount <= 0:
            raise ValidationError("مبلغ برداشت باید مثبت باشد.")

        with transaction.atomic():
            # قفل کردن رکورد برای جلوگیری از race condition
            _wallet = Wallet.objects.select_for_update().get(pk=self.pk)

            if _wallet.balance < amount:
                raise ValidationError("موجودی کافی نیست.")

            _wallet.balance = F("balance") - amount
            _wallet.save()
            _wallet.refresh_from_db()

            # ثبت رکورد تراکنش
            WalletTransaction.objects.create(
                wallet=_wallet,
                transaction_type=transaction_type
                or WalletTransaction.TransactionType.WITHDRAW,
                amount=-amount,  # ذخیره مبلغ برداشت به صورت منفی
                running_balance=_wallet.balance,
                description=description,
                order=order,
            )

        self.refresh_from_db()


# --------------------------------------------------------------------------------------------------------
class WalletTransaction(models.Model):

    class TransactionType(models.TextChoices):
        DEPOSIT = "DEPOSIT", "واریز"
        WITHDRAW = "WITHDRAW", "برداشت"
        PURCHASE = "PURCHASE", "خرید"
        REFUND = "REFUND", "بازگشت وجه"
        WITHDRAW_RESTORE = "WITHDRAW_RESTORE", "بازگشت برداشت ردشده"

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name="کیف پول",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wallet_transactions",
        verbose_name="سفارش مرتبط",
    )

    transaction_type = models.CharField(
        max_length=20,  # قبلاً 10 بود
        choices=TransactionType.choices,
        verbose_name="نوع تراکنش",
    )

    amount = models.DecimalField(verbose_name="مبلغ", max_digits=10, decimal_places=0)

    running_balance = models.DecimalField(
        verbose_name="موجودی پس از تراکنش",
        max_digits=10,
        decimal_places=0,
        help_text="موجودی کیف پول بعد از انجام این تراکنش",
    )

    description = models.TextField(verbose_name="توضیحات", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "تراکنش کیف پول"
        verbose_name_plural = "تراکنش‌های کیف پول"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_transaction_type_display()} مبلغ {self.amount} برای {_user_label(self.wallet.user)}"


class WalletWithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار بررسی"
        APPROVED = "approved", "تایید شده"
        REJECTED = "rejected", "رد شده"
        CANCELLED = "cancelled", "لغو شده"

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name="withdrawal_requests",
        verbose_name="کیف پول",
    )
    amount = models.DecimalField(
        max_digits=10, decimal_places=0, verbose_name="مبلغ برداشت"
    )

    # ستون‌های جدید
    iban = models.CharField(max_length=26, verbose_name="شماره شبا")
    account_holder_name = models.CharField(max_length=120, verbose_name="نام صاحب حساب")
    bank_name = models.CharField(
        max_length=80, blank=True, default="", verbose_name="نام بانک"
    )

    # ستون‌های legacy برای سازگاری با دیتابیس‌های قدیمی
    legacy_destination_iban = models.CharField(
        max_length=26,
        blank=True,
        default="",
        editable=False,
        db_column="destination_iban",
        verbose_name="ستون سازگاری شبا",
    )
    legacy_destination_account_holder_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        editable=False,
        db_column="destination_account_holder_name",
        verbose_name="ستون سازگاری صاحب حساب",
    )
    legacy_destination_bank_name = models.CharField(
        max_length=80,
        blank=True,
        default="",
        editable=False,
        db_column="destination_bank_name",
        verbose_name="ستون سازگاری بانک",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="وضعیت",
    )
    note = models.TextField(blank=True, default="", verbose_name="یادداشت")
    payment_receipt = models.FileField(
        upload_to="wallet_withdrawal_receipts/",
        null=True,
        blank=True,
        verbose_name="رسید واریز",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان بررسی")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    def approve(self, *, note: str = ""):
        if self.status != self.Status.PENDING:
            raise ValidationError("فقط درخواست‌های در انتظار را می‌توان تایید کرد.")
        self.status = self.Status.APPROVED
        self.reviewed_at = timezone.now()
        if note:
            self.note = note
        self.save(update_fields=["status", "reviewed_at", "note", "updated_at"])
        return self

    def reject(self, *, note: str = ""):
        if self.status != self.Status.PENDING:
            raise ValidationError("فقط درخواست‌های در انتظار را می‌توان رد کرد.")

        with transaction.atomic():
            request = WalletWithdrawalRequest.objects.select_for_update().get(
                pk=self.pk
            )
            if request.status != self.Status.PENDING:
                raise ValidationError("این درخواست قبلاً بررسی شده است.")

            request.status = self.Status.REJECTED
            request.reviewed_at = timezone.now()
            request.note = (
                note
                or "این درخواست توسط تیم مالی رد شد و مبلغ به کیف پول برگشت داده شد."
            )
            request.save(update_fields=["status", "reviewed_at", "note", "updated_at"])

        self.refresh_from_db()
        return self

    def cancel(self, *, note: str = ""):
        if self.status != self.Status.PENDING:
            raise ValidationError("فقط درخواست‌های در انتظار را می‌توان لغو کرد.")

        with transaction.atomic():
            request = WalletWithdrawalRequest.objects.select_for_update().get(
                pk=self.pk
            )
            if request.status != self.Status.PENDING:
                raise ValidationError("این درخواست قبلاً بررسی شده است.")

            request.status = self.Status.CANCELLED
            request.reviewed_at = timezone.now()
            request.note = (
                note
                or "درخواست برداشت توسط کاربر لغو شد و مبلغ به کیف پول برگشت داده شد."
            )
            request.save(update_fields=["status", "reviewed_at", "note", "updated_at"])

        self.refresh_from_db()
        return self

    def _restore_balance_if_needed(self):
        amount = int(self.amount or 0)
        wallet = Wallet.objects.select_for_update().get(pk=self.wallet_id)

        wallet.balance = F("balance") + amount
        wallet.save(update_fields=["balance"])
        wallet.refresh_from_db()

        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type=WalletTransaction.TransactionType.WITHDRAW_RESTORE,
            amount=amount,
            running_balance=wallet.balance,
            description="بازگشت مبلغ برداشت ردشده/لغوشده",
        )

    def save(self, *args, **kwargs):
        is_create = self._state.adding
        previous_status = None

        if not is_create and self.pk:
            previous_status = (
                WalletWithdrawalRequest.objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )

        should_restore = previous_status == self.Status.PENDING and self.status in {
            self.Status.REJECTED,
            self.Status.CANCELLED,
        }

        if (
            self.status
            in {self.Status.APPROVED, self.Status.REJECTED, self.Status.CANCELLED}
            and not self.reviewed_at
        ):
            self.reviewed_at = timezone.now()
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("reviewed_at")
                kwargs["update_fields"] = list(update_fields)

        with transaction.atomic():
            if should_restore:
                self._restore_balance_if_needed()
                if not self.note:
                    self.note = (
                        "درخواست برداشت رد/لغو شد و مبلغ به کیف پول برگشت داده شد."
                    )
                    update_fields = kwargs.get("update_fields")
                    if update_fields is not None:
                        update_fields = set(update_fields)
                        update_fields.add("note")
                        kwargs["update_fields"] = list(update_fields)

            return super().save(*args, **kwargs)

    class Meta:
        verbose_name = "درخواست برداشت کیف پول"
        verbose_name_plural = "درخواست‌های برداشت کیف پول"
        ordering = ["-created_at"]

    def __str__(self):
        return f"برداشت {self.amount} برای {_user_label(self.wallet.user)}"


# -----------------------------------------------------------------------------------------------------------------


class SalonSettlement(models.Model):
    class PayoutState(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment", "در انتظار پرداخت"
        MANUAL_COLLECTION = "manual_collection", "پرداخت در سالن"
        READY = "ready", "آماده تسویه"
        HOLD = "hold", "نیازمند بررسی"
        PAID = "paid", "تسویه‌شده"
        CANCELLED = "cancelled", "لغوشده"

    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="salon_settlement",
        verbose_name="سفارش",
    )
    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.CASCADE,
        related_name="settlements",
        verbose_name="سالن",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="salon_settlements",
        verbose_name="مشتری",
    )
    payment = models.OneToOneField(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="settlement",
        verbose_name="پرداخت",
    )
    payment_method = models.CharField(
        max_length=20, blank=True, default="", verbose_name="روش پرداخت"
    )
    payment_provider = models.CharField(
        max_length=20, blank=True, default="", verbose_name="درگاه پرداخت"
    )
    gross_services_amount = models.PositiveIntegerField(
        default=0, verbose_name="جمع خدمات"
    )
    discount_amount = models.PositiveIntegerField(default=0, verbose_name="مبلغ تخفیف")
    tax_amount = models.PositiveIntegerField(default=0, verbose_name="مالیات")
    paid_amount = models.PositiveIntegerField(default=0, verbose_name="مبلغ پرداخت‌شده")
    refund_amount = models.PositiveIntegerField(
        default=0, verbose_name="مبلغ بازگشت‌داده‌شده"
    )
    first_visit_commission_applies = models.BooleanField(
        default=False, verbose_name="کارمزد اولین مراجعه"
    )
    platform_commission_percent = models.PositiveSmallIntegerField(
        default=0, verbose_name="درصد کارمزد"
    )
    platform_commission_amount = models.PositiveIntegerField(
        default=0, verbose_name="مبلغ کارمزد"
    )
    net_amount_due_to_salon = models.PositiveIntegerField(
        default=0, verbose_name="خالص قابل تسویه"
    )
    payout_state = models.CharField(
        max_length=20,
        choices=PayoutState.choices,
        default=PayoutState.AWAITING_PAYMENT,
        verbose_name="وضعیت تسویه",
    )
    payout_hold_reason = models.CharField(
        max_length=255, blank=True, default="", verbose_name="دلیل نگه‌داری"
    )
    eligible_for_payout_at = models.DateTimeField(
        null=True, blank=True, verbose_name="زمان آمادگی تسویه"
    )
    paid_out_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان تسویه")
    policy_snapshot = models.JSONField(
        default=dict, blank=True, verbose_name="اسنپ‌شات قوانین"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "سند تسویه سالن"
        verbose_name_plural = "اسناد تسویه سالن"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.salon} - {self.order.order_number}"


class SalonWallet(models.Model):
    salon = models.OneToOneField(
        "salons.Salon",
        on_delete=models.CASCADE,
        related_name="finance_wallet",
        verbose_name="سالن",
    )
    available_balance = models.DecimalField(
        max_digits=10, decimal_places=0, default=0, verbose_name="موجودی قابل برداشت"
    )
    pending_balance = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        default=0,
        verbose_name="موجودی در انتظار تسویه",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "کیف پول مالی سالن"
        verbose_name_plural = "کیف پول‌های مالی سالن"
        constraints = [
            CheckConstraint(
                check=Q(available_balance__gte=0), name="sal_wallet_avail_gte0"
            ),
            CheckConstraint(
                check=Q(pending_balance__gte=0), name="salon_wallet_pending_gte_zero"
            ),
        ]

    def __str__(self):
        return f"کیف پول مالی {self.salon.salon_name}"

    @property
    def total_balance(self):
        return int(self.available_balance or 0) + int(self.pending_balance or 0)

    def _record(
        self,
        *,
        tx_type,
        pending_delta=0,
        available_delta=0,
        description="",
        order=None,
        settlement=None,
    ):
        if not pending_delta and not available_delta:
            return None
        with transaction.atomic():
            wallet = SalonWallet.objects.select_for_update().get(pk=self.pk)
            new_pending = int(wallet.pending_balance or 0) + int(pending_delta or 0)
            new_available = int(wallet.available_balance or 0) + int(
                available_delta or 0
            )
            if new_pending < 0:
                raise ValidationError("موجودی در انتظار تسویه سالن کافی نیست.")
            if new_available < 0:
                raise ValidationError("موجودی قابل برداشت سالن کافی نیست.")
            wallet.pending_balance = new_pending
            wallet.available_balance = new_available
            wallet.save(
                update_fields=["pending_balance", "available_balance", "updated_at"]
            )
            tx = SalonWalletTransaction.objects.create(
                wallet=wallet,
                transaction_type=tx_type,
                pending_delta=int(pending_delta or 0),
                available_delta=int(available_delta or 0),
                pending_balance_after=new_pending,
                available_balance_after=new_available,
                description=description,
                order=order,
                settlement=settlement,
            )
        self.refresh_from_db()
        return tx

    def add_pending(
        self, amount: int, *, description: str, order=None, settlement=None
    ):
        return self._record(
            tx_type=SalonWalletTransaction.TransactionType.SALE_PENDING,
            pending_delta=int(amount),
            description=description,
            order=order,
            settlement=settlement,
        )

    def release_pending(
        self, amount: int, *, description: str, order=None, settlement=None
    ):
        return self._record(
            tx_type=SalonWalletTransaction.TransactionType.PENDING_RELEASE,
            pending_delta=-int(amount),
            available_delta=int(amount),
            description=description,
            order=order,
            settlement=settlement,
        )

    def reverse_pending(
        self, amount: int, *, description: str, order=None, settlement=None
    ):
        return self._record(
            tx_type=SalonWalletTransaction.TransactionType.REFUND_DEBIT,
            pending_delta=-int(amount),
            description=description,
            order=order,
            settlement=settlement,
        )

    def reverse_available(
        self, amount: int, *, description: str, order=None, settlement=None
    ):
        return self._record(
            tx_type=SalonWalletTransaction.TransactionType.REFUND_DEBIT,
            available_delta=-int(amount),
            description=description,
            order=order,
            settlement=settlement,
        )

    def request_withdraw(
        self, amount: int, *, description: str, order=None, settlement=None
    ):
        return self._record(
            tx_type=SalonWalletTransaction.TransactionType.WITHDRAW_REQUEST,
            available_delta=-int(amount),
            description=description,
            order=order,
            settlement=settlement,
        )


class SalonWalletTransaction(models.Model):
    class TransactionType(models.TextChoices):
        SALE_PENDING = "sale_pending", "ثبت فروش آنلاین"
        PENDING_RELEASE = "pending_release", "انتقال به موجودی قابل برداشت"
        REFUND_DEBIT = "refund_debit", "کسر بابت لغو/بازگشت وجه"
        WITHDRAW_REQUEST = "withdraw_request", "درخواست دریافت"
        WITHDRAW_RESTORE = "withdraw_restore", "بازگشت دریافت ردشده"
        MANUAL_ADJUSTMENT = "manual_adjustment", "اصلاح دستی"

    wallet = models.ForeignKey(
        SalonWallet,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name="کیف پول مالی سالن",
    )
    transaction_type = models.CharField(
        max_length=32, choices=TransactionType.choices, verbose_name="نوع تراکنش"
    )
    pending_delta = models.IntegerField(
        default=0, verbose_name="تغییر موجودی در انتظار"
    )
    available_delta = models.IntegerField(
        default=0, verbose_name="تغییر موجودی قابل برداشت"
    )
    pending_balance_after = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        default=0,
        verbose_name="موجودی در انتظار بعد از تراکنش",
    )
    available_balance_after = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        default=0,
        verbose_name="موجودی قابل برداشت بعد از تراکنش",
    )
    description = models.TextField(blank=True, default="", verbose_name="توضیحات")
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salon_wallet_transactions",
        verbose_name="سفارش مرتبط",
    )
    settlement = models.ForeignKey(
        "payments.SalonSettlement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wallet_transactions",
        verbose_name="سند تسویه مرتبط",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")

    class Meta:
        verbose_name = "تراکنش کیف پول سالن"
        verbose_name_plural = "تراکنش‌های کیف پول سالن"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.wallet.salon.salon_name} - {self.get_transaction_type_display()}"


class SalonWalletWithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار بررسی"
        APPROVED = "approved", "تایید شده"
        REJECTED = "rejected", "رد شده"
        CANCELLED = "cancelled", "لغو شده"

    wallet = models.ForeignKey(
        SalonWallet,
        on_delete=models.CASCADE,
        related_name="withdrawal_requests",
        verbose_name="کیف پول مالی سالن",
    )
    amount = models.DecimalField(
        max_digits=10, decimal_places=0, verbose_name="مبلغ برداشت"
    )

    # ستون‌های جدید
    iban = models.CharField(max_length=26, verbose_name="شماره شبا")
    account_holder_name = models.CharField(max_length=120, verbose_name="نام صاحب حساب")
    bank_name = models.CharField(
        max_length=80, blank=True, default="", verbose_name="نام بانک"
    )

    # ستون‌های legacy برای سازگاری با دیتابیس‌های قدیمی
    legacy_destination_iban = models.CharField(
        max_length=26,
        blank=True,
        default="",
        editable=False,
        db_column="destination_iban",
        verbose_name="ستون سازگاری شبا",
    )
    legacy_destination_account_holder_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        editable=False,
        db_column="destination_account_holder_name",
        verbose_name="ستون سازگاری صاحب حساب",
    )
    legacy_destination_bank_name = models.CharField(
        max_length=80,
        blank=True,
        default="",
        editable=False,
        db_column="destination_bank_name",
        verbose_name="ستون سازگاری بانک",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="وضعیت",
    )
    note = models.TextField(blank=True, default="", verbose_name="یادداشت")
    payment_receipt = models.FileField(
        upload_to="salon_wallet_withdrawal_receipts/",
        null=True,
        blank=True,
        verbose_name="رسید واریز",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان بررسی")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    def approve(self, *, note: str = ""):
        if self.status != self.Status.PENDING:
            raise ValidationError("فقط درخواست‌های در انتظار را می‌توان تایید کرد.")
        self.status = self.Status.APPROVED
        self.reviewed_at = timezone.now()
        if note:
            self.note = note
        self.save(update_fields=["status", "reviewed_at", "note", "updated_at"])
        return self

    def reject(self, *, note: str = ""):
        if self.status != self.Status.PENDING:
            raise ValidationError("فقط درخواست‌های در انتظار را می‌توان رد کرد.")

        with transaction.atomic():
            request = SalonWalletWithdrawalRequest.objects.select_for_update().get(
                pk=self.pk
            )
            if request.status != self.Status.PENDING:
                raise ValidationError("این درخواست قبلاً بررسی شده است.")

            request.status = self.Status.REJECTED
            request.reviewed_at = timezone.now()
            request.note = (
                note
                or "این درخواست توسط تیم مالی رد شد و مبلغ به موجودی قابل برداشت سالن برگشت داده شد."
            )
            request.save(update_fields=["status", "reviewed_at", "note", "updated_at"])

        self.refresh_from_db()
        return self

    def cancel(self, *, note: str = ""):
        if self.status != self.Status.PENDING:
            raise ValidationError("فقط درخواست‌های در انتظار را می‌توان لغو کرد.")

        with transaction.atomic():
            request = SalonWalletWithdrawalRequest.objects.select_for_update().get(
                pk=self.pk
            )
            if request.status != self.Status.PENDING:
                raise ValidationError("این درخواست قبلاً بررسی شده است.")

            request.status = self.Status.CANCELLED
            request.reviewed_at = timezone.now()
            request.note = (
                note
                or "درخواست برداشت توسط مدیر سالن لغو شد و مبلغ به موجودی قابل برداشت برگشت داده شد."
            )
            request.save(update_fields=["status", "reviewed_at", "note", "updated_at"])

        self.refresh_from_db()
        return self

    def _restore_balance_if_needed(self):
        amount = int(self.amount or 0)
        wallet = SalonWallet.objects.select_for_update().get(pk=self.wallet_id)

        wallet.available_balance = F("available_balance") + amount
        wallet.save(update_fields=["available_balance", "updated_at"])
        wallet.refresh_from_db()

        SalonWalletTransaction.objects.create(
            wallet=wallet,
            transaction_type=SalonWalletTransaction.TransactionType.WITHDRAW_RESTORE,
            pending_delta=0,
            available_delta=amount,
            pending_balance_after=wallet.pending_balance,
            available_balance_after=wallet.available_balance,
            description="بازگشت برداشت ردشده/لغوشده سالن",
        )

    def save(self, *args, **kwargs):
        is_create = self._state.adding
        previous_status = None

        if not is_create and self.pk:
            previous_status = (
                SalonWalletWithdrawalRequest.objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )

        should_restore = previous_status == self.Status.PENDING and self.status in {
            self.Status.REJECTED,
            self.Status.CANCELLED,
        }

        if (
            self.status
            in {self.Status.APPROVED, self.Status.REJECTED, self.Status.CANCELLED}
            and not self.reviewed_at
        ):
            self.reviewed_at = timezone.now()
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("reviewed_at")
                kwargs["update_fields"] = list(update_fields)

        with transaction.atomic():
            if should_restore:
                self._restore_balance_if_needed()
                if not self.note:
                    self.note = "درخواست برداشت رد/لغو شد و مبلغ به موجودی قابل برداشت سالن برگشت داده شد."
                    update_fields = kwargs.get("update_fields")
                    if update_fields is not None:
                        update_fields = set(update_fields)
                        update_fields.add("note")
                        kwargs["update_fields"] = list(update_fields)

            return super().save(*args, **kwargs)

    class Meta:
        verbose_name = "درخواست برداشت کیف پول سالن"
        verbose_name_plural = "درخواست‌های برداشت کیف پول سالن"
        ordering = ["-created_at"]

    def __str__(self):
        return f"برداشت {self.amount} برای سالن {self.wallet.salon.salon_name}"


# -----------------------------------------------------------------------------------------------------------------
# سند مالی هر آیتم رزرو
class OrderDetailFinancialSnapshot(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        FINALIZED = "finalized", "نهایی‌شده"
        REVERSED = "reversed", "برگشت‌خورده"

    order_detail = models.OneToOneField(
        "orders.OrderDetail",
        on_delete=models.CASCADE,
        related_name="financial_snapshot",
        verbose_name="آیتم رزرو",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="detail_financial_snapshots",
        verbose_name="سفارش",
    )
    settlement = models.ForeignKey(
        "payments.SalonSettlement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="detail_snapshots",
        verbose_name="سند تسویه سفارش",
    )
    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.CASCADE,
        related_name="ord_detail_fin_snapshots",
        verbose_name="سالن",
    )
    stylist = models.ForeignKey(
        "accounts.Stylist",
        on_delete=models.CASCADE,
        related_name="financial_snapshots",
        verbose_name="آرایشگر",
    )
    service = models.ForeignKey(
        "services.Services",
        on_delete=models.CASCADE,
        related_name="financial_snapshots",
        verbose_name="خدمت",
    )
    commission_rule = models.ForeignKey(
        "services.StylistCommissionRule",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="financial_snapshots",
        verbose_name="قانون سهم استفاده‌شده",
    )

    payment_method = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="روش پرداخت",
    )
    payment_provider = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="درگاه پرداخت",
    )

    gross_amount = models.PositiveIntegerField(default=0, verbose_name="مبلغ خام خدمت")
    discount_allocated = models.PositiveIntegerField(
        default=0, verbose_name="تخفیف تخصیص‌یافته"
    )
    paid_amount_allocated = models.PositiveIntegerField(
        default=0, verbose_name="مبلغ پرداخت‌شده تخصیص‌یافته"
    )
    platform_commission_allocated = models.PositiveIntegerField(
        default=0, verbose_name="کارمزد پلتفرم تخصیص‌یافته"
    )
    net_after_platform = models.PositiveIntegerField(
        default=0, verbose_name="خالص بعد از کارمزد پلتفرم"
    )

    material_cost_total = models.PositiveIntegerField(
        default=0, verbose_name="کل هزینه مواد"
    )
    material_cost_paid_by_salon = models.PositiveIntegerField(
        default=0, verbose_name="هزینه مواد با سالن"
    )
    material_cost_paid_by_stylist = models.PositiveIntegerField(
        default=0, verbose_name="هزینه مواد با آرایشگر"
    )

    share_base_amount = models.PositiveIntegerField(
        default=0, verbose_name="مبنای محاسبه سهم"
    )

    stylist_gross_share = models.PositiveIntegerField(
        default=0, verbose_name="سهم ناخالص آرایشگر"
    )
    stylist_material_deduction = models.PositiveIntegerField(
        default=0, verbose_name="کسر هزینه مواد از آرایشگر"
    )
    stylist_net_share = models.PositiveIntegerField(
        default=0, verbose_name="سهم خالص آرایشگر"
    )

    salon_gross_share = models.PositiveIntegerField(
        default=0, verbose_name="سهم ناخالص سالن"
    )
    salon_material_deduction = models.PositiveIntegerField(
        default=0, verbose_name="کسر هزینه مواد از سالن"
    )
    salon_net_share = models.PositiveIntegerField(
        default=0, verbose_name="سهم خالص سالن"
    )
    salon_net_profit = models.PositiveIntegerField(
        default=0, verbose_name="سود خالص سالن"
    )
    extra_charges_amount = models.PositiveIntegerField(
        default=0, verbose_name="هزینه‌های اضافه تأییدشده"
    )
    total_customer_paid = models.PositiveIntegerField(
        default=0, verbose_name="کل مبلغ پرداخت/ثبت‌شده مشتری"
    )
    salon_customer_compensation = models.PositiveIntegerField(
        default=0, verbose_name="جبران مشتری توسط سالن"
    )
    salon_refund_amount = models.PositiveIntegerField(
        default=0, verbose_name="مبلغ برگشت وجه"
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="وضعیت سند مالی",
    )

    rule_snapshot = models.JSONField(
        default=dict, blank=True, verbose_name="اسنپ‌شات قانون سهم"
    )
    material_snapshot = models.JSONField(
        default=list, blank=True, verbose_name="اسنپ‌شات مواد مصرفی"
    )
    calculation_snapshot = models.JSONField(
        default=dict, blank=True, verbose_name="جزئیات محاسبه"
    )

    finalized_at = models.DateTimeField(
        null=True, blank=True, verbose_name="زمان نهایی شدن"
    )
    reversed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان برگشت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    @property
    def is_finalized(self):
        return self.status == self.Status.FINALIZED

    def mark_finalized(self):
        if self.status == self.Status.REVERSED:
            raise ValidationError("سند مالی برگشت‌خورده را نمی‌توان نهایی کرد.")
        self.status = self.Status.FINALIZED
        self.finalized_at = timezone.now()
        self.save(update_fields=["status", "finalized_at", "updated_at"])
        return self

    def mark_reversed(self):
        if self.status == self.Status.REVERSED:
            return self
        self.status = self.Status.REVERSED
        self.reversed_at = timezone.now()
        self.save(update_fields=["status", "reversed_at", "updated_at"])
        return self

    def __str__(self):
        return f"سند مالی {self.order.order_number} / {self.service}"

    class Meta:
        verbose_name = "سند مالی آیتم رزرو"
        verbose_name_plural = "اسناد مالی آیتم‌های رزرو"
        ordering = ["-created_at", "-id"]
        constraints = [
            CheckConstraint(
                check=Q(gross_amount__gte=0), name="detail_fin_gross_gte_zero"
            ),
            CheckConstraint(
                check=Q(discount_allocated__gte=0), name="detail_fin_discount_gte_zero"
            ),
            CheckConstraint(
                check=Q(paid_amount_allocated__gte=0), name="detail_fin_paid_gte_zero"
            ),
            CheckConstraint(
                check=Q(platform_commission_allocated__gte=0),
                name="detail_fin_platform_gte_zero",
            ),
            CheckConstraint(
                check=Q(net_after_platform__gte=0),
                name="det_fin_net_plat_gte0",
            ),
            CheckConstraint(
                check=Q(material_cost_total__gte=0),
                name="detail_fin_mat_total_gte_zero",
            ),
            CheckConstraint(
                check=Q(stylist_net_share__gte=0), name="detail_fin_sty_net_gte_zero"
            ),
            CheckConstraint(
                check=Q(salon_net_share__gte=0), name="detail_fin_salon_net_gte_zero"
            ),
        ]


# -----------------------------------------------------------------------------------------------------------------
# کیف پول مالی آرایشگر
class StylistWallet(models.Model):
    stylist = models.OneToOneField(
        "accounts.Stylist",
        on_delete=models.CASCADE,
        related_name="finance_wallet",
        verbose_name="آرایشگر",
    )
    available_balance = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        default=0,
        verbose_name="مانده قابل دریافت",
    )
    pending_balance = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        default=0,
        verbose_name="موجودی در انتظار تسویه",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    @property
    def total_balance(self):
        return int(self.available_balance or 0) + int(self.pending_balance or 0)

    def _record(
        self,
        *,
        tx_type,
        pending_delta=0,
        available_delta=0,
        description="",
        salon=None,
        order=None,
        order_detail=None,
        financial_snapshot=None,
        withdrawal_request=None,
    ):
        resolved_salon = self._resolve_salon(
            salon=salon,
            order=order,
            order_detail=order_detail,
            financial_snapshot=financial_snapshot,
            withdrawal_request=withdrawal_request,
        )

        pending_delta = int(pending_delta or 0)
        available_delta = int(available_delta or 0)

        with transaction.atomic():
            wallet = StylistWallet.objects.select_for_update().get(pk=self.pk)

            # مانده اصلی wallet کلی است.
            # مانده سالن‌محور از روی transactionهای دارای salon محاسبه می‌شود.
            new_pending = int(wallet.pending_balance or 0) + pending_delta
            new_available = int(wallet.available_balance or 0) + available_delta

            if new_pending < 0:
                raise ValidationError("مانده در انتظار کیف پول کافی نیست.")

            if new_available < 0:
                raise ValidationError("مانده قابل برداشت کیف پول کافی نیست.")

            wallet.pending_balance = new_pending
            wallet.available_balance = new_available
            wallet.save(
                update_fields=[
                    "pending_balance",
                    "available_balance",
                    "updated_at",
                ]
            )

            tx = StylistWalletTransaction.objects.create(
                wallet=wallet,
                salon=resolved_salon,
                transaction_type=tx_type,
                pending_delta=pending_delta,
                available_delta=available_delta,
                pending_balance_after=new_pending,
                available_balance_after=new_available,
                description=description,
                order=order,
                order_detail=order_detail,
                financial_snapshot=financial_snapshot,
                withdrawal_request=withdrawal_request,
            )

        self.refresh_from_db()
        return tx

    def add_pending(
        self,
        amount: int,
        *,
        description: str,
        salon=None,
        order=None,
        order_detail=None,
        financial_snapshot=None,
    ):
        return self._record(
            tx_type=StylistWalletTransaction.TransactionType.SERVICE_PENDING,
            pending_delta=int(amount),
            description=description,
            salon=salon,
            order=order,
            order_detail=order_detail,
            financial_snapshot=financial_snapshot,
        )

    def release_pending(
        self,
        amount: int,
        *,
        description: str,
        salon=None,
        order=None,
        order_detail=None,
        financial_snapshot=None,
    ):
        return self._record(
            tx_type=StylistWalletTransaction.TransactionType.PENDING_RELEASE,
            pending_delta=-int(amount),
            available_delta=int(amount),
            description=description,
            salon=salon,
            order=order,
            order_detail=order_detail,
            financial_snapshot=financial_snapshot,
        )

    def reverse_pending(
        self,
        amount: int,
        *,
        description: str,
        salon=None,
        order=None,
        order_detail=None,
        financial_snapshot=None,
    ):
        return self._record(
            tx_type=StylistWalletTransaction.TransactionType.REVERSAL,
            pending_delta=-int(amount),
            description=description,
            salon=salon,
            order=order,
            order_detail=order_detail,
            financial_snapshot=financial_snapshot,
        )

    def reverse_available(
        self,
        amount: int,
        *,
        description: str,
        salon=None,
        order=None,
        order_detail=None,
        financial_snapshot=None,
    ):
        return self._record(
            tx_type=StylistWalletTransaction.TransactionType.REVERSAL,
            available_delta=-int(amount),
            description=description,
            salon=salon,
            order=order,
            order_detail=order_detail,
            financial_snapshot=financial_snapshot,
        )

    def request_withdraw(
        self,
        amount: int,
        *,
        salon,
        description: str = "درخواست دریافت درآمد متخصص",
        withdrawal_request=None,
    ):
        if not salon:
            raise ValidationError("برای درخواست برداشت، مجموعه باید مشخص باشد.")

        salon_available = self.available_balance_for_salon(salon)
        if salon_available < int(amount or 0):
            raise ValidationError("مانده قابل برداشت متخصص در این مجموعه کافی نیست.")

        return self._record(
            tx_type=StylistWalletTransaction.TransactionType.WITHDRAW_REQUEST,
            available_delta=-int(amount),
            description=description,
            salon=salon,
            withdrawal_request=withdrawal_request,
        )

    def create_withdrawal_request(
        self,
        *,
        salon,
        amount: int,
        iban: str,
        account_holder_name: str,
        bank_name: str = "",
        note: str = "",
    ):
        amount = int(amount or 0)

        if not salon:
            raise ValidationError("برای درخواست برداشت، مجموعه باید مشخص باشد.")

        if amount <= 0:
            raise ValidationError("مبلغ دریافت باید بیشتر از صفر باشد.")

        with transaction.atomic():
            wallet = StylistWallet.objects.select_for_update().get(pk=self.pk)

            salon_available = wallet.available_balance_for_salon(salon)
            if salon_available < amount:
                raise ValidationError(
                    "مانده قابل برداشت متخصص در این مجموعه کافی نیست."
                )

            request = StylistWalletWithdrawalRequest.objects.create(
                wallet=wallet,
                salon=salon,
                amount=amount,
                iban=iban,
                account_holder_name=account_holder_name,
                bank_name=bank_name,
                note=note,
            )

            wallet.request_withdraw(
                amount,
                salon=salon,
                description=f"ثبت درخواست دریافت درآمد متخصص از مجموعه {salon} به مبلغ {amount}",
                withdrawal_request=request,
            )

        self.refresh_from_db()

        return request

    def _resolve_salon(
        self,
        *,
        salon=None,
        order=None,
        order_detail=None,
        financial_snapshot=None,
        withdrawal_request=None,
    ):
        if salon:
            return salon

        if financial_snapshot and getattr(financial_snapshot, "salon_id", None):
            return financial_snapshot.salon

        if order_detail and getattr(order_detail, "salon_id", None):
            return order_detail.salon

        if order and getattr(order, "salon_id", None):
            return order.salon

        if withdrawal_request and getattr(withdrawal_request, "salon_id", None):
            return withdrawal_request.salon

        return None

    def pending_balance_for_salon(self, salon):
        if not salon:
            return 0

        return int(
            self.transactions.filter(salon=salon).aggregate(
                total=Coalesce(Sum("pending_delta"), Value(0))
            )["total"]
            or 0
        )

    def available_balance_for_salon(self, salon):
        if not salon:
            return 0

        return int(
            self.transactions.filter(salon=salon).aggregate(
                total=Coalesce(Sum("available_delta"), Value(0))
            )["total"]
            or 0
        )

    def total_balance_for_salon(self, salon):
        return self.pending_balance_for_salon(salon) + self.available_balance_for_salon(
            salon
        )

    def __str__(self):
        return f"حساب مالی آرایشگر {self.stylist}"

    class Meta:
        verbose_name = "حساب مالی آرایشگر"
        verbose_name_plural = "حساب‌های مالی آرایشگران"
        constraints = [
            CheckConstraint(
                check=Q(available_balance__gte=0), name="sty_wallet_available_gte_zero"
            ),
            CheckConstraint(
                check=Q(pending_balance__gte=0), name="sty_wallet_pending_gte_zero"
            ),
        ]


class StylistWalletTransaction(models.Model):
    class TransactionType(models.TextChoices):
        SERVICE_PENDING = "service_pending", "ثبت درآمد خدمت"
        PENDING_RELEASE = "pending_release", "انتقال به مانده قابل دریافت"
        REVERSAL = "reversal", "برگشت/اصلاح"
        WITHDRAW_REQUEST = "withdraw_request", "درخواست دریافت"
        WITHDRAW_RESTORE = "withdraw_restore", "بازگشت دریافت ردشده"
        MANUAL_ADJUSTMENT = "manual_adjustment", "اصلاح دستی"

    wallet = models.ForeignKey(
        StylistWallet,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name="حساب مالی آرایشگر",
    )
    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stylist_wallet_transactions",
        verbose_name="مجموعه مرتبط",
    )
    transaction_type = models.CharField(
        max_length=32,
        choices=TransactionType.choices,
        verbose_name="نوع تراکنش",
    )
    pending_delta = models.IntegerField(
        default=0, verbose_name="تغییر موجودی در انتظار"
    )
    available_delta = models.IntegerField(
        default=0, verbose_name="تغییر موجودی قابل برداشت"
    )
    pending_balance_after = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        default=0,
        verbose_name="موجودی در انتظار بعد از تراکنش",
    )
    available_balance_after = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        default=0,
        verbose_name="مانده قابل دریافت بعد از تراکنش",
    )
    description = models.TextField(blank=True, default="", verbose_name="توضیحات")
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stylist_wallet_transactions",
        verbose_name="سفارش مرتبط",
    )
    order_detail = models.ForeignKey(
        "orders.OrderDetail",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stylist_wallet_transactions",
        verbose_name="آیتم رزرو مرتبط",
    )
    financial_snapshot = models.ForeignKey(
        OrderDetailFinancialSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stylist_wallet_transactions",
        verbose_name="سند مالی مرتبط",
    )
    withdrawal_request = models.ForeignKey(
        "payments.StylistWalletWithdrawalRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name="درخواست دریافت مرتبط",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")

    def __str__(self):
        return f"{self.wallet.stylist} - {self.get_transaction_type_display()}"

    class Meta:
        verbose_name = "تراکنش حساب مالی آرایشگر"
        verbose_name_plural = "تراکنش‌های حساب مالی آرایشگر"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["salon", "created_at"], name="sty_wal_tx_salon_created_idx"
            ),
            models.Index(
                fields=["wallet", "salon"], name="sty_wal_tx_wallet_salon_idx"
            ),
        ]


class StylistWalletWithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار بررسی"
        APPROVED = "approved", "تایید شده"
        REJECTED = "rejected", "رد شده"
        CANCELLED = "cancelled", "لغو شده"

    wallet = models.ForeignKey(
        StylistWallet,
        on_delete=models.CASCADE,
        related_name="withdrawal_requests",
        verbose_name="حساب مالی آرایشگر",
    )
    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stylist_wallet_withdrawal_requests",
        verbose_name="مجموعه مرتبط",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        verbose_name="مبلغ دریافت",
    )
    iban = models.CharField(max_length=26, verbose_name="شماره شبا")
    account_holder_name = models.CharField(max_length=120, verbose_name="نام صاحب حساب")
    bank_name = models.CharField(
        max_length=80,
        blank=True,
        default="",
        verbose_name="نام بانک",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="وضعیت",
    )
    note = models.TextField(blank=True, default="", verbose_name="یادداشت")
    payment_receipt = models.FileField(
        upload_to="stylist_wallet_withdrawal_receipts/",
        null=True,
        blank=True,
        verbose_name="رسید واریز",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان بررسی")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    def approve(self, *, note: str = "", payment_receipt=None):
        if self.status != self.Status.PENDING:
            raise ValidationError("فقط درخواست‌های در انتظار را می‌توان تایید کرد.")

        if payment_receipt is not None:
            self.payment_receipt = payment_receipt

        self.status = self.Status.APPROVED
        self.reviewed_at = timezone.now()

        if note:
            self.note = note

        update_fields = ["status", "reviewed_at", "note", "updated_at"]
        if payment_receipt is not None:
            update_fields.append("payment_receipt")
        self.save(update_fields=update_fields)
        return self

    def reject(self, *, note: str = ""):
        if self.status != self.Status.PENDING:
            raise ValidationError("فقط درخواست‌های در انتظار را می‌توان رد کرد.")

        with transaction.atomic():
            request = StylistWalletWithdrawalRequest.objects.select_for_update().get(
                pk=self.pk
            )

            if request.status != self.Status.PENDING:
                raise ValidationError("این درخواست قبلاً بررسی شده است.")

            request.status = self.Status.REJECTED
            request.reviewed_at = timezone.now()
            request.note = (
                note
                or "این درخواست توسط تیم مالی رد شد و مبلغ به مانده قابل دریافت آرایشگر برگشت داده شد."
            )
            request.save(update_fields=["status", "reviewed_at", "note", "updated_at"])

        self.refresh_from_db()
        return self

    def cancel(self, *, note: str = ""):
        if self.status != self.Status.PENDING:
            raise ValidationError("فقط درخواست‌های در انتظار را می‌توان لغو کرد.")

        with transaction.atomic():
            request = StylistWalletWithdrawalRequest.objects.select_for_update().get(
                pk=self.pk
            )

            if request.status != self.Status.PENDING:
                raise ValidationError("این درخواست قبلاً بررسی شده است.")

            request.status = self.Status.CANCELLED
            request.reviewed_at = timezone.now()
            request.note = (
                note
                or "درخواست دریافت درآمد توسط آرایشگر لغو شد و مبلغ به مانده قابل دریافت برگشت داده شد."
            )
            request.save(update_fields=["status", "reviewed_at", "note", "updated_at"])

        self.refresh_from_db()
        return self

    def _restore_balance_if_needed(self):
        amount = int(self.amount or 0)
        if amount <= 0:
            return None

        wallet = StylistWallet.objects.select_for_update().get(pk=self.wallet_id)

        return wallet._record(
            tx_type=StylistWalletTransaction.TransactionType.WITHDRAW_RESTORE,
            available_delta=amount,
            description="بازگشت دریافت ردشده/لغوشده متخصص",
            salon=self.salon,
            withdrawal_request=self,
        )
    
    def save(self, *args, **kwargs):
        is_create = self._state.adding
        previous_status = None

        if not is_create and self.pk:
            previous_status = (
                StylistWalletWithdrawalRequest.objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )

        should_restore = previous_status == self.Status.PENDING and self.status in {
            self.Status.REJECTED,
            self.Status.CANCELLED,
        }

        if (
            self.status
            in {self.Status.APPROVED, self.Status.REJECTED, self.Status.CANCELLED}
            and not self.reviewed_at
        ):
            self.reviewed_at = timezone.now()
            update_fields = kwargs.get("update_fields")

            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("reviewed_at")
                kwargs["update_fields"] = list(update_fields)

        with transaction.atomic():
            if should_restore:
                self._restore_balance_if_needed()

                if not self.note:
                    self.note = "درخواست دریافت درآمد رد/لغو شد و مبلغ به مانده قابل دریافت آرایشگر برگشت داده شد."
                    update_fields = kwargs.get("update_fields")

                    if update_fields is not None:
                        update_fields = set(update_fields)
                        update_fields.add("note")
                        kwargs["update_fields"] = list(update_fields)

            return super().save(*args, **kwargs)

    def __str__(self):
        return f"درخواست دریافت {self.amount} برای آرایشگر {self.wallet.stylist}"

    class Meta:
        verbose_name = "درخواست دریافت درآمد آرایشگر"
        verbose_name_plural = "درخواست‌های دریافت درآمد آرایشگران"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["salon", "status"], name="sty_wd_salon_status_idx"),
            models.Index(fields=["wallet", "salon"], name="sty_wd_wallet_salon_idx"),
        ]


# -----------------------------------------------------------------------------------------------------------------
# لایه مالی رسمی Loomera: حساب داخلی، Ledger و سیاست‌های مالی
class FinancialAccount(models.Model):
    class AccountType(models.TextChoices):
        SALON = "salon", "حساب مالی سالن"
        STAFF_RECEIVABLE = "staff_receivable", "مطالبات آرایشگر از سالن"
        PLATFORM_COMMISSION = "platform_commission", "کمیسیون Loomera"
        SALON_DEBT = "salon_debt", "بدهی سالن به Loomera"
        CLIENT_COMPENSATION = "client_compensation", "اعتبار جبرانی مشتری"
        PROVIDER_CLEARING = "provider_clearing", "حساب واسط provider پرداخت"
        REFUND = "refund", "برگشت وجه"
        ADJUSTMENT = "adjustment", "اصلاحات مالی"

    owner_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="financial_accounts",
        verbose_name="نوع مالک",
    )
    owner_object_id = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="شناسه مالک"
    )
    owner = GenericForeignKey("owner_content_type", "owner_object_id")
    account_type = models.CharField(
        max_length=64, choices=AccountType.choices, verbose_name="نوع حساب"
    )
    currency = models.CharField(max_length=8, default="IRR", verbose_name="واحد پول")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    def __str__(self):
        return f"{self.get_account_type_display()} - {self.owner or 'Loomera'}"

    class Meta:
        verbose_name = "حساب مالی داخلی"
        verbose_name_plural = "حساب‌های مالی داخلی"
        indexes = [
            models.Index(
                fields=["account_type", "is_active"], name="fin_acc_type_active_idx"
            ),
            models.Index(
                fields=["owner_content_type", "owner_object_id"],
                name="fin_acc_owner_idx",
            ),
        ]


class LedgerEntry(models.Model):
    class Direction(models.TextChoices):
        DEBIT = "debit", "بدهکار"
        CREDIT = "credit", "بستانکار"

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        POSTED = "posted", "ثبت‌شده"
        VOIDED = "voided", "باطل‌شده با سند اصلاحی"

    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        verbose_name="حساب",
    )
    order = models.ForeignKey(
        "orders.Order",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        verbose_name="سفارش",
    )
    order_detail = models.ForeignKey(
        "orders.OrderDetail",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        verbose_name="آیتم رزرو",
    )
    group_id = models.UUIDField(db_index=True, verbose_name="شناسه گروه سند")
    entry_type = models.CharField(max_length=64, verbose_name="نوع ثبت")
    direction = models.CharField(
        max_length=16, choices=Direction.choices, verbose_name="جهت"
    )
    amount = models.PositiveBigIntegerField(verbose_name="مبلغ")
    currency = models.CharField(max_length=8, default="IRR", verbose_name="واحد پول")
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.POSTED,
        verbose_name="وضعیت",
    )
    description = models.TextField(blank=True, default="", verbose_name="توضیحات")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="فراداده")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_ledger_entries",
        verbose_name="ثبت‌کننده",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")

    def __str__(self):
        return f"{self.get_direction_display()} {self.amount} / {self.account}"

    class Meta:
        verbose_name = "ثبت دفتر مالی"
        verbose_name_plural = "ثبت‌های دفتر مالی"
        ordering = ["-created_at", "-id"]
        constraints = [
            CheckConstraint(check=Q(amount__gte=0), name="ledger_entry_amount_gte_zero")
        ]
        indexes = [
            models.Index(fields=["group_id", "status"], name="ledger_group_status_idx"),
            models.Index(fields=["order", "created_at"], name="ledger_order_time_idx"),
            models.Index(
                fields=["order_detail", "created_at"], name="ledger_detail_time_idx"
            ),
            models.Index(
                fields=["entry_type", "created_at"], name="ledger_type_time_idx"
            ),
        ]


class CommissionPolicy(models.Model):
    class CommissionType(models.TextChoices):
        PERCENTAGE = "percentage", "درصدی"
        FIXED_AMOUNT = "fixed_amount", "مبلغ ثابت"

    salon = models.ForeignKey(
        "salons.Salon",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="commission_policies",
        verbose_name="سالن",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    applies_to_new_client_only = models.BooleanField(
        default=True, verbose_name="فقط مشتری جدید"
    )
    commission_type = models.CharField(
        max_length=32,
        choices=CommissionType.choices,
        default=CommissionType.PERCENTAGE,
        verbose_name="نوع کمیسیون",
    )
    commission_value = models.PositiveIntegerField(
        default=0, verbose_name="مقدار کمیسیون"
    )
    include_extra_charges = models.BooleanField(
        default=False, verbose_name="شامل هزینه‌های اضافه"
    )
    include_material_charges = models.BooleanField(
        default=False, verbose_name="شامل هزینه مواد دریافتی از مشتری"
    )
    effective_from = models.DateTimeField(
        null=True, blank=True, verbose_name="شروع اعتبار"
    )
    effective_to = models.DateTimeField(
        null=True, blank=True, verbose_name="پایان اعتبار"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    @classmethod
    def get_active_for(cls, *, salon=None, at=None):
        at = at or timezone.now()
        return (
            cls.objects.filter(
                models.Q(salon=salon) | models.Q(salon__isnull=True), is_active=True
            )
            .filter(
                models.Q(effective_from__isnull=True)
                | models.Q(effective_from__lte=at),
                models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=at),
            )
            .order_by(models.F("salon").desc(nulls_last=True), "-effective_from", "-id")
            .first()
        )

    def __str__(self):
        return f"سیاست کمیسیون {self.salon or 'عمومی'}"

    class Meta:
        verbose_name = "سیاست کمیسیون پلتفرم"
        verbose_name_plural = "سیاست‌های کمیسیون پلتفرم"
        indexes = [
            models.Index(
                fields=["salon", "is_active"], name="comm_policy_salon_active_idx"
            )
        ]


class BookingPaymentPolicy(models.Model):
    class PaymentMode(models.TextChoices):
        PAY_AT_VENUE = "pay_at_venue", "پرداخت در محل"
        DEPOSIT_REQUIRED = "deposit_required", "بیعانه"
        FULL_ONLINE_PAYMENT = "full_online_payment", "پرداخت کامل آنلاین"
        BNPL_AVAILABLE = "bnpl_available", "پرداخت قسطی"

    class DepositType(models.TextChoices):
        FIXED_AMOUNT = "fixed_amount", "مبلغ ثابت"
        PERCENTAGE = "percentage", "درصدی"

    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.CASCADE,
        related_name="booking_payment_policies",
        verbose_name="سالن",
    )
    service = models.ForeignKey(
        "services.Services",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="booking_payment_policies",
        verbose_name="خدمت",
    )
    is_enabled = models.BooleanField(default=True, verbose_name="فعال")
    payment_mode = models.CharField(
        max_length=64,
        choices=PaymentMode.choices,
        default=PaymentMode.PAY_AT_VENUE,
        verbose_name="حالت پرداخت",
    )
    deposit_type = models.CharField(
        max_length=64,
        choices=DepositType.choices,
        blank=True,
        default="",
        verbose_name="نوع بیعانه",
    )
    deposit_value = models.PositiveIntegerField(default=0, verbose_name="مقدار بیعانه")
    min_deposit_amount = models.PositiveBigIntegerField(
        default=0, verbose_name="حداقل بیعانه"
    )
    max_deposit_amount = models.PositiveBigIntegerField(
        default=0, verbose_name="حداکثر بیعانه"
    )
    remaining_payment_method = models.CharField(
        max_length=64, default="pay_at_venue", verbose_name="روش پرداخت باقی‌مانده"
    )
    customer_facing_text = models.TextField(
        blank=True, default="", verbose_name="متن قابل نمایش به مشتری"
    )
    machine_rules = models.JSONField(
        default=dict, blank=True, verbose_name="قوانین ماشینی"
    )
    effective_from = models.DateTimeField(
        null=True, blank=True, verbose_name="شروع اعتبار"
    )
    effective_to = models.DateTimeField(
        null=True, blank=True, verbose_name="پایان اعتبار"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    def clean(self):
        super().clean()
        if (
            self.payment_mode == self.PaymentMode.DEPOSIT_REQUIRED
            and not self.deposit_type
        ):
            raise ValidationError("برای بیعانه، نوع بیعانه باید مشخص شود.")
        if (
            self.effective_from
            and self.effective_to
            and self.effective_to < self.effective_from
        ):
            raise ValidationError("پایان اعتبار نمی‌تواند قبل از شروع اعتبار باشد.")

    def __str__(self):
        return f"قانون پرداخت {self.salon}"

    class Meta:
        verbose_name = "قانون پرداخت رزرو"
        verbose_name_plural = "قوانین پرداخت رزرو"
        indexes = [
            models.Index(
                fields=["salon", "service", "is_enabled"],
                name="booking_pay_policy_lookup_idx",
            )
        ]


class CancellationPolicy(models.Model):
    class PenaltyType(models.TextChoices):
        NONE = "none", "بدون جریمه"
        FIXED_AMOUNT = "fixed_amount", "مبلغ ثابت"
        PERCENTAGE_OF_SERVICE_PRICE = "percentage_of_service_price", "درصد مبلغ خدمت"
        DEPOSIT_AMOUNT = "deposit_amount", "معادل بیعانه"

    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.CASCADE,
        related_name="cancellation_policies",
        verbose_name="سالن",
    )
    service = models.ForeignKey(
        "services.Services",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="cancellation_policies",
        verbose_name="خدمت",
    )
    is_enabled = models.BooleanField(default=True, verbose_name="فعال")
    free_cancellation_until_hours = models.PositiveIntegerField(
        default=24, verbose_name="مهلت لغو رایگان"
    )
    client_late_cancel_penalty_type = models.CharField(
        max_length=64,
        choices=PenaltyType.choices,
        default=PenaltyType.NONE,
        verbose_name="نوع جریمه مشتری",
    )
    client_late_cancel_penalty_value = models.PositiveIntegerField(
        default=0, verbose_name="مقدار جریمه مشتری"
    )
    no_show_penalty_type = models.CharField(
        max_length=64,
        choices=PenaltyType.choices,
        default=PenaltyType.NONE,
        verbose_name="نوع جریمه عدم حضور",
    )
    no_show_penalty_value = models.PositiveIntegerField(
        default=0, verbose_name="مقدار جریمه عدم حضور"
    )
    mirror_client_penalty_for_salon = models.BooleanField(
        default=True, verbose_name="اعمال متقارن برای سالن"
    )
    salon_late_cancel_penalty_cap_type = models.CharField(
        max_length=64,
        choices=PenaltyType.choices,
        default=PenaltyType.PERCENTAGE_OF_SERVICE_PRICE,
        verbose_name="نوع سقف جریمه سالن",
    )
    salon_late_cancel_penalty_cap_value = models.PositiveIntegerField(
        default=30, verbose_name="مقدار سقف جریمه سالن"
    )
    emergency_exception_allowed = models.BooleanField(
        default=True, verbose_name="امکان استثنای اضطراری"
    )
    emergency_exception_requires_review = models.BooleanField(
        default=True, verbose_name="نیاز به بررسی استثنا"
    )
    customer_facing_text = models.TextField(
        blank=True, default="", verbose_name="متن قابل نمایش به مشتری"
    )
    machine_rules = models.JSONField(
        default=dict, blank=True, verbose_name="قوانین ماشینی"
    )
    effective_from = models.DateTimeField(
        null=True, blank=True, verbose_name="شروع اعتبار"
    )
    effective_to = models.DateTimeField(
        null=True, blank=True, verbose_name="پایان اعتبار"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    def __str__(self):
        return f"قانون لغو {self.salon}"

    class Meta:
        verbose_name = "قانون لغو"
        verbose_name_plural = "قوانین لغو"
        indexes = [
            models.Index(
                fields=["salon", "service", "is_enabled"],
                name="cancel_policy_lookup_idx",
            )
        ]


class PaymentProvider(models.Model):
    class ProviderType(models.TextChoices):
        PSP = "psp", "پرداخت آنلاین"
        BNPL = "bnpl", "پرداخت قسطی"
        MANUAL = "manual", "دستی"

    name = models.CharField(max_length=128, verbose_name="نام provider")
    code = models.CharField(max_length=64, unique=True, verbose_name="کد provider")
    provider_type = models.CharField(
        max_length=64, choices=ProviderType.choices, verbose_name="نوع provider"
    )
    is_active = models.BooleanField(default=False, verbose_name="فعال")
    supports_deposit = models.BooleanField(
        default=False, verbose_name="پشتیبانی بیعانه"
    )
    supports_full_payment = models.BooleanField(
        default=False, verbose_name="پشتیبانی پرداخت کامل"
    )
    supports_bnpl = models.BooleanField(default=False, verbose_name="پشتیبانی BNPL")
    supports_refund = models.BooleanField(
        default=False, verbose_name="پشتیبانی برگشت وجه"
    )
    supports_partial_refund = models.BooleanField(
        default=False, verbose_name="پشتیبانی برگشت جزئی"
    )
    config = models.JSONField(default=dict, blank=True, verbose_name="تنظیمات")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "ارائه‌دهنده پرداخت"
        verbose_name_plural = "ارائه‌دهندگان پرداخت"


class SalonPaymentProviderConfig(models.Model):
    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.CASCADE,
        related_name="payment_provider_configs",
        verbose_name="سالن",
    )
    provider = models.ForeignKey(
        PaymentProvider,
        on_delete=models.CASCADE,
        related_name="salon_configs",
        verbose_name="provider",
    )
    is_enabled = models.BooleanField(default=False, verbose_name="فعال")
    allowed_services = models.ManyToManyField(
        "services.Services",
        blank=True,
        related_name="payment_provider_configs",
        verbose_name="خدمات مجاز",
    )
    min_amount = models.PositiveBigIntegerField(default=0, verbose_name="حداقل مبلغ")
    max_amount = models.PositiveBigIntegerField(default=0, verbose_name="حداکثر مبلغ")
    provider_commission_type = models.CharField(
        max_length=64, blank=True, default="", verbose_name="نوع کارمزد provider"
    )
    provider_commission_value = models.PositiveIntegerField(
        default=0, verbose_name="مقدار کارمزد provider"
    )
    settlement_type = models.CharField(
        max_length=64, blank=True, default="", verbose_name="نوع تسویه"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    def __str__(self):
        return f"{self.salon} / {self.provider}"

    class Meta:
        verbose_name = "تنظیم provider پرداخت سالن"
        verbose_name_plural = "تنظیمات provider پرداخت سالن‌ها"
        constraints = [
            models.UniqueConstraint(
                fields=["salon", "provider"], name="uniq_provider_cfg_salon"
            )
        ]


class PaymentTransaction(models.Model):
    class Method(models.TextChoices):
        PAY_AT_VENUE = "pay_at_venue", "پرداخت در محل"
        ONLINE_CARD = "online_card", "پرداخت آنلاین"
        DEPOSIT_ONLINE = "deposit_online", "بیعانه آنلاین"
        BNPL_SNAPPPAY = "bnpl_snapppay", "اسنپ‌پی"
        BNPL_DIGIPAY = "bnpl_digipay", "دیجی‌پی"
        BNPL_TARA = "bnpl_tara", "تارا"

    class Status(models.TextChoices):
        INITIATED = "initiated", "شروع شده"
        PENDING = "pending", "در انتظار"
        PAID = "paid", "پرداخت شده"
        FAILED = "failed", "ناموفق"
        CANCELLED = "cancelled", "لغو شده"
        REFUNDED = "refunded", "برگشت داده شده"
        PARTIALLY_REFUNDED = "partially_refunded", "برگشت جزئی"

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="payment_transactions_v2",
        verbose_name="سفارش",
    )
    order_detail = models.ForeignKey(
        "orders.OrderDetail",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payment_transactions_v2",
        verbose_name="آیتم رزرو",
    )
    provider = models.ForeignKey(
        PaymentProvider,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name="provider",
    )
    legacy_payment = models.ForeignKey(
        Payment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_transactions_v2",
        verbose_name="پرداخت قدیمی مرتبط",
    )
    method = models.CharField(
        max_length=64, choices=Method.choices, verbose_name="روش پرداخت"
    )
    amount = models.PositiveBigIntegerField(verbose_name="مبلغ")
    status = models.CharField(
        max_length=64,
        choices=Status.choices,
        default=Status.INITIATED,
        verbose_name="وضعیت",
    )
    provider_reference = models.CharField(
        max_length=255, blank=True, default="", verbose_name="شناسه provider"
    )
    provider_payload = models.JSONField(
        default=dict, blank=True, verbose_name="payload provider"
    )
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان پرداخت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    def __str__(self):
        return f"{self.order} / {self.method} / {self.amount}"

    class Meta:
        verbose_name = "تراکنش پرداخت"
        verbose_name_plural = "تراکنش‌های پرداخت"
        indexes = [
            models.Index(fields=["status", "created_at"], name="pay_tx_status_time_idx")
        ]


class ExtraCharge(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PENDING_CLIENT_CONFIRMATION = (
            "pending_client_confirmation",
            "در انتظار تأیید مشتری",
        )
        APPROVED = "approved", "تأیید شده"
        REJECTED = "rejected", "رد شده"
        MANAGER_APPROVED = "manager_approved", "تأیید مدیریتی"

    order_detail = models.ForeignKey(
        "orders.OrderDetail",
        on_delete=models.CASCADE,
        related_name="extra_charges",
        verbose_name="آیتم رزرو",
    )
    title = models.CharField(max_length=255, verbose_name="عنوان")
    amount = models.PositiveBigIntegerField(verbose_name="مبلغ")
    reason = models.TextField(blank=True, default="", verbose_name="دلیل")
    status = models.CharField(
        max_length=64,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="وضعیت",
    )
    client_confirmed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="زمان تأیید مشتری"
    )
    manager_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_extra_charges",
        verbose_name="تأییدکننده مدیریتی",
    )
    manager_approved_at = models.DateTimeField(
        null=True, blank=True, verbose_name="زمان تأیید مدیریتی"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_extra_charges",
        verbose_name="ایجادکننده",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "هزینه اضافه"
        verbose_name_plural = "هزینه‌های اضافه"
        indexes = [
            models.Index(
                fields=["order_detail", "status"], name="extra_charge_detail_status_idx"
            )
        ]


class StaffEarning(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        PAYABLE = "payable", "قابل پرداخت"
        REQUESTED = "requested", "درخواست پرداخت شده"
        PAID_BY_SALON = "paid_by_salon", "پرداخت‌شده توسط سالن"
        DISPUTED = "disputed", "دارای اختلاف"
        ADJUSTED = "adjusted", "اصلاح‌شده"

    order_detail = models.OneToOneField(
        "orders.OrderDetail",
        on_delete=models.PROTECT,
        related_name="staff_earning",
        verbose_name="آیتم رزرو",
    )
    financial_snapshot = models.OneToOneField(
        OrderDetailFinancialSnapshot,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="staff_earning",
        verbose_name="سند مالی",
    )
    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.PROTECT,
        related_name="staff_earnings",
        verbose_name="سالن",
    )
    stylist = models.ForeignKey(
        "accounts.Stylist",
        on_delete=models.PROTECT,
        related_name="staff_earnings",
        verbose_name="آرایشگر",
    )
    gross_share = models.PositiveBigIntegerField(default=0, verbose_name="سهم ناخالص")
    material_deduction = models.PositiveBigIntegerField(
        default=0, verbose_name="کسر مواد"
    )
    adjustments = models.BigIntegerField(default=0, verbose_name="اصلاحات")
    net_profit = models.BigIntegerField(default=0, verbose_name="سود خالص")
    status = models.CharField(
        max_length=64,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="وضعیت",
    )
    calculated_at = models.DateTimeField(
        null=True, blank=True, verbose_name="زمان محاسبه"
    )
    requested_at = models.DateTimeField(
        null=True, blank=True, verbose_name="زمان درخواست"
    )
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان پرداخت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    def __str__(self):
        return f"مطالبه {self.stylist} / {self.net_profit}"

    class Meta:
        verbose_name = "مطالبه آرایشگر"
        verbose_name_plural = "مطالبات آرایشگران"
        indexes = [
            models.Index(
                fields=["salon", "stylist", "status"], name="staff_earning_lookup_idx"
            )
        ]


class StaffPayoutRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار بررسی"
        APPROVED = "approved", "تأیید شده"
        REJECTED = "rejected", "رد شده"
        PAID = "paid", "پرداخت شده"
        CANCELLED = "cancelled", "لغو شده"

    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.PROTECT,
        related_name="staff_payout_requests",
        verbose_name="سالن",
    )
    stylist = models.ForeignKey(
        "accounts.Stylist",
        on_delete=models.PROTECT,
        related_name="staff_payout_requests",
        verbose_name="آرایشگر",
    )
    earnings = models.ManyToManyField(
        StaffEarning, blank=True, related_name="payout_requests", verbose_name="مطالبات"
    )
    requested_amount = models.PositiveBigIntegerField(verbose_name="مبلغ درخواستی")
    approved_amount = models.PositiveBigIntegerField(
        default=0, verbose_name="مبلغ تأیید شده"
    )
    status = models.CharField(
        max_length=64,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="وضعیت",
    )
    staff_note = models.TextField(
        blank=True, default="", verbose_name="یادداشت آرایشگر"
    )
    manager_note = models.TextField(blank=True, default="", verbose_name="یادداشت مدیر")
    payment_receipt = models.FileField(
        upload_to="staff_payout_receipts/",
        null=True,
        blank=True,
        verbose_name="رسید پرداخت",
    )
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان درخواست")
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان تصمیم")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان پرداخت")

    def __str__(self):
        return f"درخواست پرداخت {self.stylist} / {self.requested_amount}"

    class Meta:
        verbose_name = "درخواست پرداخت سهم آرایشگر"
        verbose_name_plural = "درخواست‌های پرداخت سهم آرایشگران"
        indexes = [
            models.Index(
                fields=["salon", "stylist", "status"], name="staff_payout_lookup_idx"
            )
        ]


class FinancialAdjustment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار بررسی"
        APPROVED = "approved", "تأیید شده"
        REJECTED = "rejected", "رد شده"
        APPLIED = "applied", "اعمال شده"

    order = models.ForeignKey(
        "orders.Order",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="financial_adjustments",
        verbose_name="سفارش",
    )
    order_detail = models.ForeignKey(
        "orders.OrderDetail",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="financial_adjustments",
        verbose_name="آیتم رزرو",
    )
    financial_snapshot = models.ForeignKey(
        OrderDetailFinancialSnapshot,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="financial_adjustments",
        verbose_name="سند مالی",
    )
    reason = models.TextField(verbose_name="دلیل اصلاح")
    amount = models.BigIntegerField(verbose_name="مبلغ اصلاح")
    target_field = models.CharField(
        max_length=128, blank=True, default="", verbose_name="فیلد هدف"
    )
    status = models.CharField(
        max_length=64,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="وضعیت",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_financial_adjustments",
        verbose_name="درخواست‌کننده",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_financial_adjustments",
        verbose_name="تأییدکننده",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان تأیید")
    applied_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان اعمال")

    def __str__(self):
        return f"اصلاح مالی {self.amount}"

    class Meta:
        verbose_name = "اصلاح مالی"
        verbose_name_plural = "اصلاحات مالی"
        indexes = [
            models.Index(
                fields=["status", "created_at"], name="fin_adj_status_time_idx"
            )
        ]


class RefundRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار بررسی"
        APPROVED = "approved", "تأیید شده"
        REJECTED = "rejected", "رد شده"
        PROCESSING = "processing", "در حال پردازش"
        REFUNDED = "refunded", "برگشت داده شده"
        FAILED = "failed", "ناموفق"

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="refund_requests",
        verbose_name="سفارش",
    )
    payment_transaction = models.ForeignKey(
        PaymentTransaction,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="refund_requests",
        verbose_name="تراکنش پرداخت",
    )
    amount = models.PositiveBigIntegerField(verbose_name="مبلغ")
    reason = models.TextField(blank=True, default="", verbose_name="دلیل")
    status = models.CharField(
        max_length=64,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="وضعیت",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_refunds",
        verbose_name="درخواست‌کننده",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_refunds",
        verbose_name="بررسی‌کننده",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    def __str__(self):
        return f"برگشت وجه {self.order} / {self.amount}"

    class Meta:
        verbose_name = "درخواست برگشت وجه"
        verbose_name_plural = "درخواست‌های برگشت وجه"


class CustomerCompensation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        CREDITED = "credited", "اعتبار ثبت شد"
        PAID = "paid", "پرداخت شد"
        CANCELLED = "cancelled", "لغو شد"

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="customer_compensations",
        verbose_name="سفارش",
    )
    order_detail = models.ForeignKey(
        "orders.OrderDetail",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="customer_compensations",
        verbose_name="آیتم رزرو",
    )
    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.PROTECT,
        related_name="customer_compensations",
        verbose_name="سالن",
    )
    customer = models.ForeignKey(
        "accounts.Customer",
        on_delete=models.PROTECT,
        related_name="compensations",
        verbose_name="مشتری",
    )
    amount = models.PositiveBigIntegerField(verbose_name="مبلغ جبران")
    reason = models.TextField(blank=True, default="", verbose_name="دلیل")
    status = models.CharField(
        max_length=64,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="وضعیت",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_customer_compensations",
        verbose_name="ایجادکننده",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")

    def __str__(self):
        return f"جبران مشتری {self.customer} / {self.amount}"

    class Meta:
        verbose_name = "اعتبار/جبران مشتری"
        verbose_name_plural = "اعتبارها و جبران‌های مشتری"
