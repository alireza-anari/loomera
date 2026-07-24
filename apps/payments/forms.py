from django import forms
from django.conf import settings


BASE_INPUT = "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-loomera-primary focus:outline-none"


class WalletChargeForm(forms.Form):
    amount = forms.DecimalField(
        label="مبلغ شارژ (تومان)",
        min_value=10000,
        max_digits=10,
        decimal_places=0,
        widget=forms.NumberInput(
            attrs={
                "class": BASE_INPUT,
                "placeholder": "مبلغ را وارد کنید",
            }
        ),
    )


class WalletWithdrawalRequestForm(forms.Form):
    amount = forms.IntegerField(
        label="مبلغ برداشت",
        min_value=1,
        widget=forms.NumberInput(
            attrs={
                "class": BASE_INPUT,
                "placeholder": "مثلاً 250000",
            }
        ),
    )
    iban = forms.CharField(
        label="شماره شبا",
        max_length=26,
        widget=forms.TextInput(
            attrs={
                "class": f"{BASE_INPUT} uppercase tracking-wide",
                "placeholder": "IRxxxxxxxxxxxxxxxxxxxxxxxx",
                "dir": "ltr",
            }
        ),
    )
    account_holder_name = forms.CharField(
        label="نام صاحب حساب",
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "class": BASE_INPUT,
                "placeholder": "نام و نام خانوادگی",
            }
        ),
    )
    bank_name = forms.CharField(
        label="نام بانک",
        max_length=80,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": BASE_INPUT,
                "placeholder": "اختیاری",
            }
        ),
    )

    def clean_amount(self):
        amount = int(self.cleaned_data.get("amount") or 0)
        min_amount = int(
            getattr(settings, "WALLET_WITHDRAW_MIN_AMOUNT", 50000) or 50000
        )
        max_amount = int(
            getattr(settings, "WALLET_WITHDRAW_MAX_AMOUNT", 50000000) or 50000000
        )
        if amount < min_amount:
            raise forms.ValidationError(f"حداقل مبلغ برداشت {min_amount:,} تومان است.")
        if amount > max_amount:
            raise forms.ValidationError(f"حداکثر مبلغ برداشت {max_amount:,} تومان است.")
        return amount

    def clean_iban(self):
        value = (self.cleaned_data.get("iban") or "").strip().upper().replace(" ", "")
        if not value.startswith("IR") or len(value) != 26:
            raise forms.ValidationError("شماره شبای واردشده معتبر نیست.")
        return value


class SalonWalletWithdrawalRequestForm(forms.Form):
    amount = forms.IntegerField(
        label="مبلغ برداشت از امور مالی مجموعه",
        min_value=1,
        widget=forms.NumberInput(
            attrs={
                "class": BASE_INPUT,
                "placeholder": "مثلاً 750000",
            }
        ),
    )
    iban = forms.CharField(
        label="شماره شبای مقصد",
        max_length=26,
        widget=forms.TextInput(
            attrs={
                "class": f"{BASE_INPUT} uppercase tracking-wide",
                "placeholder": "IRxxxxxxxxxxxxxxxxxxxxxxxx",
                "dir": "ltr",
            }
        ),
    )
    account_holder_name = forms.CharField(
        label="نام صاحب حساب",
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "class": BASE_INPUT,
                "placeholder": "مثلاً سارا احمدی",
            }
        ),
    )
    bank_name = forms.CharField(
        label="نام بانک",
        max_length=80,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": BASE_INPUT,
                "placeholder": "برای پیگیری دقیق‌تر، نام بانک را هم وارد کن",
            }
        ),
    )

    def clean_amount(self):
        amount = int(self.cleaned_data.get("amount") or 0)
        min_amount = int(
            getattr(settings, "SALON_WALLET_WITHDRAW_MIN_AMOUNT", 100000) or 100000
        )
        max_amount = int(
            getattr(settings, "SALON_WALLET_WITHDRAW_MAX_AMOUNT", 200000000)
            or 200000000
        )
        if amount < min_amount:
            raise forms.ValidationError(
                f"حداقل مبلغ برداشت برای مجموعه {min_amount:,} تومان است."
            )
        if amount > max_amount:
            raise forms.ValidationError(
                f"حداکثر مبلغ برداشت برای مجموعه {max_amount:,} تومان است."
            )
        return amount

    def clean_iban(self):
        value = (self.cleaned_data.get("iban") or "").strip().upper().replace(" ", "")
        if not value.startswith("IR") or len(value) != 26:
            raise forms.ValidationError("شماره شبای مقصد معتبر نیست.")
        return value
