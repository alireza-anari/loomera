from django import forms
from django.conf import settings

from .models import PaymentType


class OrderForm(forms.Form):
    payment_type = forms.ChoiceField(
        label="",
        choices=[],
        widget=forms.RadioSelect(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_type"].choices = [
            (item.pk, item.payment_title) for item in PaymentType.objects.all()
        ]


class AppointmentCheckoutForm(forms.Form):
    PAYMENT_METHOD_ONLINE = "online"
    PAYMENT_METHOD_WALLET = "wallet"
    PAYMENT_METHOD_SALON = "pay_in_salon"

    coupon_code = forms.CharField(
        required=False,
        max_length=100,
        label="کد تخفیف",
        widget=forms.TextInput(
            attrs={
                "class": "w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm focus:border-purple-500 focus:outline-none",
                "placeholder": "اگر کد تخفیف دارید وارد کنید",
                "dir": "ltr",
            }
        ),
    )
    payment_method = forms.ChoiceField(
        label="روش پرداخت", choices=[], widget=forms.RadioSelect()
    )

    def __init__(self, *args, requires_online_payment=False, **kwargs):
        super().__init__(*args, **kwargs)
        online_payment_enabled = bool(
            getattr(settings, "ONLINE_PAYMENT_ENABLED", False)
        )
        self.requires_online_payment = bool(
            requires_online_payment and online_payment_enabled
        )
        self.online_payment_enabled = online_payment_enabled

        choices = []
        if online_payment_enabled:
            choices.extend(
                [
                    (self.PAYMENT_METHOD_ONLINE, "پرداخت آنلاین"),
                    (self.PAYMENT_METHOD_WALLET, "پرداخت با کیف پول"),
                ]
            )

        if not self.requires_online_payment:
            choices.append((self.PAYMENT_METHOD_SALON, "پرداخت در مجموعه"))

        self.fields["payment_method"].choices = choices
        self.fields["payment_method"].initial = (
            self.PAYMENT_METHOD_ONLINE
            if self.requires_online_payment
            else self.PAYMENT_METHOD_SALON
        )

    def clean_coupon_code(self):
        return (self.cleaned_data.get("coupon_code") or "").strip().upper()

    def clean_payment_method(self):
        method = self.cleaned_data.get("payment_method")
        if not self.online_payment_enabled and method != self.PAYMENT_METHOD_SALON:
            raise forms.ValidationError("در نسخه بتا فقط پرداخت در مجموعه فعال است.")
        if self.requires_online_payment and method not in {
            self.PAYMENT_METHOD_ONLINE,
            self.PAYMENT_METHOD_WALLET,
        }:
            raise forms.ValidationError(
                "برای اولین مراجعه به این مجموعه، فقط پرداخت دیجیتال (آنلاین یا کیف پول) مجاز است."
            )
        return method
