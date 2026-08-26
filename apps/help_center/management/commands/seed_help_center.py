from django.core.management.base import BaseCommand
from django.db import transaction

from apps.help_center import knowledge
from apps.help_center.models import (
    Audience,
    HelpArticle,
    HelpCategory,
    HelpLegalDocument,
    HelpPageContext,
)
from apps.help_center.page_catalog import CATEGORY_DEFAULTS, CONTEXTS, GUIDES


class Command(BaseCommand):
    help = (
        "Seed missing Help Center content. Existing Admin edits are preserved by "
        "default. Use --refresh-defaults to overwrite code-seeded defaults."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--refresh-defaults",
            action="store_true",
            help="Update existing seeded categories/articles/contexts from code defaults.",
        )

    def _upsert(self, model, lookup, defaults, refresh):
        obj, created = model.objects.get_or_create(**lookup, defaults=defaults)
        if not created and refresh:
            for field, value in defaults.items():
                setattr(obj, field, value)
            obj.save()
        return obj

    @transaction.atomic
    def handle(self, *args, **options):
        refresh = bool(options["refresh_defaults"])
        category_map = {}

        # Original Phase 1/2 categories remain compatible.
        for index, (slug, data) in enumerate(knowledge.CATEGORIES.items(), start=1):
            audience = slug if slug in {Audience.CUSTOMER, Audience.MANAGER, Audience.STYLIST} else Audience.ALL
            category_map[slug] = self._upsert(
                HelpCategory,
                {"slug": slug},
                {
                    "title": data["title"],
                    "description": data["description"],
                    "icon": data["icon"],
                    "audience": audience,
                    "sort_order": index * 10,
                    "is_published": True,
                },
                refresh,
            )

        next_order = 200
        for slug, data in CATEGORY_DEFAULTS.items():
            if slug in category_map:
                continue
            title, icon, description = data
            audience = slug if slug in {Audience.CUSTOMER, Audience.MANAGER, Audience.STYLIST} else Audience.ALL
            category_map[slug] = self._upsert(
                HelpCategory,
                {"slug": slug},
                {
                    "title": title,
                    "description": description,
                    "icon": icon,
                    "audience": audience,
                    "sort_order": next_order,
                    "is_published": True,
                },
                refresh,
            )
            next_order += 10

        article_map = {}

        # Keep existing fallback docs, then let Phase 3 exact-page docs add to them.
        original_specs = []
        for item in knowledge.ARTICLES:
            original_specs.append(
                {
                    "key": item.key,
                    "slug": item.slug,
                    "title": item.title,
                    "audience": item.role,
                    "category": item.category,
                    "summary": item.summary,
                    "body": "",
                    "steps": [{"title": t, "body": b} for t, b in item.steps],
                    "tips": list(item.tips),
                    "keywords": " ".join(item.keywords),
                }
            )

        merged = {spec["key"]: spec for spec in original_specs}
        for spec in GUIDES:
            merged[spec["key"]] = spec

        for index, spec in enumerate(merged.values(), start=1):
            category = category_map.get(spec["category"])
            if category is None:
                category = self._upsert(
                    HelpCategory,
                    {"slug": spec["category"]},
                    {
                        "title": spec["category"],
                        "description": "",
                        "icon": "fa-regular fa-circle-question",
                        "audience": Audience.ALL,
                        "sort_order": 900,
                        "is_published": True,
                    },
                    refresh,
                )
                category_map[spec["category"]] = category

            audience = spec["audience"] if spec["audience"] in Audience.values else Audience.ALL
            article_map[spec["key"]] = self._upsert(
                HelpArticle,
                {"key": spec["key"]},
                {
                    "category": category,
                    "slug": spec["slug"],
                    "title": spec["title"],
                    "audience": audience,
                    "summary": spec["summary"],
                    "body": spec.get("body", ""),
                    "steps": spec.get("steps", []),
                    "tips": spec.get("tips", []),
                    "keywords": spec.get("keywords", ""),
                    "sort_order": index * 10,
                    "is_published": True,
                },
                refresh,
            )

        exact_contexts = 0
        for spec in CONTEXTS:
            article = article_map.get(spec["article_key"])
            if article is None:
                continue
            route_name = spec.get("route_name", "")
            path_pattern = spec.get("path_pattern", "")
            role = spec.get("role", Audience.ALL)
            lookup = {"role": role, "route_name": route_name} if route_name else {"role": role, "path_pattern": path_pattern}
            prompts = spec.get("quick_prompts") or [
                step.get("title", "")
                for step in (article.steps or [])[:3]
                if isinstance(step, dict) and step.get("title")
            ]
            self._upsert(
                HelpPageContext,
                lookup,
                {
                    "page_key": spec["page_key"],
                    "article": article,
                    "route_name": route_name,
                    "path_pattern": path_pattern,
                    "quick_prompts": prompts,
                    "priority": spec.get("priority", 100),
                    "is_active": True,
                },
                refresh,
            )
            exact_contexts += 1

        # Regex mappings remain only as compatibility fallback.
        for index, (pattern, page_key) in enumerate(knowledge.ROUTE_RULES, start=1):
            article = article_map.get(page_key)
            if not article:
                continue
            role = article.audience if article.audience in {Audience.CUSTOMER, Audience.MANAGER, Audience.STYLIST} else Audience.ALL
            self._upsert(
                HelpPageContext,
                {"role": role, "path_pattern": pattern.pattern},
                {
                    "page_key": page_key,
                    "article": article,
                    "route_name": "",
                    "quick_prompts": [
                        step.get("title", "")
                        for step in (article.steps or [])[:3]
                        if isinstance(step, dict) and step.get("title")
                    ],
                    "priority": 500 - min(index, 400),
                    "is_active": True,
                },
                refresh,
            )

        legal_seed = (
            ("privacy", "حریم خصوصی", "accounts:privacy_policy"),
            ("terms", "شرایط استفاده", "accounts:terms_of_use"),
            ("messaging-privacy", "حریم خصوصی پیام‌رسان‌ها", "messaging:privacy"),
        )
        for slug, title, url_name in legal_seed:
            self._upsert(
                HelpLegalDocument,
                {"slug": slug, "version": "legacy"},
                {
                    "title": title,
                    "summary": "",
                    "content": "",
                    "audience": Audience.ALL,
                    "status": HelpLegalDocument.Status.PUBLISHED,
                    "is_current": True,
                    "legacy_url_name": url_name,
                },
                refresh,
            )

        mode = "refresh-defaults" if refresh else "preserve-admin-edits"
        self.stdout.write(
            self.style.SUCCESS(
                f"Help Center seed complete ({mode}): {len(article_map)} articles, "
                f"{exact_contexts} exact page contexts."
            )
        )
