# Help Docs RAG v1.5.1 — category seed fix

v1.5 introduced articles in two new documentation categories but the category
records themselves were missing from `production_docs.json`.

Added:
- `manager` → مدیریت مجموعه
- `content` → محتوا و انتشار

Also added a fixture regression test so every article category must exist.

No migration is required.

If the failed v1.5 seed was run inside the command's transaction, it rolled back
and can simply be rerun after replacing this file.

```powershell
python manage.py seed_help_center --refresh-defaults
python manage.py rebuild_help_chunks
python manage.py audit_help_coverage
python manage.py test apps.help_center.tests
python manage.py check
```
