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


CATEGORY_AUDIENCE = {
    "manager": Audience.MANAGER,
    "stylist": Audience.STYLIST,
    "customer": Audience.CUSTOMER,
}


class Command(BaseCommand):
    help = "Seed/upgrade Help Center CMS from the fallback knowledge registry."

    @transaction.atomic
    def handle(self, *args, **options):
        category_map = {}
        for index, (slug, data) in enumerate(knowledge.CATEGORIES.items(), start=1):
            category, _ = HelpCategory.objects.update_or_create(
                slug=slug,
                defaults={
                    "title": data["title"],
                    "description": data["description"],
                    "icon": data["icon"],
                    "audience": CATEGORY_AUDIENCE.get(slug, Audience.ALL),
                    "sort_order": index * 10,
                    "is_published": True,
                },
            )
            category_map[slug] = category

        article_map = {}
        for index, item in enumerate(knowledge.ARTICLES, start=1):
            category = category_map.get(item.category)
            if category is None:
                category, _ = HelpCategory.objects.get_or_create(
                    slug=item.category,
                    defaults={
                        "title": item.category,
                        "sort_order": 500,
                        "is_published": True,
                    },
                )
                category_map[item.category] = category

            article, _ = HelpArticle.objects.update_or_create(
                key=item.key,
                defaults={
                    "category": category,
                    "slug": item.slug,
                    "title": item.title,
                    "audience": item.role if item.role in Audience.values else Audience.ALL,
                    "summary": item.summary,
                    "steps": [
                        {"title": title, "body": body}
                        for title, body in item.steps
                    ],
                    "tips": list(item.tips),
                    "keywords": " ".join(item.keywords),
                    "sort_order": index * 10,
                    "is_published": True,
                },
            )
            article_map[item.key] = article

        for index, (pattern, page_key) in enumerate(knowledge.ROUTE_RULES, start=1):
            article = article_map.get(page_key)
            if article is None:
                continue
            role = (
                article.audience
                if article.audience in {Audience.CUSTOMER, Audience.MANAGER, Audience.STYLIST}
                else Audience.ALL
            )
            HelpPageContext.objects.update_or_create(
                role=role,
                path_pattern=pattern.pattern,
                defaults={
                    "page_key": page_key,
                    "article": article,
                    "quick_prompts": [
                        step.get("title", "")
                        for step in article.steps[:3]
                        if isinstance(step, dict) and step.get("title")
                    ],
                    "priority": 1000 - min(index, 900),
                    "is_active": True,
                },
            )

        legal_seed = (
            ("privacy", "حریم خصوصی", "accounts:privacy_policy"),
            ("terms", "شرایط استفاده", "accounts:terms_of_use"),
            ("messaging-privacy", "حریم خصوصی پیام‌رسان‌ها", "messaging:privacy"),
        )
        for slug, title, url_name in legal_seed:
            HelpLegalDocument.objects.update_or_create(
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

        self.stdout.write(
            self.style.SUCCESS(
                f"Help Center seeded: {len(category_map)} categories, "
                f"{len(article_map)} articles, {len(knowledge.ROUTE_RULES)} route rules."
            )
        )
