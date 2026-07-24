# Loomera Docs / Content Integration Audit — Phase 4

## Canonical source of truth
- Brand/content/CRM/marketing/onboarding/media assets: `files.zip`
- Runtime code/source: `loomera.zip`
- Current repo docs: `docs/`

## Files refreshed or added
- `docs/README.md`
- `docs/brand/loomera-mini-brand-guideline.md`
- `docs/brand/loomera-brand-qa-pass-summary.md`
- `docs/brand/loomera-brand-qa-issue-log.csv`
- `docs/content/loomera-core-copy-pack.md`
- `docs/content/loomera-microcopy-system.md`
- `docs/content/loomera-cta-state-message-library-fa.md`
- `docs/design-system/*` canonical handoff docs and manifests
- `docs/crm/source/*`
- `docs/email/*`
- `docs/notifications/README.md`
- `docs/marketing/*`
- `docs/onboarding/*`
- `docs/media/*`
- `templates/email/loomera_email_base_rtl.html`
- `templates/email/loomera_minimal_transactional.html`
- `templates/notifications/loomera_inapp_notification.txt`

## Deprecated / duplicate source notes
- `loomera-placeholder-set(1).md` is treated as duplicate and is not imported.
- `loomera-category-artwork-icons-final` is older than `loomera-category-artwork-icons-approved-package`; approved package is canonical.
- Partner onboarding has multiple HTML/print/share variants; all HTML source variants are retained under `docs/onboarding/source-html/`, while binary exports are mapped for manual transfer only.
- Launch Hero Banner asset is missing. Social launch template exists but is not treated as canonical hero banner.

## Legacy copy policy
Human-facing docs should use Loomera only. Legacy names can remain only inside migration/audit/diff files or compatibility notes where they describe old keys/routes that must stay functional.
