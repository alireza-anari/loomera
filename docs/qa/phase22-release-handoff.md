# Phase 22 — Release Handoff

## Release status

This package is a QA and handoff package, not a product-code patch. It is safe to add to the repository as documentation/tools. Product release readiness still depends on running the visual and functional checklist in a real environment.

## Required pre-release commands

```bash
python tools/apply_phase21_localization_patch.py
npm ci
npm run build
python manage.py check
python tools/run_phase22_static_qa.py --json docs/qa/phase22-static-qa-results.local.json
```

## Recommended manual QA order

1. Apply Phase 01–21 patches in order.
2. Run Phase 21 localization script and confirm it is idempotent.
3. Build CSS through the normal pipeline.
4. Run Django check and smoke tests.
5. Seed or prepare data for customer and partner states.
6. Capture screenshots using `phase22-screenshot-matrix.md`.
7. Complete `phase22-regression-checklist.md`.
8. Review residual English/localization hits from static QA.
9. Approve release only if no P0/P1 blockers remain.

## Blocker definitions

| Priority | Meaning |
|---|---|
| P0 | route crash, auth/booking/payment break, missing CTA for core flow, broken mobile nav/sticky CTA |
| P1 | major visual regression, unreadable RTL/currency/status, wrong role navigation |
| P2 | polish issue, spacing inconsistency, minor copy issue |
| P3 | nice-to-have enhancement |

## Known sandbox limitations

- No running Django server/database was available.
- No browser screenshot capture or pixel diff could be executed in the sandbox.
- Full Phase 01–20 patch chain was not available as separate applyable artifacts in this sandbox session; the QA package is designed to be run against the real current repo.
