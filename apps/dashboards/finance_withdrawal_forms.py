from django import forms
from django.core.exceptions import ValidationError

from apps.payments.models import StylistWalletWithdrawalRequest


BASE_INPUT = (
    "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm "
    "text-slate-800 outline-none transition focus:border-loomera-primary/30 "
    "focus:ring-2 focus:ring-loomera-primary/10"
)


class StylistWithdrawalRequestForm(forms.ModelForm):
    class Meta:
        model = StylistWalletWithdrawalRequest
        fields = [
            "amount",
            "iban",
            "account_holder_name",
            "bank_name",
            "note",
        ]
        widgets = {
            "amount": forms.NumberInput(
                attrs={
                    "class": BASE_INPUT,
                    "min": 1,
                    "placeholder": "مثلاً ۵۰۰۰۰۰",
                }
            ),
            "iban": forms.TextInput(
                attrs={
                    "class": BASE_INPUT,
                    "placeholder": "IRxxxxxxxxxxxxxxxxxxxxxxxx",
                    "dir": "ltr",
                }
            ),
            "account_holder_name": forms.TextInput(
                attrs={
                    "class": BASE_INPUT,
                    "placeholder": "نام صاحب حساب",
                }
            ),
            "bank_name": forms.TextInput(
                attrs={
                    "class": BASE_INPUT,
                    "placeholder": "نام بانک",
                }
            ),
            "note": forms.Textarea(
                attrs={
                    "class": BASE_INPUT,
                    "rows": 3,
                    "placeholder": "توضیح اختیاری",
                }
            ),
        }

    def __init__(self, *args, wallet=None, salon=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.wallet = wallet
        self.salon = salon

        self.fields["amount"].label = "مبلغ دریافت"
        self.fields["iban"].label = "شماره شبا برای واریز"
        self.fields["account_holder_name"].label = "نام صاحب حساب"
        self.fields["bank_name"].label = "نام بانک"
        self.fields["note"].label = "یادداشت اختیاری"

    def clean_amount(self):
        amount = int(self.cleaned_data.get("amount") or 0)

        if amount <= 0:
            raise ValidationError("مبلغ دریافت باید بیشتر از صفر باشد.")

        if not self.salon:
            raise ValidationError(
                "برای ثبت درخواست دریافت، مجموعه فعال باید مشخص باشد."
            )

        if self.wallet and amount > int(
            self.wallet.available_balance_for_salon(self.salon) or 0
        ):
            raise ValidationError(
                "مبلغ دریافت از مانده قابل دریافت شما در این مجموعه بیشتر است."
            )

        return amount

    def clean_iban(self):
        iban = (self.cleaned_data.get("iban") or "").strip().replace(" ", "")

        if not iban.startswith("IR"):
            raise ValidationError("شماره شبا باید با IR شروع شود.")

        if len(iban) != 26:
            raise ValidationError("شماره شبا باید ۲۶ کاراکتر باشد.")

        return iban

    def save(self, commit=True):
        if not self.wallet:
            raise ValidationError("حساب مالی متخصص مشخص نیست.")

        if not self.salon:
            raise ValidationError("مجموعه فعال مشخص نیست.")

        return self.wallet.create_withdrawal_request(
            salon=self.salon,
            amount=self.cleaned_data["amount"],
            iban=self.cleaned_data["iban"],
            account_holder_name=self.cleaned_data["account_holder_name"],
            bank_name=self.cleaned_data.get("bank_name") or "",
            note=self.cleaned_data.get("note") or "",
        )
