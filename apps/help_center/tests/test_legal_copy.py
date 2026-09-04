from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class LegalCopyGuardTests(SimpleTestCase):
    def _template(self, relative_path):
        return (Path(settings.BASE_DIR) / relative_path).read_text(encoding="utf-8")

    def test_legal_index_is_plain_language_hub(self):
        text = self._template("templates/help_center/legal_index.html")
        self.assertIn("قوانین و مقررات لومرا", text)
        self.assertIn("قبل از رزرو", text)
        self.assertIn("قانون از این متن مهم‌تر است", text)

    def test_terms_explains_platform_and_in_person_service_separately(self):
        text = self._template("templates/accounts/terms_of_use.html")
        self.assertIn("لومرا چه کاری انجام می‌دهد", text)
        self.assertIn("خدمت حضوری", text)
        self.assertIn("حقوقی را که قانون برای مصرف‌کننده حفظ کرده", text)

    def test_terms_does_not_invent_current_cancellation_fee(self):
        text = self._template("templates/accounts/terms_of_use.html")
        self.assertIn("جریمه خودکار لغو یا عدم مراجعه از مشتری دریافت نمی‌شود", text)
        self.assertNotIn("جریمه ۲۴ ساعت", text)
        self.assertNotIn("جریمه ۴۸ ساعت", text)

    def test_privacy_explains_sensitive_data_and_user_controls(self):
        text = self._template("templates/accounts/privacy_policy.html")
        self.assertIn("رضایت صریح مشتری", text)
        self.assertIn("درخواست حذف حساب", text)
        self.assertIn("پیام ضروری با تبلیغ فرق دارد", text)

    def test_privacy_does_not_claim_unverified_ad_tracking(self):
        text = self._template("templates/accounts/privacy_policy.html")
        self.assertIn("ادعایی درباره استفاده از کوکی تبلیغاتی", text)
        self.assertNotIn("Google Analytics", text)

    def test_messaging_privacy_separates_marketing_and_operational_messages(self):
        text = self._template("templates/messaging/privacy.html")
        self.assertIn("پیام ضروری و پیام تبلیغاتی جداست", text)
        self.assertIn("انتخابت را بعداً تغییر بدهی", text)
        self.assertIn("رمز پویا", text)
