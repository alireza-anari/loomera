# Phase 22 — Visual QA, Screenshot Diff & Final Alignment

## Scope

Phase 22 is a release-readiness and QA handoff phase. It should not change product UI, backend logic, routes, URLconf, models, migrations, payment logic, booking logic, auth/session logic, dashboard query builders, or business behavior.

## Important execution note

The available sandbox did not include a running Django application, database fixtures, browser screenshots, or all previous phase patch ZIPs as independently applyable artifacts. Therefore, this package contains:

- static QA results from the available uploaded `loomera (2).zip` source and Phase 21 patch;
- screenshot matrix and diff plan to run in the real project environment;
- release regression checklist;
- final alignment criteria for customer mobile, partner mobile, desktop public, and desktop partner;
- a local static QA script.

No product source file is modified by Phase 22.

## Source and reference inventory

| Asset | Role | Count / notes |
|---|---:|---|
| `loomera (2).zip` | main uploaded source | 1422 entries, 212 HTML files |
| `files.zip` | brand/assets/docs | 752 entries, 146 images, 5 PDFs |
| `fresha_android_reference_renamed.zip` | mobile benchmark | 359 entries, 357 images |
| `fresha_desktop_reference_renamed.zip` | desktop benchmark | 60 entries, 58 images |
| `loomera_phase21_rtl_persian_localization_patch.zip` | Phase 21 localization patch | idempotent script + docs |

## Phase 21 pre-check

The Phase 21 patch script was present and the selected source contained the Phase 21 CSS marker and changelog. Running the script through Python import on the selected working tree returned `Changed files: 0`, meaning it was idempotent for the selected extracted files.

## Static QA summary

| Check | Result |
|---|---:|
| Template files scanned | 197 |
| Python files scanned | 95 |
| Template tag balance | pass, 0 issues found |
| CSS brace balance | pass for `loomera-brand.css` and `loomera-typography.css` |
| Tailwind config syntax | pass via `node --check tailwind.config.js` |
| `Fresha` visible/source term scan | 0 hits in scanned templates/CSS |
| `Salonify/salonify/SALONIFY` visible/source term scan | 0 hits in scanned templates/CSS |
| Generic English leftovers | small residual list; requires Phase 22 manual copy QA |
| Django check | not executed; Django was not installed in sandbox |
| Browser screenshot diff | not executed; no running app/browser baseline in sandbox |

## Residual localization items requiring visual QA

Static scan still found a small number of English/half-English terms in the selected uploaded source. These may be developer-facing text, CSS comments, route labels, or visible UI depending on runtime.

Priority for manual review:

1. `templates/accounts/delete_account.html` — contains `Delete`
2. `templates/components/booking_bar.html` — contains `Booking`
3. `templates/payments/wallet_charge.html` — contains `Back`, `Submit`, `mock`
4. `templates/main/support/success.html` — contains `Back`
5. Partner templates with `workspace`, `preview`, `planner`, `catalog`, `readiness`, `backend`, `deterministic`

Do not replace these blindly in Phase 22 unless verified as visible end-user copy. If they are code comments, CSS tokens, data attributes, JS hooks, or internal naming, leave them unchanged.

## Visual alignment gates

| Product area | Required alignment |
|---|---|
| Customer mobile | app-like home, search, venue, booking, checkout, account; bottom nav and sticky CTA safe |
| Partner mobile | app-like dashboard, calendar, clients, finance, marketing, reports; operational cards and quick actions |
| Desktop public | website-like homepage/search/profile/auth; wide sections and clean hierarchy |
| Desktop partner | web-app/dashboard-like; sidebar/topbar, tables, filters and reports readable |
| RTL/Persian | natural Persian copy, RTL layout, no broken truncation, safe numeric/date/currency display |
| Iran market | تومان, Iranian phone labels, cities/services, no fake Jalali conversion |
| Brand | Loomera calm/premium/trusted identity retained |

## Screenshot diff protocol

Run screenshot capture only in a local/staging environment after all Phase 01–21 patches have been applied, database fixtures are loaded, and login states are available.

Recommended breakpoints:

- Mobile customer: 390 × 844
- Mobile partner: 390 × 844
- Tablet smoke: 768 × 1024
- Desktop public: 1440 × 1024
- Desktop partner: 1440 × 1024

Diff thresholds:

- 0–2% pixel difference for stable component pages after final alignment.
- 2–5% acceptable for content-dependent cards/tables.
- >5% requires visual review.
- Any layout overflow, broken RTL, hidden CTA, overlapped bottom nav, or unreadable status badge is a release blocker regardless of percentage.

## Release decision

Phase 22 should be marked release-ready only after:

- all critical routes render with no template/runtime error;
- screenshots pass the matrix in `phase22-screenshot-matrix.md`;
- regression checklist in `phase22-regression-checklist.md` is completed;
- Phase 21 localization spot-check confirms visible Persian copy is acceptable;
- no backend or route changes are included in the release patch.
