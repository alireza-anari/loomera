# Phase 22 — Visual QA, Screenshot Diff & Final Alignment

## Scope

Phase 22 adds final QA documentation, a screenshot matrix, a regression checklist, a release handoff, and a local static QA helper. It does not modify product templates, CSS, routes, views, models, migrations, backend logic, or assets.

## Artifacts

- `docs/qa/phase22-visual-qa-final-report.md`
- `docs/qa/phase22-screenshot-matrix.md`
- `docs/qa/phase22-regression-checklist.md`
- `docs/qa/phase22-release-handoff.md`
- `docs/qa/phase22-static-qa-results.json`
- `tools/run_phase22_static_qa.py`

## QA performed in sandbox

- Selected source extraction from `loomera (2).zip`
- Phase 21 idempotency check through direct Python execution
- Template tag balance scan on 197 HTML templates
- CSS brace balance scan on `loomera-brand.css` and `loomera-typography.css`
- Tailwind config syntax check with `node --check`
- Residual English/legacy term scan in templates/CSS
- Reference inventory count for Fresha mobile/desktop reference ZIPs and brand ZIP

## QA not performed in sandbox

- Browser screenshot capture
- Pixel screenshot diff
- Django runtime route rendering
- Database-backed booking/payment/auth/dashboard smoke tests

These must be run in staging/local with real fixtures.
