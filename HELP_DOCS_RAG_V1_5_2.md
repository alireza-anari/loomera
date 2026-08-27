# Help Docs RAG v1.5.2 — retrieval precision hotfix

No database migration.

Fixes:
- phrase-level weighting for curated multi-word aliases
- salon opening hours separated from stylist shift synonyms
- small exact-role tie-breaker for manager/stylist operational docs
- ambiguous metadata cleaned for existing-service vs request-new-service
- discriminative operational intents such as cancel, connect/disconnect and amount limits
- regression tests for retrieval scoring

Full fixture benchmark simulation:
- benchmarks: 67
- collisions after hotfix: 0

Apply:

```powershell
python manage.py seed_help_center --refresh-defaults
python manage.py rebuild_help_chunks
python manage.py audit_help_coverage
python manage.py test apps.help_center.tests
python manage.py check
```
