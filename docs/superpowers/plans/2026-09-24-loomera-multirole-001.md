# LOOMERA-MULTIROLE-001 Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for bounded implementation tasks and independent review. Follow the phases in order; run focused tests at each gate and the full suite last.

**Goal:** One mobile identity can book as a customer, have a stylist profile with independent memberships, and manage several salons without granting any new permission through workspace selection.

**Architecture:** Preserve CustomUser, Customer, Stylist, SalonManager, Salon.salon_manager, SalonMembership, and StaffDashboardPermission. Centralize capabilities and authorization, add safe role attachment and an additive persisted workspace preference, then adapt existing web and integration entry points.

**Tech Stack:** Django 5.2.17, Python 3.13.14; local isolated SpatiaLite tests, existing templates and JavaScript.

**Spec:** User's approved implementation instructions, `C:/Users/Hanie/.codex/attachments/1851eeb4-cfe5-4a62-a6e2-01a08231add5/Pasted text.txt`; preceding audit, `C:/Users/Hanie/AppData/Local/Temp/loomera-multirole-001-audit-20260924.md`.

## Global Constraints

- Work only in `feature/loomera-multirole-001` in the existing checkout, as explicitly requested.
- Do not alter main, staging, beta-v1.0.0, test_media, production databases, or historical financial relations.
- No push, merge, PR or deployment. Import only PR119's content commit; stop on conflict.
- No generic role redesign, no multiple managers per salon, no User merge or broad customer backfill.
- Keep mobile/password login and the three signup entry points. Never change an existing identity while attaching a role.
- Run tests in a sanitized temporary mirror, not against the checkout's .env, media or database.
- User explicitly authorized all phases without additional confirmation, overriding skill handoff approval defaults.

## Review Focus

- A stale role or salon selection must not resurrect revoked membership or authorize a foreign salon.
- A role intent for a different mobile must not attach a profile to the authenticated account.
- Existing passwords, account activity, marketing preferences and historical records must survive every failure path.
- A form open in tab A must retain its own salon even after tab B changes workspace.
- The first multi-professional login must still show a chooser even if a single-workspace preference already exists.

## Phase 0: PR119 and test isolation

- [x] Record branch, status and starting SHA `4ee3f982de1e091c36ee8ca342c216d2fac9a61b`.
- [x] Inspect PR119 diff and cherry-pick content commit `4c5f2da`; resulting commit `107ea89` has the same tree as origin/main and no conflicts.
- [ ] Run `apps.stylists.test_beta_specialist_visibility` plus nearby booking/readiness regressions in isolated mirror.

## Phase 1: Core services

Files: new `apps/accounts/services/access.py`, `workspaces.py`, `test_multirole_services.py`.

Interfaces: `capabilities_for(user)` returns available capability names; `ensure_customer(user)` lazily returns the existing/new Customer without altering existing preferences; `managed_salons(user)` returns owner-scoped queryset; `resolve_manager_salon(user, salon_id=None)` returns an owned Salon or None and rejects foreign/malformed IDs and ambiguous multiple salons; `resolve_stylist_membership(user, salon_id)` returns only an active membership for that user; `available_workspaces(user)` returns customer, stylist and each manager salon (manager onboarding if no salon).

- [ ] Write real database tests for customer-only, stylist, one/two manager salons, manager+stylist, foreign ID, paused/ended membership, inactive user and idempotent Customer creation.
- [ ] Run RED; implement services; run GREEN and focused regressions.
- [ ] Review service permissions before adapting views.

## Phase 2: Customer-for-all

Files: accounts/views.py, orders/views.py, API customer entry points, new test_multirole_customer.py.

- [ ] Add integration tests for all provider combinations reaching personal booking and preserving customer preferences; observe RED.
- [ ] Use ensure_customer at authorized customer entry points, remove provider exclusion in the customer guard, preserve existing profiles and marketing consent.
- [ ] Run tests and nearby customer/booking regressions; review.

## Phase 3: Safe add-role and second-salon creation

Files: accounts/services/role_intents.py, accounts/forms.py/views.py/urls.py, dashboards onboarding helper, test_multirole_role_flows.py.

- [ ] Add tests for existing mobile through each signup, identity preservation, session-bound/expiring intent, wrong-account login, repeated attachment, and new salon without replacing the existing salon; observe RED.
- [ ] Keep new-user signup behavior; authenticate existing users through existing login, bind validated intent to user/mobile/role, create missing profile atomically. Never invoke existing-user signup deactivation/delete logic.
- [ ] Provide authenticated add-role/add-salon entry points without creating memberships automatically.
- [ ] Run security and onboarding regressions; review.

## Phase 4: Persistent workspace and login routing

Files: accounts/models.py, additive migration, services/workspaces.py, accounts workspace views/urls, auth redirects and test_multirole_workspaces.py.

- [ ] Add preference with user OneToOne, workspace kind, nullable salon FK and explicit multi-workspace-choice marker.
- [ ] Test first chooser, stored preference after logout, revocation, single remaining destination, tampering and safe next/deep links; observe RED before routing implementation.
- [ ] Resolve safe continuation before ordinary routing, persist explicit choices, reauthorize every switch. Customer is always selectable but does not itself force chooser.
- [ ] Keep stylist as the user's single stylist workspace; its existing per-salon membership selector stays independently authorized, as specified by the current Workspace contract.
- [ ] Generate/test only additive preference migration; run auth regressions and review.

## Phase 5: Explicit manager salon scope

Files: dashboards manager views/layout/finance/content/quick links, search views, scope middleware/helper and common form integration, test_multirole_manager_scope.py.

- [ ] Tests for A+B manager, read/write A and B, foreign C, URL/session/POST mismatch and simultaneous tabs; observe RED.
- [ ] Replace ambiguous manager-only get/first queries with shared owner-scoped resolver. An object target or explicit salon ID is authoritative input only after ownership verification.
- [ ] Preserve GET selection convenience; require each multi-salon mutation/form to carry its own target rather than rely on mutable session preference.
- [ ] Run manager, finance, report, onboarding and quick-link regressions; review all ambiguous sites.

## Phase 6: Stylist compatibility

Files: stylist context and invitation handling, test_multirole_memberships.py.

- [ ] Test no membership side effects of manager/stylist role addition, own-salon membership acceptance, revoked/foreign/expired invitations, private resume booking and privacy.
- [ ] Preserve legacy valid memberships without reactivating ended/paused records; validate expiry and acceptance transaction.
- [ ] Run focused membership, schedule and PR119 regressions; review.

## Phase 7: Existing UI

Files: workspace chooser template, existing account/signup templates, shell headers/sidebar, workspace context and common form target integration.

- [ ] Add render/navigation tests for current workspace, customer access and add-role/salon links.
- [ ] Make minimal markup changes; retain the three signup entry points and current login form.
- [ ] Run shell, dashboard and customer UX regressions. Update legacy expectations only for the expressly approved new behavior, recording the reason.

## Phase 8: API, Lumi and bots

Files: API auth serializer; help_center context/conversation/action services; lumi/context; messaging role/bot handlers; focused integration tests.

- [ ] Test all API role flags, server-authorized Lumi role/salon scope, conversation isolation/revocation, ambiguous manager bot callbacks and foreign callback rejection; observe RED.
- [ ] Reuse shared capabilities; correct stylist accessor; preserve server authorization and force selector for ambiguous bot scope.
- [ ] Run API/help_center/messaging/bot permission regressions; review.

## Final verification

- [ ] `git diff --check`; migration drift check in isolated settings.
- [ ] Dedicated multirole suite; auth/accounts suite; salon/dashboard/stylist/booking/order/payment/API/help_center/messaging suites; then full suite.
- [ ] Independent whole-change review and fixes verified by relevant tests. Never weaken/skip tests to pass.
- [ ] Confirm main/staging/tag and existing test_media unchanged; report exact PASS/FAIL/ERROR/SKIP, changed files/migration, SHAs, manual tests and remaining risks.

## Progress ledger

Phase 0 complete: cherry-pick successful, `4ee3f98..107ea89`, no conflicts. PR119 regression labels (specialist visibility, salon booking readiness, public booking API security): 17 PASS, 0 FAIL/ERROR/SKIP, isolated run `run-9h3aasz_`. Main and beta tag unchanged. External harness preloads OSGeo GDAL before Python SQLite to avoid a Windows DLL collision; no application changes were needed for the harness.

Phase 1: shared core contract tests written; RED run pending. All later implementation phases pending. Read-only Phase 5 inventory and Phase 2 booking preparation delegated separately.

Preflight: Phases 1–8 share service interfaces sequentially; phases 2–5 share accounts/views and dashboards/views, so no concurrent edits to those files. Tests use real authorization/query boundaries. User's latest contract fixes one reference manager per salon and authorizes additive preference migration. Work stays on the named feature branch; test isolation is external and never copies test_media or credentials.
