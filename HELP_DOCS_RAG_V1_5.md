# Help Docs RAG v1.5

No database migration is added.

- 96 production articles
- 53 contextual prompt mappings
- category pages and article counts
- topic/type filters for search
- troubleshooting section on Help Center home
- article breadcrumbs and direct Ask Assistant actions
- explicit docs for unfinished Products/Stocktakes capabilities
- new onboarding, services, content, reports, stylist and customer discovery docs

Apply:

```powershell
python manage.py seed_help_center --refresh-defaults
python manage.py rebuild_help_chunks
python manage.py audit_help_coverage
python manage.py test apps.help_center.tests
python manage.py check
```

Then run:

```powershell
python manage.py runserver
```

QA:
- /help/
- /help/category/team/
- /help/category/getting-started/
- /help/search/?q=نوبت
- /help/search/?type=troubleshooting
- open an article and click «از دستیار بپرس»
