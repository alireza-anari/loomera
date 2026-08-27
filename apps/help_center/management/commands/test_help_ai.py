from django.core.management.base import BaseCommand, CommandError

from apps.help_center.ai import AIProviderError, get_ai_provider


class Command(BaseCommand):
    help = "Test the configured Help AI provider with a minimal direct request."

    def handle(self, *args, **options):
        provider = get_ai_provider()
        self.stdout.write(f"Provider: {provider.provider_name}")
        self.stdout.write(f"Model: {getattr(provider, 'model', '') or '<empty>'}")
        self.stdout.write(f"Enabled: {bool(getattr(provider, 'enabled', False))}")
        if not getattr(provider, "enabled", False):
            raise CommandError(
                "Help AI provider is not fully configured. Check HELP_AI_PROVIDER, "
                "HELP_AI_MODEL and the matching API key."
            )
        try:
            answer = provider.complete(
                [
                    {
                        "role": "user",
                        "content": "فقط به فارسی بنویس: اتصال دستیار لومرا برقرار است",
                    }
                ]
            )
        except AIProviderError as exc:
            detail = (exc.detail or "").strip().replace("\n", " ")[:500]
            raise CommandError(
                f"AI test failed: provider={exc.provider or provider.provider_name} "
                f"status={exc.status or '-'} detail={detail or '-'}"
            ) from exc
        self.stdout.write(self.style.SUCCESS(answer))
