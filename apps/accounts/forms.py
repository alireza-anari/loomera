import os

from apps.main.ui_feedback import user_error_message

from PIL import Image, ImageSequence, UnidentifiedImageError
from django.conf import settings

from django import forms
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
import jdatetime

from .models import Customer, CustomerAddress, CustomUser, SalonManager, Stylist
from django.core.validators import validate_email

PERSIAN_DIGITS_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
ARABIC_DIGITS_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_digits(value):
    return (
        (value or "").translate(PERSIAN_DIGITS_MAP).translate(ARABIC_DIGITS_MAP).strip()
    )


CUSTOMER_PROFILE_IMAGE_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
CUSTOMER_PROFILE_IMAGE_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

CUSTOMER_PROFILE_IMAGE_BLOCKED_FILENAME_PARTS = {
    ".php",
    ".phtml",
    ".php3",
    ".php4",
    ".php5",
    ".asp",
    ".aspx",
    ".jsp",
    ".cgi",
    ".pl",
    ".py",
    ".rb",
    ".htm",
    ".html",
    ".js",
    ".svg",
    ".xml",
    ".exe",
    ".sh",
    ".bat",
    ".cmd",
    ".gif",
}

CUSTOMER_PROFILE_IMAGE_MAX_SIZE = 2 * 1024 * 1024


def _customer_profile_image_max_dimension():
    return max(
        int(getattr(settings, "CUSTOMER_PROFILE_IMAGE_MAX_DIMENSION", 5000) or 1),
        1,
    )


def _customer_profile_image_max_pixels():
    return max(
        int(getattr(settings, "CUSTOMER_PROFILE_IMAGE_MAX_PIXELS", 10_000_000) or 1),
        1,
    )


def _customer_profile_image_is_animated(image):
    if getattr(image, "is_animated", False):
        return True

    try:
        return sum(1 for _frame in ImageSequence.Iterator(image)) > 1
    except Exception:
        return False


def validate_customer_profile_image_upload(
    uploaded_file, *, declared_content_type=None
):
    if not uploaded_file:
        return uploaded_file

    if uploaded_file.size > CUSTOMER_PROFILE_IMAGE_MAX_SIZE:
        raise ValidationError("حجم تصویر نباید بیشتر از ۲ مگابایت باشد.")

    original_name = os.path.basename(uploaded_file.name or "").lower()
    _, ext = os.path.splitext(original_name)

    if ext not in CUSTOMER_PROFILE_IMAGE_ALLOWED_EXTENSIONS:
        raise ValidationError(
            "پسوند تصویر مجاز نیست. فقط جی‌پی‌جی، پی‌اِن‌جی یا وِب‌پی قابل قبول است."
        )

    name_without_last_ext = original_name[: -len(ext)] if ext else original_name
    if any(
        blocked in name_without_last_ext
        for blocked in CUSTOMER_PROFILE_IMAGE_BLOCKED_FILENAME_PARTS
    ):
        raise ValidationError("نام یا پسوند فایل مجاز نیست.")

    content_type = (
        declared_content_type
        if declared_content_type is not None
        else getattr(uploaded_file, "content_type", "")
    )
    content_type = str(content_type or "").split(";")[0].strip().lower()

    if content_type not in CUSTOMER_PROFILE_IMAGE_ALLOWED_CONTENT_TYPES:
        raise ValidationError(
            "فرمت فایل مجاز نیست. فقط جی‌پی‌جی، پی‌اِن‌جی یا وِب‌پی قابل قبول است."
        )

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)

        if image.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValidationError("فرمت واقعی تصویر مجاز نیست.")

        if _customer_profile_image_is_animated(image):
            raise ValidationError("تصویر متحرک برای پروفایل مجاز نیست.")

        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValidationError("ابعاد تصویر معتبر نیست.")

        max_dimension = _customer_profile_image_max_dimension()
        if width > max_dimension or height > max_dimension:
            raise ValidationError("ابعاد تصویر بیش از حد مجاز است.")

        if width * height > _customer_profile_image_max_pixels():
            raise ValidationError("تعداد پیکسل‌های تصویر بیش از حد مجاز است.")

        uploaded_file.seek(0)
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError("فایل ارسال‌شده تصویر معتبر نیست.")

    return uploaded_file


# ------------------------------------------------------------------------------------------------------------
# User Creation Form
class CustomUserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="رمز عبور", widget=forms.PasswordInput)
    password2 = forms.CharField(label="تکرار رمز عبور", widget=forms.PasswordInput)

    class Meta:
        model = CustomUser
        fields = ["mobile_number", "name", "family", "email"]

    def clean_password2(self):
        cd = self.cleaned_data
        if cd["password1"] and cd["password2"] and cd["password1"] != cd["password2"]:
            raise ValidationError("رمز عبور و تکرار آن مغایرت دارند ")
        return cd["password2"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


# -----------------------------------------------------------------------------------------------------------
# User Change Form
class CustomUserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(
        help_text="برای تغییر رمز عبور روی این <a href='../password' >لینک</a> کلیک کنید "
    )

    class Meta:
        model = CustomUser
        fields = [
            "mobile_number",
            "password",
            "name",
            "family",
            "email",
            "is_active",
            "is_admin",
        ]


# -------------------------------------------------------------------------------------------------------------
# Shared signup form
class BaseSignupForm(forms.ModelForm):
    signup_kind = None
    password1 = forms.CharField(
        label="رمز عبور",
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "حداقل ۸ کاراکتر"}
        ),
    )
    password2 = forms.CharField(
        label="تکرار رمز عبور",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "رمز عبور را دوباره وارد کنید",
            }
        ),
    )
    agree_to_terms = forms.BooleanField(
        label="با شرایط و قوانین موافقم",
        required=True,
        widget=forms.CheckboxInput(attrs={"class": "form-control"}),
    )

    class Meta:
        model = CustomUser
        fields = ["name", "family", "mobile_number"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "نام"}
            ),
            "family": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "نام خانوادگی"}
            ),
            "mobile_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "09xxxxxxxxx",
                    "inputmode": "numeric",
                }
            ),
        }

    def clean_mobile_number(self):
        mobile_number = "".join(
            ch for ch in self.cleaned_data.get("mobile_number", "") if ch.isdigit()
        )

        if len(mobile_number) != 11 or not mobile_number.startswith("09"):
            raise ValidationError("شماره موبایل باید ۱۱ رقم باشد و با 09 شروع شود")

        self._reuse_user = None
        queryset = CustomUser.objects.filter(mobile_number=mobile_number)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)

        existing_user = queryset.first()
        if existing_user:
            role_profile_map = {
                "customer": "customer_profile",
                "salon": "salon_manager_profile",
                "stylist": "stylist",
            }
            current_profile_name = role_profile_map.get(self.signup_kind)
            conflicting_profiles = [
                profile_name
                for kind, profile_name in role_profile_map.items()
                if kind != self.signup_kind
            ]

            has_conflicting_role = any(
                hasattr(existing_user, profile_name)
                for profile_name in conflicting_profiles
            )

            if (
                not existing_user.is_active
                and not existing_user.is_admin
                and not has_conflicting_role
            ):
                self._reuse_user = existing_user
                self.instance = existing_user
                return mobile_number

            if current_profile_name and hasattr(existing_user, current_profile_name):
                raise ValidationError("این شماره موبایل قبلاً با همین نقش ثبت شده است.")

            raise ValidationError("این شماره موبایل قبلاً ثبت شده است")

        return mobile_number

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            raise ValidationError("رمز عبور و تأیید آن مطابقت ندارند")

        if password1 and len(password1) < 8:
            raise ValidationError("رمز عبور باید حداقل ۸ کاراکتر باشد")

        if password1:
            try:
                validate_password(
                    password1,
                    self.instance if getattr(self.instance, "pk", None) else None,
                )
            except ValidationError as exc:
                raise ValidationError(
                    user_error_message(
                        exc, fallback="رمز عبور شرایط امنیتی لازم را ندارد."
                    )
                )

        return password2

    def save(self, commit=True):
        user = getattr(self, "_reuse_user", None) or super().save(commit=False)
        user.name = self.cleaned_data["name"]
        user.family = self.cleaned_data["family"]
        user.mobile_number = self.cleaned_data["mobile_number"]
        user.set_password(self.cleaned_data["password1"])
        user.is_active = False
        if commit:
            user.save()
        return user


# -------------------------------------------------------------------------------------------------------------
# Register Form (Salon / business signup)
class RegisterUserForm(BaseSignupForm):
    signup_kind = "salon"


# -------------------------------------------------------------------------------------------------------------
# Stylist / Specialist Signup Form
class StylistSignupForm(BaseSignupForm):
    signup_kind = "stylist"

    expert = forms.CharField(
        label="تخصص اصلی",
        max_length=100,
        required=True,
        error_messages={"required": "تخصص اصلی را وارد کنید."},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "مثلاً رنگ مو، ناخن، ماساژ، پوست و زیبایی",
            }
        ),
    )

    def clean_expert(self):
        value = (self.cleaned_data.get("expert") or "").strip()
        if len(value) < 2:
            raise ValidationError("تخصص اصلی باید حداقل ۲ کاراکتر باشد.")
        return value


# -------------------------------------------------------------------------------------------------------------
# Customer Signup Form
class CustomerSignupForm(BaseSignupForm):
    signup_kind = "customer"


# ---------------------------------------------------------------------------------------
#
class SpecialistSignupForm(BaseSignupForm):
    signup_kind = "stylist"

    expert = forms.CharField(
        label="تخصص اصلی",
        max_length=100,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "مثلاً ماساژ، ناخن، پوست، رنگ مو، میکاپ",
            }
        ),
    )

    resume_headline = forms.CharField(
        label="عنوان حرفه‌ای",
        max_length=180,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "مثلاً متخصص ماساژ ریلکسی و درمانی",
            }
        ),
    )

    def clean_expert(self):
        value = (self.cleaned_data.get("expert") or "").strip()
        if not value:
            raise ValidationError("تخصص اصلی را وارد کنید.")
        return value


# -------------------------------------------------------------------------------------------------------------
# Verify Registration Form
class VerifyRegisterForm(forms.Form):
    active_code = forms.CharField(
        label="کد فعالسازی ",
        error_messages={"required": "این فیلد نمی‌تواند خالی باشد"},
        widget=forms.TextInput(
            attrs={
                "class": "register-input-group",
                "placeholder": "کد دریافتی را وارد کنید ",
            },
        ),
    )


# ------------------------------------------------------------------------------------------------------------------
# Login Form
class LoginUserForm(forms.Form):
    mobile_number = forms.CharField(
        label="شماره موبایل",
        error_messages={"required": "این فیلد نمی‌تواند خالی باشد "},
        widget=forms.TextInput(
            attrs={
                "class": "register-input-group",
                "placeholder": "موبایل را وارد کنید ",
            },
        ),
    )
    password = forms.CharField(
        label="رمز عبور ",
        error_messages={"required": "این فیلد نمی‌تواند خالی باشد "},
        widget=forms.PasswordInput(
            attrs={
                "class": "register-input-group",
                "placeholder": "رمز عبور را وارد کنید ",
            },
        ),
    )


# -------------------------------------------------------------------------------------------------------------------
# فرم تغییر رمز عبور
class ChangePasswordForm(forms.Form):
    current_password = forms.CharField(
        label="رمز عبور فعلی",
        required=False,
        error_messages={"required": "این فیلد نمی‌تواند خالی باشد"},
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "رمز عبور فعلی را وارد کنید",
            },
        ),
    )
    password1 = forms.CharField(
        label="رمز عبور جدید",
        error_messages={"required": "این فیلد نمی‌تواند خالی باشد"},
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "رمز عبور جدید را وارد کنید",
            },
        ),
    )
    password2 = forms.CharField(
        label="تکرار رمز عبور جدید",
        error_messages={"required": "این فیلد نمی‌تواند خالی باشد"},
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "رمز عبور جدید را دوباره وارد کنید",
            },
        ),
    )

    def __init__(self, *args, require_current_password=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_current_password = require_current_password
        self.fields["current_password"].required = require_current_password
        if not require_current_password:
            self.fields["current_password"].widget = forms.HiddenInput()

    def clean_current_password(self):
        return self.cleaned_data.get("current_password")

    def clean_password2(self):
        cd = self.cleaned_data
        password1 = cd.get("password1")
        password2 = cd.get("password2")

        if password1 and password2 and password1 != password2:
            raise ValidationError("رمز عبور و تکرار آن مغایرت دارند")

        if password1 and len(password1) < 8:
            raise ValidationError("رمز عبور باید حداقل ۸ کاراکتر باشد")

        if password1:
            try:
                validate_password(password1)
            except ValidationError as exc:
                raise ValidationError(
                    user_error_message(
                        exc, fallback="رمز عبور شرایط امنیتی لازم را ندارد."
                    )
                )

        return password2


# ------------------------------------------------------------------------------------------------------------------------
# فرم فراموشی رمز عبور
class RememberPasswordForm(forms.Form):
    mobile_number = forms.CharField(
        label="شماره موبایل",
        error_messages={"required": "این فیلد نمی‌تواند خالی باشد "},
        widget=forms.TextInput(
            attrs={
                "class": "register-input-group",
                "placeholder": "موبایل را وارد کنید ",
            },
        ),
    )


# ------------------------------------------------------------------------------------------------------------------------
# فرم آپدیت پروفایل مشتری
class CustomerUpdateProfileForm(forms.ModelForm):
    image = forms.ImageField(label="تصویر پروفایل", required=False)

    birth_day = forms.CharField(
        label="روز",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "روز"}),
    )
    birth_month = forms.CharField(
        label="ماه",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "ماه"}),
    )
    birth_year = forms.CharField(
        label="سال",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "سال"}),
    )

    class Meta:
        model = CustomUser
        fields = ["name", "family", "email"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "نام خود را بنویسید"}
            ),
            "family": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "نام خانوادگی خود را بنویسید",
                }
            ),
            "email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "ایمیل خود را وارد کنید"}
            ),
        }

    def __init__(self, *args, **kwargs):
        customer_instance = kwargs.pop("customer_instance", None)

        files = kwargs.get("files")
        if files is None and len(args) > 1:
            files = args[1]

        raw_image = files.get("image") if files else None
        self._raw_profile_image_content_type = (
            getattr(raw_image, "content_type", "") or ""
        )

        super().__init__(*args, **kwargs)

        self.fields["image"].widget.attrs.update(
            {"accept": "image/jpeg,image/png,image/webp"}
        )

        self.fields["name"].required = True
        self.fields["family"].required = True
        self.fields["name"].error_messages["required"] = "نام را وارد کنید."
        self.fields["family"].error_messages["required"] = "نام خانوادگی را وارد کنید."
        self.fields["email"].error_messages["invalid"] = "ایمیل واردشده معتبر نیست."

        if customer_instance:
            self.fields["image"].initial = customer_instance.profile_image
            if customer_instance.birth_date:
                j_date = jdatetime.date.fromgregorian(date=customer_instance.birth_date)
                self.fields["birth_day"].initial = str(j_date.day)
                self.fields["birth_month"].initial = str(j_date.month)
                self.fields["birth_year"].initial = str(j_date.year)

    def clean_name(self):
        value = (self.cleaned_data.get("name") or "").strip()
        if not value:
            raise ValidationError("نام را وارد کنید.")
        return value

    def clean_family(self):
        value = (self.cleaned_data.get("family") or "").strip()
        if not value:
            raise ValidationError("نام خانوادگی را وارد کنید.")
        return value

    def clean_email(self):
        value = (self.cleaned_data.get("email") or "").strip()
        if not value:
            return ""

        try:
            validate_email(value)
        except ValidationError as exc:
            raise ValidationError("ایمیل واردشده معتبر نیست.") from exc

        return value.lower()

    def clean_image(self):
        image = self.cleaned_data.get("image")
        return validate_customer_profile_image_upload(
            image,
            declared_content_type=self._raw_profile_image_content_type or None,
        )

    def save(self, commit=True):
        user_instance = super().save(commit=False)
        customer_instance = self.customer_instance or Customer.objects.get(
            user=user_instance
        )

        birth_day = self.cleaned_data.get("birth_day")
        birth_month = self.cleaned_data.get("birth_month")
        birth_year = self.cleaned_data.get("birth_year")

        if birth_day and birth_month and birth_year:
            try:
                j_date = jdatetime.date(
                    int(birth_year), int(birth_month), int(birth_day)
                )
                customer_instance.birth_date = j_date.togregorian()
            except (ValueError, AttributeError):
                customer_instance.birth_date = None
        else:
            customer_instance.birth_date = None

        if self.cleaned_data.get("image"):
            customer_instance.profile_image = self.cleaned_data["image"]

        if commit:
            user_instance.save()
            customer_instance.save()

        return user_instance


class SalonManagerUpdateProfileForm(forms.ModelForm):
    """Edit only the manager account identity owned by this profile page.

    Salon contact/location data belongs to the salon profile, while the mobile
    number is the authentication identifier and must not be writable through a
    cosmetic profile form.
    """

    image = forms.ImageField(label="تصویر پروفایل", required=False)

    class Meta:
        model = CustomUser
        fields = ["name", "family", "email"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "نام"}
            ),
            "family": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "نام خانوادگی"}
            ),
            "email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "ایمیل (اختیاری)"}
            ),
        }

    def __init__(self, *args, **kwargs):
        manager_instance = kwargs.pop("manager_instance", None)

        files = kwargs.get("files")
        if files is None and len(args) > 1:
            files = args[1]
        raw_image = files.get("image") if files else None
        self._raw_profile_image_content_type = (
            getattr(raw_image, "content_type", "") or ""
        )

        super().__init__(*args, **kwargs)
        self.manager_instance = manager_instance
        self.fields["image"].widget.attrs.update(
            {"accept": "image/jpeg,image/png,image/webp"}
        )

        if manager_instance:
            self.fields["image"].initial = manager_instance.profile_image

    def clean_image(self):
        image = self.cleaned_data.get("image")
        return validate_customer_profile_image_upload(
            image,
            declared_content_type=self._raw_profile_image_content_type or None,
        )

    def save(self, commit=True):
        user_instance = super().save(commit=False)
        manager_instance = self.manager_instance or SalonManager.objects.get(
            user=user_instance
        )

        image = self.cleaned_data.get("image")
        if image:
            manager_instance.profile_image = image

        if commit:
            user_instance.save()
            if image:
                manager_instance.save(update_fields=["profile_image"])

        return user_instance


class CustomerAddressForm(forms.ModelForm):
    class Meta:
        model = CustomerAddress
        fields = [
            "title",
            "phone_number",
            "city",
            "address_line",
            "postal_code",
            "plaque",
            "unit",
            "is_default",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "مثلاً خانه یا محل کار"}),
            "phone_number": forms.TextInput(attrs={"placeholder": "شماره تماس"}),
            "city": forms.TextInput(attrs={"placeholder": "شهر"}),
            "address_line": forms.Textarea(
                attrs={"rows": 4, "placeholder": "نشانی کامل"}
            ),
            "postal_code": forms.TextInput(attrs={"placeholder": "کد پستی ۱۰ رقمی"}),
            "plaque": forms.TextInput(attrs={"placeholder": "پلاک"}),
            "unit": forms.TextInput(attrs={"placeholder": "واحد"}),
            "is_default": forms.CheckboxInput(
                attrs={
                    "class": "h-4 w-4 rounded border-gray-300 text-purple-600 focus:ring-purple-500"
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        input_class = (
            "w-full px-4 py-3 rounded-2xl border border-gray-200 text-gray-900 "
            "placeholder-gray-400 focus:outline-none focus:border-purple-400 "
            "focus:ring-1 focus:ring-purple-400 transition"
        )

        textarea_class = (
            "w-full px-4 py-3 rounded-2xl border border-gray-200 text-gray-900 "
            "placeholder-gray-400 focus:outline-none focus:border-purple-400 "
            "focus:ring-1 focus:ring-purple-400 transition resize-none"
        )

        for field_name in [
            "title",
            "phone_number",
            "city",
            "postal_code",
            "plaque",
            "unit",
        ]:
            self.fields[field_name].widget.attrs["class"] = input_class

        self.fields["address_line"].widget.attrs["class"] = textarea_class

        self.fields["title"].label = "عنوان آدرس"
        self.fields["phone_number"].label = "شماره تماس"
        self.fields["city"].label = "شهر"
        self.fields["address_line"].label = "نشانی کامل"
        self.fields["postal_code"].label = "کد پستی"
        self.fields["plaque"].label = "پلاک"
        self.fields["unit"].label = "واحد"

        self.fields["title"].required = True
        self.fields["address_line"].required = True

        self.fields["phone_number"].widget.attrs.update(
            {"inputmode": "numeric", "dir": "ltr"}
        )
        self.fields["postal_code"].widget.attrs.update(
            {"inputmode": "numeric", "dir": "ltr", "maxlength": "10"}
        )

    def clean_title(self):
        value = (self.cleaned_data.get("title") or "").strip()
        if not value:
            raise ValidationError("عنوان آدرس را وارد کنید.")
        return value

    def clean_address_line(self):
        value = (self.cleaned_data.get("address_line") or "").strip()
        if not value:
            raise ValidationError("نشانی کامل را وارد کنید.")
        return value

    def clean_phone_number(self):
        value = normalize_digits(self.cleaned_data.get("phone_number"))
        if not value:
            return ""
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) not in [10, 11]:
            raise ValidationError("شماره تماس باید فقط شامل عدد و ۱۰ یا ۱۱ رقم باشد.")
        return digits

    def clean_postal_code(self):
        value = normalize_digits(self.cleaned_data.get("postal_code"))
        if not value:
            return ""
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) != 10:
            raise ValidationError("کد پستی باید ۱۰ رقم باشد.")
        return digits

    def save(self, customer, commit=True):
        address = super().save(commit=False)
        address.customer = customer
        address.recipient_name = customer.get_fullName()
        if not address.phone_number:
            address.phone_number = customer.user.mobile_number
        if commit:
            address.save()
        return address


class AddCustomerForm(forms.Form):
    name = forms.CharField(max_length=100, label="نام")
    family = forms.CharField(max_length=100, label="نام خانوادگی")
    mobile_number = forms.CharField(max_length=11, label="شماره موبایل")
    email = forms.EmailField(required=False, label="ایمیل")
    address = forms.CharField(required=False, widget=forms.Textarea, label="آدرس")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        input_class = (
            "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm "
            "text-slate-800 outline-none transition focus:border-loomera-primary/30 "
            "focus:ring-2 focus:ring-loomera-primary/10"
        )
        self.fields["name"].widget.attrs.update(
            {"class": input_class, "placeholder": "مثلاً سارا"}
        )
        self.fields["family"].widget.attrs.update(
            {"class": input_class, "placeholder": "مثلاً احمدی"}
        )
        self.fields["mobile_number"].widget.attrs.update(
            {
                "class": input_class,
                "placeholder": "09xxxxxxxxx",
                "inputmode": "numeric",
                "dir": "ltr",
            }
        )
        self.fields["email"].widget.attrs.update(
            {"class": input_class, "placeholder": "example@email.com", "dir": "ltr"}
        )
        self.fields["address"].widget.attrs.update(
            {
                "class": "min-h-28 w-full rounded-[24px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-loomera-primary/30 focus:ring-2 focus:ring-loomera-primary/10",
                "placeholder": "نشانی یا توضیح کوتاه برای شناسایی مشتری",
            }
        )

    def clean_mobile_number(self):
        value = normalize_digits(self.cleaned_data.get("mobile_number"))
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) != 11 or not digits.startswith("09"):
            raise ValidationError("شماره موبایل باید ۱۱ رقم باشد و با 09 شروع شود.")
        if CustomUser.objects.filter(mobile_number=digits).exists():
            raise ValidationError("این شماره موبایل قبلاً ثبت شده است.")
        return digits

    def clean_name(self):
        value = (self.cleaned_data.get("name") or "").strip()
        if not value:
            raise ValidationError("نام مشتری را وارد کنید.")
        return value

    def clean_family(self):
        value = (self.cleaned_data.get("family") or "").strip()
        if not value:
            raise ValidationError("نام خانوادگی مشتری را وارد کنید.")
        return value


class DeleteAccountReasonForm(forms.Form):
    REASON_CHOICES = (
        ("not_using", "دیگر از Loomera استفاده نمی‌کنم."),
        ("too_many_notifications", "اعلان‌ها یا پیام‌ها برای من زیاد است."),
        ("privacy_concern", "نگران حریم خصوصی یا اطلاعات حساب هستم."),
        ("bad_experience", "تجربه خوبی از رزرو یا استفاده از سرویس نداشتم."),
        ("found_alternative", "از سرویس یا روش دیگری استفاده می‌کنم."),
        ("other", "دلیل دیگری دارم."),
    )

    reason = forms.ChoiceField(
        required=True,
        label="دلیل حذف حساب",
        choices=REASON_CHOICES,
        error_messages={"required": "لطفاً دلیل حذف حساب را انتخاب کنید."},
        widget=forms.RadioSelect,
    )

    confirm_appointments = forms.BooleanField(
        required=True,
        label="می‌دانم که دسترسی به نوبت‌ها و سوابق حساب خود را از دست می‌دهم.",
        error_messages={
            "required": "برای ادامه باید از دست رفتن نوبت‌ها و سوابق را تأیید کنید."
        },
    )

    confirm_bookings = forms.BooleanField(
        required=True,
        label="می‌دانم که پس از حذف حساب، امکان رزرو از طریق Loomera برای من متوقف می‌شود.",
        error_messages={"required": "برای ادامه باید توقف امکان رزرو را تأیید کنید."},
    )

    password = forms.CharField(
        required=True,
        label="رمز عبور",
        error_messages={"required": "برای حذف حساب، رمز عبور خود را وارد کنید."},
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "رمز عبور حساب را وارد کنید",
            }
        ),
    )
