from django.apps import AppConfig


class InstagramIntegrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.instagram_integration"
    verbose_name = "Instagram Integration"

    def ready(self):
        # Register deployment/configuration checks. No network I/O here.
        from . import checks  # noqa: F401
