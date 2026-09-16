from django.test import SimpleTestCase

from apps.help_center.actions.manager_operations import _mobile_from_message, _role_title_from_message


class LumiManagerParserTests(SimpleTestCase):
    def test_extracts_persian_mobile_for_invite(self):
        self.assertEqual(_mobile_from_message("این متخصص رو با ۰۹۱۲۱۲۳۴۵۶۷ دعوت کن"), "09121234567")

    def test_extracts_optional_role_title(self):
        self.assertEqual(_role_title_from_message("دعوت کن، عنوان: رنگ کار"), "رنگ کار")
