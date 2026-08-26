from django.core.management.base import BaseCommand
from django.urls import URLPattern, URLResolver, get_resolver

from apps.help_center.models import HelpPageContext
from apps.help_center.page_catalog import TARGET_ROUTE_NAMES


NAMESPACES = {
    "accounts", "articles", "csf", "dashboards", "help_center", "main",
    "messaging", "notifications", "orders", "payments", "salons", "search",
    "services", "stylists",
}

IGNORE_TOKENS = {
    "api", "summary", "read_all", "notification_read", "toggle", "delete",
    "remove", "cancel", "action", "availability", "export", "download",
    "preview", "qr_", "image", "suggestions", "click", "mark_", "set_active",
    "logout", "health", "robots", "verify", "complete",
}


def walk(patterns, namespaces=()):
    for entry in patterns:
        if isinstance(entry, URLResolver):
            next_ns = namespaces + ((entry.namespace,) if entry.namespace else ())
            yield from walk(entry.url_patterns, next_ns)
        elif isinstance(entry, URLPattern) and entry.name:
            yield ":".join((*namespaces, entry.name)) if namespaces else entry.name


def is_candidate(view_name):
    if ":" in view_name:
        namespace, local = view_name.split(":", 1)
        if namespace not in NAMESPACES:
            return False
    else:
        local = view_name
        if view_name != "support":
            return False
    lowered = local.lower()
    return not any(token in lowered for token in IGNORE_TOKENS)


class Command(BaseCommand):
    help = "Audit exact route-name coverage for Loomera Help Center page guides."

    def handle(self, *args, **options):
        project_routes = set(walk(get_resolver().url_patterns))
        target_routes = set(TARGET_ROUTE_NAMES)
        active_db_routes = set(
            HelpPageContext.objects.filter(is_active=True)
            .exclude(route_name="")
            .values_list("route_name", flat=True)
        )

        missing_from_project = sorted(target_routes - project_routes)
        missing_in_db = sorted(target_routes - active_db_routes)
        candidate_routes = {name for name in project_routes if is_candidate(name)}
        uncovered_candidates = sorted(candidate_routes - active_db_routes)

        self.stdout.write(self.style.MIGRATE_HEADING("Help Center route coverage"))
        self.stdout.write(f"Project named routes: {len(project_routes)}")
        self.stdout.write(f"Declared user-facing routes: {len(target_routes)}")
        self.stdout.write(f"Active DB exact contexts: {len(active_db_routes)}")

        if missing_from_project:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Declared routes not found in current project:"))
            for name in missing_from_project:
                self.stdout.write(f"  - {name}")

        if missing_in_db:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR("Declared routes missing from HelpPageContext DB:"))
            for name in missing_in_db:
                self.stdout.write(f"  - {name}")
            self.stdout.write(self.style.WARNING("Run: python manage.py seed_help_center"))
        else:
            self.stdout.write(self.style.SUCCESS("All declared page routes have active exact contexts."))

        if uncovered_candidates:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Potential user-facing routes without exact guides (heuristic):"))
            for name in uncovered_candidates:
                self.stdout.write(f"  - {name}")

        if missing_from_project or missing_in_db:
            raise SystemExit(1)
