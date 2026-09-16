from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.urls import NoReverseMatch, reverse

from apps.help_center.models import ArticleType, HelpArticle


ACTIONS_FILE = Path(__file__).resolve().parents[2] / "data" / "workflow_actions.json"


class Command(BaseCommand):
    help = "Audit guided Help Center workflow coverage and route links."

    def handle(self, *args, **options):
        payload = json.loads(ACTIONS_FILE.read_text(encoding="utf-8"))
        specs = payload.get("articles", {})
        workflows = list(
            HelpArticle.objects.filter(
                article_type=ArticleType.WORKFLOW,
                is_published=True,
            ).order_by("audience", "key")
        )

        issues = []
        linked = 0
        total_steps = 0
        by_role = {}

        for article in workflows:
            steps = list(article.steps or [])
            by_role.setdefault(article.audience, {"articles": 0, "linked": 0})
            by_role[article.audience]["articles"] += 1
            if not steps:
                issues.append(f"NO STEPS {article.key}")
                continue

            total_steps += len(steps)
            has_link = False
            for index, step in enumerate(steps, 1):
                if not isinstance(step, dict):
                    issues.append(f"INVALID STEP {article.key} #{index}")
                    continue
                if not str(step.get("title") or "").strip():
                    issues.append(f"NO TITLE {article.key} #{index}")
                if not str(step.get("body") or step.get("description") or "").strip():
                    issues.append(f"NO BODY {article.key} #{index}")
                route = str(step.get("route_name") or step.get("url_name") or "").strip()
                if route:
                    try:
                        reverse(route)
                    except NoReverseMatch:
                        issues.append(f"BROKEN/ARG ROUTE {article.key} #{index}: {route}")
                    else:
                        has_link = True

                dynamic_route = str(step.get("dynamic_route_name") or "").strip()
                if dynamic_route:
                    mapping = step.get("dynamic_kwargs") or {}
                    context_routes = step.get("context_route_names") or []
                    if not isinstance(mapping, dict) or not mapping:
                        issues.append(
                            f"DYNAMIC ROUTE WITHOUT KWARGS {article.key} #{index}: {dynamic_route}"
                        )
                    if not isinstance(context_routes, list) or not context_routes:
                        issues.append(
                            f"DYNAMIC ROUTE WITHOUT CONTEXT ROUTES {article.key} #{index}: {dynamic_route}"
                        )
                    # A parameterized route should fail without kwargs; a static
                    # route is also acceptable if explicitly configured.
                    has_link = True

            if has_link:
                linked += 1
                by_role[article.audience]["linked"] += 1

        missing_fixture = sorted(
            article.key for article in workflows if article.key not in specs
        )
        for key in missing_fixture:
            issues.append(f"MISSING ACTION SPEC {key}")

        self.stdout.write("Loomera Help guided workflow audit")
        self.stdout.write(f"Published workflows: {len(workflows)}")
        self.stdout.write(f"Structured steps: {total_steps}")
        self.stdout.write(f"Workflows with clickable entry links: {linked}/{len(workflows)}")
        self.stdout.write("")
        for role, values in sorted(by_role.items()):
            self.stdout.write(
                f"{role}: {values['articles']} workflow(s), "
                f"{values['linked']} with clickable links"
            )

        if issues:
            self.stdout.write("")
            for issue in issues:
                self.stdout.write(self.style.ERROR(issue))
            raise SystemExit(f"Workflow audit failed: {len(issues)} issue(s).")

        self.stdout.write(self.style.SUCCESS("Workflow audit passed."))
