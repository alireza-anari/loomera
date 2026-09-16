from django.apps import AppConfig


class HelpCenterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.help_center"
    verbose_name = "مرکز راهنمای لومرا"

    def ready(self):
        from . import signals  # noqa: F401

