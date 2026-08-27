from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.help_center.models import (
    Audience,
    HelpArticle,
    HelpCategory,
    HelpLegalDocument,
    HelpPageContext,
)


DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "production_docs.json"
WORKFLOW_ACTIONS_FILE = Path(__file__).resolve().parents[2] / "data" / "workflow_actions.json"


class Command(BaseCommand):
    help = (
        "Seed the docs-first Loomera Help Center from production_docs.json. "
        "Published Admin edits are preserved by default. Use --refresh-defaults "
        "only when code defaults must intentionally replace current seeded docs."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--refresh-defaults",
            action="store_true",
            help="Overwrite existing fixture-managed categories/articles/contexts.",
        )

    def _load_data(self):
        try:
            payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise CommandError(f"Help docs fixture not found: {DATA_FILE}") from exc
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid Help docs JSON: {exc}") from exc

        for key in ("categories", "articles", "contexts"):
            if not isinstance(payload.get(key), list):
                raise CommandError(f"production_docs.json must contain a list named {key!r}.")
        return payload

    def _load_workflow_actions(self):
        if not WORKFLOW_ACTIONS_FILE.exists():
            return {}
        try:
            payload = json.loads(WORKFLOW_ACTIONS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid workflow_actions.json: {exc}") from exc
        articles = payload.get("articles", {})
        return articles if isinstance(articles, dict) else {}

    @staticmethod
    def _assign_and_save(obj, defaults):
        changed = []
        for field, value in defaults.items():
            if getattr(obj, field) != value:
                setattr(obj, field, value)
                changed.append(field)
        if changed:
            obj.save(update_fields=[*changed, "updated_at"] if hasattr(obj, "updated_at") else changed)
        return bool(changed)

    def _upsert_category(self, spec, *, refresh):
        defaults = {
            "title": spec["title"],
            "description": spec.get("description", ""),
            "icon": spec.get("icon", "fa-regular fa-circle-question"),
            "audience": spec.get("audience", Audience.ALL),
            "sort_order": int(spec.get("sort_order", 100)),
            "is_published": True,
        }
        obj, created = HelpCategory.objects.get_or_create(slug=spec["slug"], defaults=defaults)
        # reset_help_center_prototype deliberately unpublishes old prototype rows;
        # an unpublished fixture row is safe to adopt once without overwriting a
        # currently published editor-maintained category.
        if not created and (refresh or not obj.is_published):
            self._assign_and_save(obj, defaults)
        return obj, created

    def _upsert_article(self, spec, category, *, refresh, sort_order, workflow_actions=None):
        workflow_spec = (workflow_actions or {}).get(spec["key"], {})
        defaults = {
            "key": spec["key"],
            "category": category,
            "slug": spec["slug"],
            "title": spec["title"],
            "audience": spec.get("audience", Audience.ALL),
            "article_type": spec.get("article_type", "guide"),
            "aliases": spec.get("aliases", ""),
            "is_featured": bool(spec.get("is_featured", False)),
            "source_refs": spec.get("source_refs", []),
            "summary": spec["summary"],
            "body": spec.get("body", ""),
            "steps": workflow_spec.get("steps", spec.get("steps", [])),
            "tips": spec.get("tips", []),
            "keywords": spec.get("keywords", ""),
            "sort_order": int(spec.get("sort_order", sort_order)),
            "is_published": True,
        }

        by_key = HelpArticle.objects.filter(key=spec["key"]).first()
        by_slug = HelpArticle.objects.filter(slug=spec["slug"]).first()

        # During the docs-first migration, old prototype articles remain in the
        # database as unpublished rows. Some production documents intentionally
        # reuse their public slug while getting a cleaner stable key. Adopt that
        # unpublished row instead of inserting a duplicate slug.
        if by_key is None and by_slug is not None:
            if by_slug.is_published and not refresh:
                raise CommandError(
                    "Cannot adopt published article with duplicate slug "
                    f"{spec['slug']!r}: existing key={by_slug.key!r}, "
                    f"fixture key={spec['key']!r}. Resolve it in Admin or use "
                    "--refresh-defaults intentionally."
                )
            obj = by_slug
            self._assign_and_save(obj, defaults)
            return obj, False

        # A rarer transition case: the desired key already exists, while an old
        # unpublished prototype row owns the desired slug. Retire only that stale
        # unpublished slug so the canonical row can take it. Published collisions
        # are never changed silently.
        if by_key is not None and by_slug is not None and by_key.pk != by_slug.pk:
            if by_slug.is_published:
                raise CommandError(
                    "Published HelpArticle slug collision for "
                    f"{spec['slug']!r}: keys {by_key.key!r} and {by_slug.key!r}."
                )
            legacy_slug = f"prototype-{by_slug.pk}-{by_slug.slug}"
            max_len = HelpArticle._meta.get_field("slug").max_length
            by_slug.slug = legacy_slug[:max_len]
            by_slug.save(update_fields=["slug", "updated_at"])

        if by_key is not None:
            obj = by_key
            if refresh or not obj.is_published:
                # Saving the article rebuilds its chunks through post_save signal.
                self._assign_and_save(obj, defaults)
            return obj, False

        obj = HelpArticle.objects.create(**defaults)
        return obj, True

    def _upsert_context(self, spec, article, *, refresh):
        role = spec.get("role", Audience.ALL)
        route_name = str(spec.get("route_name") or "").strip()
        path_pattern = str(spec.get("path_pattern") or "").strip()
        if not route_name and not path_pattern:
            raise CommandError(
                f"Context for {spec.get('article_key')!r} has neither route_name nor path_pattern."
            )
        lookup = (
            {"role": role, "route_name": route_name}
            if route_name
            else {"role": role, "path_pattern": path_pattern}
        )
        defaults = {
            "page_key": spec.get("page_key") or article.key,
            "article": article,
            "route_name": route_name,
            "path_pattern": path_pattern,
            "quick_prompts": spec.get("quick_prompts", []),
            "priority": int(spec.get("priority", 100)),
            "is_active": True,
        }
        obj, created = HelpPageContext.objects.get_or_create(**lookup, defaults=defaults)
        # Context is UX metadata, not a knowledge source. Keeping it in sync with
        # the curated fixture is safe when refreshing; otherwise preserve Admin edits.
        if not created and refresh:
            self._assign_and_save(obj, defaults)
        return obj, created

    @transaction.atomic
    def handle(self, *args, **options):
        data = self._load_data()
        workflow_actions = self._load_workflow_actions()
        refresh = bool(options["refresh_defaults"])

        category_map = {}
        created_categories = 0
        for spec in data["categories"]:
            category, created = self._upsert_category(spec, refresh=refresh)
            category_map[category.slug] = category
            created_categories += int(created)

        article_map = {}
        created_articles = 0
        for index, spec in enumerate(data["articles"], start=1):
            category = category_map.get(spec.get("category"))
            if category is None:
                raise CommandError(
                    f"Unknown category {spec.get('category')!r} for article {spec.get('key')!r}."
                )
            article, created = self._upsert_article(
                spec,
                category,
                refresh=refresh,
                sort_order=index * 10,
                workflow_actions=workflow_actions,
            )
            article_map[article.key] = article
            created_articles += int(created)

        created_contexts = 0
        for spec in data["contexts"]:
            article = article_map.get(spec.get("article_key"))
            if article is None:
                # It may be an existing published article preserved by Admin.
                article = HelpArticle.objects.filter(key=spec.get("article_key")).first()
            if article is None:
                raise CommandError(f"Context article not found: {spec.get('article_key')!r}")
            _, created = self._upsert_context(spec, article, refresh=refresh)
            created_contexts += int(created)

        # Legal text is never invented by this seed. Legacy rows keep redirecting
        # to the authoritative pages until real reviewed documents are entered in Admin.
        for slug, title, url_name in (
            ("privacy", "حریم خصوصی", "accounts:privacy_policy"),
            ("terms", "شرایط استفاده", "accounts:terms_of_use"),
            ("messaging-privacy", "حریم خصوصی پیام‌رسان‌ها", "messaging:privacy"),
        ):
            HelpLegalDocument.objects.get_or_create(
                slug=slug,
                version="legacy",
                defaults={
                    "title": title,
                    "summary": "",
                    "content": "",
                    "audience": Audience.ALL,
                    "status": HelpLegalDocument.Status.PUBLISHED,
                    "is_current": True,
                    "legacy_url_name": url_name,
                },
            )

        mode = "refresh-defaults" if refresh else "preserve-published-admin-edits"
        self.stdout.write(
            self.style.SUCCESS(
                "Help docs seed complete "
                f"({mode}, version={data.get('version', 'unknown')}): "
                f"{len(category_map)} categories ({created_categories} new), "
                f"{len(article_map)} articles ({created_articles} new), "
                f"{len(data['contexts'])} contexts ({created_contexts} new)."
            )
        )
