# Loomera Help Knowledge Base v1.4 — build audit

Build-time checks completed in the artifact environment:

- production_docs.json parses successfully
- 12 categories
- 75 articles
- 34 page-context prompt mappings
- 51 retrieval benchmark cases declared
- unique article keys and slugs
- every article has internal source_refs, summary and keywords
- all Help Center Python files compile successfully
- help_assistant.js passes `node --check`
- fixture-level chunk-score simulation using the production retrieval weights ranked the expected article first for all 51 benchmark questions

The final Django/database verification must still be run after seeding on the Loomera project:

```powershell
python manage.py seed_help_center --refresh-defaults
python manage.py rebuild_help_chunks
python manage.py audit_help_coverage
python manage.py test apps.help_center.tests
python manage.py check
```
