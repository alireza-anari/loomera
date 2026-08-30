from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class TelegramDashboardCommunicationSettingsStaticGuards(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_shared_manager_stylist_settings_expose_bale_and_telegram(self):
        view = self.read("apps/dashboards/manager_settings_views.py")
        template = self.read("templates/dashboards/manager_communication_settings.html")

        self.assertIn("MessagingProviderKey.BALE", view)
        self.assertIn("MessagingProviderKey.TELEGRAM", view)
        self.assertIn("NotificationChannel.BALE.value", view)
        self.assertIn("NotificationChannel.TELEGRAM.value", view)
        self.assertIn('"messaging:provider_quick_connect"', view)

        self.assertIn('name="bale_operational"', template)
        self.assertIn('name="bale_marketing"', template)
        self.assertIn('name="telegram_operational"', template)
        self.assertIn('name="telegram_marketing"', template)
        self.assertIn("اتصال به بله", template)
        self.assertIn("اتصال به تلگرام", template)
        self.assertIn('data-lm-task-label="اتصال پیام‌رسان‌ها"', template)

    def test_settings_copy_no_longer_describes_bale_as_only_live_provider(self):
        view = self.read("apps/dashboards/manager_settings_views.py")
        self.assertNotIn("This page intentionally exposes only the channel", view)
        self.assertIn("بله و تلگرام", view)


if __name__ == "__main__":
    unittest.main(verbosity=2)
