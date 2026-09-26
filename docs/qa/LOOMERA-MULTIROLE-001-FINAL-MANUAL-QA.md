# LOOMERA-MULTIROLE-001 — FINAL MANUAL QA

Date: 2026-09-25. Final status: **MANUAL_QA_FAILED**.

## 1. Executive Summary

Real Chrome manual UI/E2E QA, supplemented by live local HTTP/API smoke and an offline bot-menu simulation. The 124-row matrix contains **104 PASS, 10 FAIL, 3 BLOCKED_BY_ENVIRONMENT, 6 INTENTIONALLY_BLOCKED and 1 NOT_APPLICABLE**. The 114 PASS/FAIL rows are executed functional checks; intentional blocks are counted separately. A row may combine closely related requests and is not a raw click/request count.

Four distinct product issues: **0 Critical, 2 High, 2 Medium**. Failures affect scoped-manager navigation/Lumi, service creation, multirole customer appointments/booking completion, and search-click recording. No cross-role or cross-salon business-data exposure was observed in the exercised checks. This is not release approval.

No source fixes, migrations, automated test runs or git mutations were performed. Only this QA report was written in the project. Disposable local records were cleaned up; original uncommitted paths remain. There is a QA execution limitation: the local map proxy made upstream map reads despite direct external-browser interception; see sections 2 and 13. No real messaging, payment or settlement was performed.

## 2. Environment

- Windows; Python 3.13.14: `E:\Projects\Loomera_BetaBugfix_py313_venv\Scripts\python.exe`; Django 5.2.17.
- Explicit `loomera.settings.development`, process `DEBUG=True`, GDAL `C:\OSGeo4W\bin\gdal311.dll` preloaded, `-B`; accounts workspace migration 0004 already applied.
- PostgreSQL/PostGIS `loomera_local`, localhost:5432. Actual DB server address `::1` verified by SELECT. No staging/production DB connection.
- Django listened on `http://127.0.0.1:8766`, no reloader. Messaging/outbound/Bale/Telegram/SMS/external AI disabled in process, email/cache locmem; pay-in-salon used. No .env edits and no secrets copied into this report.
- Native browser integration unavailable. Existing Chrome controlled through localhost DevTools, using a disposable profile and an in-memory adapter. Browser requests to non-local URLs were intercepted. Screenshots inspected inline in the tool transcript; no screenshot files created under the report-only file constraint.
- Runtime/DevTools connections were interrupted and reconnected during the run. Closed control sockets caused tool timeouts; these were not established as product hangs. Earlier raw network captures were not retained across all restarts.
- **QA-RUN-001 — local-only isolation incomplete:** browser interception did not cover server-side outbound requests. Search loaded local `/search/map-tiles/...` responses with HTTP 200; map configuration was enabled and the proxy implementation obtains them upstream. Thus the claim that every request stayed local would be incorrect. The map page was closed on discovery, followed by shutdown of the QA server/browser. This is a QA execution constraint breach, separate from the four product bugs. No key or upstream authorization header is reproduced. Map-provider behavior is not counted as a PASS.
- The local server, Chrome QA browser and in-memory adapter were stopped after testing.

## 3. Current Branch

`feature/loomera-multirole-001` throughout. No branch or git history changes.

## 4. Git status before QA

Initial recorded `git status --short`:

```text
 M apps/accounts/customer_communication_views.py
 M apps/accounts/models.py
 M apps/accounts/test_customer_notification_actions_security.py
 M apps/accounts/test_customer_notifications_summary_security.py
 M apps/accounts/test_customer_profile_image_security.py
 M apps/accounts/test_notification_settings_security.py
 M apps/accounts/test_stage1_auth_access.py
 M apps/accounts/urls.py
 M apps/accounts/views.py
 M apps/api/tests/test_api_v1_booking_confirm.py
 M apps/api/tests/test_api_v1_booking_draft_summary.py
 M apps/api/tests/test_api_v1_booking_draft_validation.py
 M apps/api/tests/test_api_v1_my_appointments.py
 M apps/api/v1/auth_serializers.py
 M apps/api/v1/booking_views.py
 M apps/api/v1/my_appointments_views.py
 M apps/bale_bot/menus.py
 M apps/bale_bot/tests.py
 M apps/comments_scores_favories/test_favorite_toggle_security.py
 M apps/comments_scores_favories/views.py
 M apps/dashboards/layout.py
 M apps/dashboards/manager_settings_views.py
 M apps/dashboards/urls.py
 M apps/dashboards/views.py
 M apps/help_center/action_views.py
 M apps/help_center/actions/manager_operations.py
 M apps/help_center/actions/router.py
 M apps/help_center/services.py
 M apps/help_center/views.py
 M apps/messaging/manager_bot.py
 M apps/messaging/promotion_bot.py
 M apps/messaging/roles.py
 M apps/messaging/test_bale_operator_final.py
 M apps/messaging/test_bale_operator_ux.py
 M apps/messaging/test_bale_operator_ux_phase3.py
 M apps/messaging/tests.py
 M apps/search/views.py
 M loomera/settings/base.py
 M static/js/components/help_assistant.js
 M templates/accounts/customer_panel.html
 M templates/base.html
 M templates/dashboard_template.html
 M templates/partials/dashboard/navbar.html
 M templates/partials/dashboard/sidebar.html
 M templates/partials/shell/desktop_site_header.html
 M templates/partials/shell/mobile_app_header.html
?? apps/accounts/migrations/0004_userworkspacepreference.py
?? apps/accounts/services/access.py
?? apps/accounts/services/role_intents.py
?? apps/accounts/services/workspaces.py
?? apps/accounts/test_multirole_customer.py
?? apps/accounts/test_multirole_role_flows.py
?? apps/accounts/test_multirole_services.py
?? apps/accounts/test_multirole_ui.py
?? apps/accounts/test_multirole_workspaces.py
?? apps/api/tests/test_multirole_auth_roles.py
?? apps/dashboards/multirole_finance_preview.py
?? apps/dashboards/multirole_manager_customers.py
?? apps/dashboards/multirole_manager_views.py
?? apps/dashboards/multirole_manual_booking.py
?? apps/dashboards/multirole_manual_booking_cancel.py
?? apps/dashboards/multirole_scope_middleware.py
?? apps/dashboards/multirole_settlement_ledger.py
?? apps/dashboards/test_multirole_manager_booking_cancel.py
?? apps/dashboards/test_multirole_manager_customers.py
?? apps/dashboards/test_multirole_manager_finance_readonly.py
?? apps/dashboards/test_multirole_manager_manual_booking.py
?? apps/dashboards/test_multirole_manager_operations.py
?? apps/dashboards/test_multirole_manager_scope.py
?? apps/dashboards/test_multirole_manager_service_forms.py
?? apps/dashboards/test_multirole_manager_settlement_ledger.py
?? apps/dashboards/test_multirole_manager_team_details.py
?? apps/dashboards/test_multirole_manager_team_invites.py
?? apps/dashboards/test_multirole_membership_compat.py
?? apps/help_center/multirole_scope.py
?? apps/help_center/tests/test_multirole_conversation_scope.py
?? apps/messaging/test_multirole_channel_scope.py
?? apps/search/test_multirole_manager_customer_scope.py
?? docs/superpowers/
?? static/css/components/workspace_switcher.css
?? static/css/pages/workspace_choose.css
?? templates/accounts/add_role.html
?? templates/accounts/workspace_choose.html
?? templates/dashboards/multirole_manager_bookings.html
?? templates/dashboards/multirole_manager_customers.html
?? templates/dashboards/multirole_manager_finance_preview.html
?? templates/dashboards/multirole_manager_manual_booking.html
?? templates/dashboards/multirole_manager_manual_booking_cancel.html
?? templates/dashboards/multirole_manager_salon_overview.html
?? templates/dashboards/multirole_manager_service_form.html
?? templates/dashboards/multirole_manager_services.html
?? templates/dashboards/multirole_manager_settlement_ledger.html
?? templates/dashboards/multirole_manager_team.html
?? templates/dashboards/multirole_manager_team_member_form.html
?? templates/partials/shell/workspace_switcher.html
?? test_media/
```

## 5. Manual test coverage

PASS covers only the stated observation. A page-open smoke does not imply all CRUD paths passed. API rows, SEC-SINGLE rows, Lumi HTTP scope rows and SEARCH-CLICK-HTTP are live HTTP checks, not UI interactions. BOT-OFFLINE calls local menu builders without transport. ORM use was fixture setup, independent corroboration or cleanup, never a substitute for a UI PASS.

| ID | Status | Observed evidence |
|---|---|---|
| AUTH-01 | PASS | Active Multi login through UI; first-login chooser at /accounts/workspaces/. |
| WS-01 | PASS | Chooser shows Customer, Stylist, owned A48/B49; excludes foreign C50. |
| CUS-01 | PASS | customerPanel shows same QA Multi identity and customer destinations. |
| UI-01 | PASS | 1440x900 customer shell/open switcher: readable RTL, active non-submit Customer, compact popover. |
| WS-02 | PASS | Customer→Stylist via navbar; correct /dashboards/stylist/ shell and same identity. |
| WS-03 | FAIL | Stylist→Manager A redirects correctly but manager navbar/sidebar/switcher absent. QA-BUG-001. |
| M-A-CUS | PASS | A customers page only CustomerA; no B customer. |
| M-B-CUS | PASS | B customers page only CustomerB; no A customer. |
| M-A-SVC | PASS | A services list only ServiceA; shared catalog row explicitly not editable. |
| M-B-SVC | PASS | B services list only ServiceB. |
| M-A-TEAM | PASS | A team lists active membership111/112. |
| M-B-TEAM | PASS | B team lists its membership113/114, no foreign C membership115. |
| TEAM-INVITE | PASS | B invite to existing Single QA account saved pending with success message; not activated; outbound disabled. |
| TEAM-EDIT | PASS | A membership111 title saved as QA Title A only with success banner. |
| M-A-FIN | PASS | A finance preview correct salon, empty wallet/settlement state, read-only. |
| M-A-LEDGER | PASS | A settlement ledger correct salon and empty read-only state. |
| M-A-ADD | FAIL | A create-service catalog select has zero options. QA-BUG-002. |
| M-B-ADD | FAIL | B create-service catalog select also empty. QA-BUG-002. |
| BOOK-M-VALIDATION | PASS | A manual booking06:00 rejected outside09–12 stylist schedule. |
| BOOK-M-CREATE | PASS | A manual booking146 saved for customer216/service49/stylist213 at2026-09-27 09:00, pay in salon. |
| BOOK-M-SCOPE | PASS | 146 present in A list, absent B; B form choices only B customer/service. |
| SEC-CUSTOMER-POST | PASS | Tampered B form customer216 rejected; generic invalid choice, no A customer name in response. |
| BOOK-M-DETAIL | PASS | 146 cancellation-confirm detail shows correct A service/date/time and unpaid-manual restriction. |
| STY-BOOK | PASS | Upcoming stylist tab and detail show146, CustomerA, A,120000 toman, unpaid pay-in-salon. |
| WS-04 | PASS | Stylist→Customer via navbar returns customerPanel without logout. |
| SEARCH-01 | PASS | Public search QA260925 shows A/B/C public results; clicked A salon link. |
| CUS-PROFILE | PASS | Profile renders same identity and immutable login number. |
| CUS-ADDRESS | PASS | Addresses page opens with empty state/add controls. |
| CUS-COMM | PASS | Customer communications opens with preferences and unavailable disabled bot connectors. |
| CUS-NOTIFY | PASS | Notifications page opens with empty state and filters. |
| CUS-WALLET | PASS | Wallet opens, zero balance, beta recharge/withdrawal explicitly unavailable. |
| CUS-SUPPORT | PASS | Support ticket list opens, empty state and create action. |
| UI-MOBILE-CUS | PASS | 390x844 customer menu contained/readable; scrollWidth390. |
| UI-KEYBOARD | PASS | Tab from open summary focuses actionable Stylist option, skips active Customer. |
| UI-TABLET | PASS | 768x1024 customer shell/menu visually inspected, readable/contained. |
| WS-05 | PASS | Customer→Manager B menu submits to scoped49 and correct B counts; shared shell issue tracked separately. |
| M-B-FIN | PASS | B finance preview correct salon, read-only empty state. |
| M-B-LEDGER | PASS | B ledger correct salon, read-only empty state. |
| M-COMM | PASS | Allowed multi-manager communications route opens; disabled bots clearly shown. |
| SEC-SALON | PASS | Foreign salon50 overview403; no C name in response. |
| SEC-SERVICE | PASS | Foreign service51 under A48 edit404. |
| SEC-TEAM | PASS | Foreign C membership115 under A48 edit404. |
| SEC-BOOKING | PASS | A booking146 cancellation under B49 returns404. |
| SEC-LEDGER | PASS | Foreign C50 ledger403. |
| LEGACY-1 | INTENTIONALLY_BLOCKED | /dashboards/ returns403 for multi-salon manager, by scope middleware design. |
| LEGACY-2 | INTENTIONALLY_BLOCKED | /dashboards/settings/ returns403 by design. |
| LEGACY-3 | INTENTIONALLY_BLOCKED | /dashboards/settings/finance/ returns403 by design. |
| LEGACY-4 | INTENTIONALLY_BLOCKED | /dashboards/SalonsCustomers/ returns403 by design. |
| BOOK-C-E2E | FAIL | Full UI salonA48/service49/stylist215/27Sep10:00/pay-in-salon confirmed but lands legacy dashboard403. QA-BUG-003. |
| CUS-APPOINTMENTS | FAIL | Explicit Customer preference still /orders/appointments/→/dashboards/403. QA-BUG-003. |
| BOOK-C-PERSIST | PASS | Manager A list shows confirmed10:00 booking; API later confirms appointment147/order146. |
| BOOK-M-CANCEL | PASS | Manager UI cancellation146 succeeds; list shows cancelled while customer147 stays confirmed. |
| AUTH-LOGOUT | PASS | Logout leaves authenticated context, redirects public salons. |
| AUTH-BAD | PASS | Wrong password remains login200 with explicit invalid credentials banner. |
| PREF-LOGIN | PASS | Saved ManagerB then logout/login restores scoped49. |
| PREF-REFRESH | PASS | Refresh scoped49 retains ManagerB. |
| WS-06 | PASS | ManagerB→Stylist via chooser works without logout; missing inline manager switcher tracked001. |
| UI-MOBILE-STY | PASS | Fresh390x844 Stylist open menu readable/contained; active Stylist highlighted. |
| STY-SCHEDULE | PASS | A stylist schedule shows A-only09–12 shift. |
| STY-PROFILE | PASS | Professional profile same identity, two memberships, A-only service; incomplete collaboration profile stated. |
| STY-SETTINGS | PASS | Stylist account/security and communication settings render. |
| STY-MEMBERSHIP-SCOPE | PASS | Active membership A→B changes schedule to B-only13–15 ServiceB. |
| LUMI-CUS | PASS | Customer chat fallback200 answers correct appointments context without external AI. |
| LUMI-STY | PASS | Stylist chat after switch starts new contextual suggestions; today's question says no appointments for B. |
| FAV-ADD | PASS | Multi in Customer mode adds A, favorite count1 and A card persists. |
| FAV-REMOVE | PASS | Same toggle removes A; favorite list count0. |
| CUS-PROFILE-VALIDATE | PASS | Invalid email rejected; native validation message observed. |
| API-AUTH-STATUS | PASS | HTTP smoke: /api/v1/auth/status/200 authenticated. |
| API-ME | PASS | HTTP smoke: /api/v1/auth/me/200 all3 capability flags true, staff/superuser false. |
| API-APPOINTMENTS | PASS | HTTP smoke: me/appointments/200 includes147; detail147 correct A48/service49/stylist215/27Sep10:00/confirmed/unpaid. |
| API-AVAILABILITY | PASS | HTTP smoke A/B availability200 with correct stylist schedules and occupied10:00 excluded. |
| API-DRAFT | PASS | HTTP smoke draft/validate and draft/summary200 valid=true; creates_order=false, locks_slot=false. |
| API-DRAFT-SCOPE | PASS | Both draft endpoints reject A+service50,B+service49,C+service49 with404 service_not_found. |
| SEC-SINGLE-SALON | PASS | HTTP smoke Single214 foreign A48 overview403, no foreign A name. |
| SEC-SINGLE-SERVICE | PASS | HTTP smoke Single214 foreign A service49 edit403, no foreign A name. |
| SEC-SINGLE-TEAM | PASS | HTTP smoke Single214 foreign A membership111 edit403, no foreign A name. |
| SEC-SINGLE-BOOK | PASS | HTTP smoke Single214 foreign A booking146 cancel GET403, no foreign A name. |
| SEC-SINGLE-LEDGER | PASS | HTTP smoke Single214 foreign A ledger403, no foreign A name. |
| CUS-PROFILE-SAVE | PASS | Saved disposable name/email via UI; persisted on later profile reload. |
| SERVICE-EDIT | PASS | Fresh B-only clone52 edited to260000 and description saved; catalog source disabled. |
| SEC-SERVICE-AB | PASS | B clone52 under A edit URL404; no260000 value disclosed. |
| FIN-LEDGER-SCOPE | PASS | A ledger shows53/54 from local orders; B remains empty even ?settlement_id=54. |
| BOT-OFFLINE | PASS | Offline menu builder213 lists all3 roles; manager selector48/49 only, no implicit salon.214 manager callbacks50;219 customer-only and foreign-role fallback safe. No transport/webhook call. |
| AUTH-INACTIVE | PASS | Inactive218 correct password did not enter authenticated workspace; remained login. |
| AUTH-SINGLE-CUS | PASS | CustomerOnly219 first login directly opens customerPanel, no professional switch options. |
| CUS-SINGLE-APPT | PASS | CustomerOnly appointments page200 with correct empty state (contrast multirole failure003). |
| SEC-CUSTOMER-MANAGER | PASS | CustomerOnly direct manager A URL403. |
| SINGLE-HOME | PASS | Single214 /dashboards/200 after completing disposable salonC onboarding fields; C50 only. |
| SINGLE-CALENDAR | PASS | C50 calendar200 with Stylist215 and empty current week, no A/B bookings. |
| SINGLE-CUSTOMERS | PASS | Legacy customer directory200 empty C-only state. |
| SINGLE-SERVICES | PASS | Service menu200 shows ServiceC51 only,120000 toman/30min. |
| SINGLE-TEAM | PASS | Team200 has Stylist215 only; excludes Multi213. |
| SINGLE-SETTINGS | PASS | Settings, manager profile and communications200; immutable phone correct; bots unavailable. |
| SINGLE-FINANCE | PASS | Legacy finance hub and scoped preview/ledger200, C-only zero balances, read-only checks. |
| LAZY-MANAGER | PASS | Removed only empty QA Customer214, then browser customerPanel200 recreated Customer214; manager profile preserved. |
| API-CONFIRM | PASS | Live HTTP draft/summary200 and pay-in-salon confirm201 created order147/appointment148 A48/service49/stylist215/2026-09-27 09:00; list/detail200 correct. |
| LUMI-SCOPE-FORGE | PASS | Live HTTP forged client C50 path/salon_id still scoped conversation to authorized ManagerA48; fallback ai=false; ORM corroborated scope metadata. |
| LUMI-SCOPE-SWITCH | PASS | Live HTTP ManagerA to B: old A conversation GET404; POST reuse200 scope_reset=true, new B49 conversation; ai=false. |
| LUMI-MULTI-UI | FAIL | Scoped managerA/B pages omit shared Lumi widget, preventing normal UI conversation there; QA-BUG-001. |
| LUMI-SINGLE-UI | PASS | Single214 dashboard Lumi UI question about today returned local fallback: no appointments; no foreign salon context. |
| UI-MOBILE-MANAGER | PASS | Fresh390x844 single-manager dashboard menu screenshot: inside viewport, scrollWidth390, C active, Customer action, no Stylist option. |
| SINGLE-TO-CUSTOMER | PASS | ManagerC mobile switcher Customer action returned customerPanel without logout. |
| SINGLE-CUS-APPTS | FAIL | After explicit Customer switch, Single214 /orders/appointments/ redirects to manager dashboard200 instead of personal appointments; broader QA-BUG-003. |
| STY-INDEPENDENT | PASS | Stylist215 login opens own dashboard; today empty, upcoming2; profile lists3 memberships and activeA service only. |
| STY-BOOK-UI | PASS | Stylist215 upcoming list includes UI147 and API148; detail147 correctly shows customer213, A,10:00–10:30,120000 toman unpaid. |
| LAZY-STYLIST | PASS | Removed only empty QA Customer215; customerPanel200 recreated it without losing Stylist/memberships. |
| STY-CUS-APPTS | FAIL | Stylist215 customerPanel My appointments redirects through manager guard to stylist dashboard200 with misleading manager-link warning; QA-BUG-003. |
| STY-A-B-BOOK-SCOPE | PASS | Stylist215 changes activeA to B: upcoming list empty and direct A appointment147 detail404. |
| STY-INACTIVE-MEMBERSHIP | PASS | Ended only QA membership114 while B active; next schedule200 fell back A, selector removedB and retainedA/C; restored fixture. |
| PREF-REVOKED | PASS | Saved ManagerB49; revoked only QA ownership49, logout/login opened chooser excludingB; directB403. Preference row remains stale49 but confers no authority. Restored owner213. |
| BROWSER-TABS | PASS | Two real Chrome tabs share QA213 login: tabA ManagerA48, tabB explicitly switches Customer; A reload still authorized A-only200, B customerPanel sameidentity. Preference is global, scoped URLs still enforce owner. |
| BROWSER-HISTORY | PASS | Customer to Stylist; CDP browser Back restored customerPanel with Customer label, Forward restored Stylist label; no logout or foreign salon data. |
| DIRECT-ROLE-PERMISSION | PASS | With Stylist preference Multi213 direct ownedA manager200, foreignC403; Customer preference similarly permits ownedA in two-tab check. Workspace is preference, not authorization. |
| SERVICE-VALIDATE | PASS | B clone52 base_price=-1 blocked by native validation; reload preserves260000. |
| M-CUSTOMER-DIRECTORY | PASS | After customer booking, A directory includes added CustomerA216 plus actual customer213; B remains its own directory. No search/detail controls exist in scoped UI. |
| M-CUSTOMER-CRUD | INTENTIONALLY_BLOCKED | Scoped customer page explicitly read-only; add customer/edit notes unavailable by current design. |
| NET-JS | PASS | Captured Runtime.exceptionThrown list empty and no HTTP500 in retained browser logs; earlier interrupted captures not retained. |
| BOT-BALE-LIVE | BLOCKED_BY_ENVIRONMENT | No real transport/token-based execution: Bale disabled for local safety; offline menu simulation covered separately. |
| BOT-TELEGRAM-LIVE | BLOCKED_BY_ENVIRONMENT | Telegram transport disabled; shared menu logic simulated, real webhook/delivery not attempted. |
| LUMI-EXTERNAL-AI | BLOCKED_BY_ENVIRONMENT | External provider intentionally disabled in local settings; tested fallback only. |
| FIN-REAL-OPS | INTENTIONALLY_BLOCKED | Real payment, withdrawal and settlement not performed per user constraint; local pay-in-salon and read-only finance covered. |
| SETTLEMENT-DETAIL-ID | NOT_APPLICABLE | Scoped ledger has no per-settlement detail route; tested foreign salon ledger and ownedB query with A settlement ID. |
| SEARCH-CLICK-HTTP | FAIL | Local authenticated form POST /search/click/ with valid A salon_id48 or B salon49 returns200 ok=true recorded=false recording_failed; DB zero clicks and server NOT NULL salon_id IntegrityError. QA-BUG-004. |
| WS-A-B-INLINE | FAIL | ManagerA to ManagerB has no inline navbar switcher on scoped pages; separate chooser is required. Both salon scopes work when explicitly chosen. QA-BUG-001. |

Coverage limits: single-manager legacy pages were exercised as page/scope smoke; the create/cancel manual-booking E2E was performed through the scoped multi-manager flow, not separately repeated through the legacy single-manager form. Address, support, notifications and communication pages were opened; every mutation on those pages was not exercised. Customer search/detail controls are absent from the current scoped read-only directory. No claim is made for unlisted CRUD operations, exhaustive keyboard/screen-reader accessibility, other browser engines, real external transport or performance/load testing. Search UI result navigation was exercised; click-recorder persistence was separately tested through form HTTP POST. No bound UI click-tracking request was observed.

## 6. Browser / viewport coverage

| Viewport | Actual inspection |
|---|---|
| Chrome 1440×900 | Customer shell/switcher; Stylist shell; single-manager dashboard; scoped manager overview and service form. RTL, labels, current-role indication, cards and key controls inspected. |
| Chrome 390×844 | Customer and Stylist switchers; fresh single-manager dashboard switcher. Readable popovers inside viewport; scrollWidth 390 in measured checks. |
| Chrome 768×1024 | Customer shell and switcher inspected visually. |
| Keyboard | Tab from customer switcher summary reaches actionable Stylist item, skips active Customer. |
| History / tabs | Back/Forward across Customer/Stylist; refresh; two simultaneous tabs for ManagerA and Customer. |

Desktop-to-mobile resizing without reload temporarily retained an open dashboard sidebar. A fresh mobile navigation rendered correctly; this was not established as a new regression. Scoped multi-manager pages fail shared-shell coverage on every inspected viewport because the shell itself is absent.

## 7. Account roles used

Disposable prefix `QA260925`:

| User ID | Capabilities / use |
|---|---|
| 213 Multi | Customer + Stylist + Manager of A/B; same login throughout switches. UI name/email edited on the disposable account. |
| 214 Single | Customer + Manager of C; no Stylist profile. Pending B invitation did not confer a Stylist role. |
| 215 Stylist | Customer + active Stylist; A/B/C memberships. |
| 216 CustomerA | Customer added by A; manual booking fixture. |
| 217 CustomerB | Customer added by B. |
| 218 Inactive | Inactive user login rejection. |
| 219 CustomerOnly | Customer-only shell/security and local click-recording smoke. |

Customer rows 214/215 were safely removed when they had no customer dependencies, then recreated by real browser customer-panel navigation. Professional identity remained intact. Credentials omitted. All these accounts were removed during cleanup.

## 8. Salons used

| Salon | Ownership / scope | Services |
|---|---|---|
| A48, qa260925-a | Multi213 | Catalog service49; stylists213/215 |
| B49, qa260925-b | Multi213 | Catalog service50; editable clone52; stylists213/215 |
| C50, qa260925-c | Single214, foreign to Multi | Catalog service51; stylist215 |

Disposable catalog groups14/15 supplied the public service taxonomy. Memberships111–115 active; invitation116 pending. Clone52 saved at260000, 40min +10min buffer. QA salon onboarding fields/opening hours were completed solely on A/B/C to distinguish onboarding gating from product errors. An existing neighborhood was referenced but never edited/deleted.

Bookings: UI manager order145/appointment146 at A09:00, then cancelled; customer UI order146/appointment147 A10:00–10:30 confirmed unpaid; API order147/appointment148 A09:00 pending unpaid. All on 2026-09-27, base price120000. Local settlement records53/54 were read-only inspected, never paid.

Only QA ownership B49 was temporarily moved to214 for revoked-preference testing and restored. Only QA membership114 was ended for inactive-membership testing and restored.

## 9. PASS scenarios

**104 PASS** rows. Principal successful observations: real role switches preserve identity/session; correct role options; authorized preference restoration and revoked-access fallback; scoped customers/services/team/finance; UI manual creation/validation/cancellation; persisted customer booking visible to manager, stylist and API; lazy customer creation for professional users; favorite/profile updates; API draft/confirm/list/detail; scoped Lumi conversation reset/forgery resistance; offline bot role/salon selection; refresh/history/two-tab behavior.

## 10. FAIL scenarios

**10 FAIL** rows map to four distinct bugs:

| Bug | Severity | Failed rows |
|---|---|---|
| QA-BUG-001 | Medium | WS-03, LUMI-MULTI-UI, WS-A-B-INLINE |
| QA-BUG-002 | High | M-A-ADD, M-B-ADD |
| QA-BUG-003 | High | BOOK-C-E2E, CUS-APPOINTMENTS, SINGLE-CUS-APPTS, STY-CUS-APPTS |
| QA-BUG-004 | Medium | SEARCH-CLICK-HTTP |

No fixes applied.

## 11. Security findings

Foreign salon/service/membership/booking/ledger URLs and foreign-customer form submission were rejected in the exercised cases. Switching preference alone did not grant authority: Multi213 could still directly open ownedA while in Customer/Stylist mode, and foreignC was forbidden. Revoked B ownership forced a safe chooser; the stale preference row remained but did not authorize access. Ended stylist membership disappeared and the active schedule fell back to A.

Lumi ignored a forged client C50 scope while A was authorized. B could not retrieve A's conversation (404); reuse reset into a new B conversation. Authorized scope metadata was verified separately in the local DB. The untrusted page_path was retained as contextual metadata but did not select authorization scope in these checks.

No cross-salon business-data leak observed. DEBUG404 exposed technical route/model labels, so these development error pages are not evidence about production error hardening. Exact settlement-detail tampering is N/A because no such scoped detail endpoint exists; ledger salon/query isolation was checked.

## 12. UI/UX findings

Customer, Stylist and single-manager shells render with readable RTL controls and usable mobile menus. Scoped multi-manager pages are standalone and lack the shared navbar/sidebar, inline switcher and Lumi entry point (001). Their forms use visibly inconsistent/default styling. Required catalog selectors have no options (002). Multirole customer appointments route away from the selected customer context (003).

Existing/media fixture 404s are listed separately below; they were not attributed to workspace-switcher regressions.

## 13. Console / Network findings

- No JavaScript exception in retained `Runtime.exceptionThrown` captures. Initial login/chooser capture also had none. This is not a claim that every console warning throughout all interrupted sessions was collected.
- No HTTP500 in retained browser responses. Search-click POST logged server IntegrityError but returned HTTP200 with recorded=false (004).
- Unexpected legitimate-flow 403: customer booking completion and customer appointments for Multi213 (003).
- Expected 403/404: foreign IDs, revoked scope, intentionally blocked legacy routes and inactive-salon detail checks.
- Two manually probed non-existent URLs, C50 `/finance/` and `/settlements/`, returned404. Correct routes `/finance/preview/` and `/finance/settlements/` returned200. These probe mistakes are not product bugs.
- `/favicon.ico`404 on standalone/error pages; `/media/salons_banner.jpg`404 for default fixture image; two existing gallery-image paths404 and existing group13 image404 on public pages. No new asset uploads were made. Missing local media is an environment/content observation, not established as a new multirole regression.
- Browser direct external-resource requests were intercepted. This did **not** prevent local map-proxy upstream reads; see QA-RUN-001 in section2. No claim of complete network isolation is made.
- No CSP/mixed-content failure was identified in the captured evidence; log continuity across restarts is limited.
- Existing khayyam pure-Python performance warning at startup is unrelated.

## 14. Blocked scenarios

**3 BLOCKED_BY_ENVIRONMENT:** Bale live transport, Telegram live transport and external-AI-provider mode. Channels/providers were disabled for local safety. Offline bot menus and Lumi fallback were tested separately. No real webhook/message was sent.

One **NOT_APPLICABLE:** scoped per-settlement detail ID, absent from the route design.

Missing multi-manager Lumi UI is a product FAIL under001, not an environment block. The empty create selector likewise remains a product FAIL, not missing fixture data.

## 15. Intentionally blocked multi-salon legacy routes

**6 INTENTIONALLY_BLOCKED** rows: four explicit legacy403 paths, current read-only customer CRUD restriction, and real financial operations prohibited by the user.

Observed legacy routes: `/dashboards/`, `/dashboards/settings/`, `/dashboards/settings/finance/`, `/dashboards/SalonsCustomers/`. The multi-salon middleware excludes legacy single-salon inference routes. These explicit manager attempts are expected blocks. Reaching the same forbidden legacy dashboard from a legitimate customer booking/appointments workflow is separately a FAIL under003.

## 16. Regression assessment

The supplied prior automated result (1956 tests, OK, skipped3) is context only; no suite was rerun. Source inspection corroborated the manual failures but did not count as a manual PASS. Scoped-manager shell/service-form issues are likely related to the new paths. The legacy professional-role redirect conflicts with newly supported customer capability. Search-click failure is confirmed now, but its historical introduction was not established. No clean historical checkout or branch comparison was performed.

## 17. Release risks

Do not treat this run as release approval. High issues block service creation and access to customer appointments after a booking that actually persists, creating confusion and repeat-submission risk. Missing inline manager navigation/Lumi violates a key requirement. Search-click analytics silently drops valid records behind HTTP200. Reverification needs the identified workflows and the explicit coverage limits in section5, with server-side map access disabled if strict local-only isolation is required.

## 18. Exact reproduction steps for every issue

Fixtures were removed after QA; recreate equivalent disposable roles/salons before reproducing. IDs below identify evidence from this run.

### QA-BUG-001— Scoped manager shell missing

- Severity: Medium. Area: Manager multi-salon UI/Workspace Switcher. Role: Customer+Stylist+Manager. Workspace: Manager A/B. Salon:A48/B49.
- Preconditions: active multi-role user owns two salons.
- URL: /dashboards/manager/salons/48/ (also49).
- Steps: log in; choose Customer; open navbar switcher; select Stylist; open navbar switcher; select management of A.
- Expected: manager navbar/sidebar and inline switcher with current salon, allowing role/salon switch without separate chooser.
- Actual: standalone overview; only links to /accounts/workspaces/ and customerPanel. No navbar, sidebar or inline switcher. Service-create form similarly standalone and unstyled. Shared Lumi absent from scoped page.
- HTTP:200. Console error: none required for reproduction; retained exception capture empty. Network error: no failing document required.
- Security impact: no exposure observed; missing navigation/context UI. Regression likelihood: high for newly added scoped templates; no old-browser baseline.
- Screenshot: viewed inline in QA tool transcript; no extra file created due report-only file rule.

### QA-BUG-002— Empty required catalog selector blocks service creation

- Severity: High. Area: scoped Manager create service. Role/workspace: Multi Manager A/B. Salon:A48/B49.
- URLs: /dashboards/manager/salons/48/services/add/ and /49/services/add/.
- Preconditions: active catalog services exist (QA services49/50/51 visible in lists); account owns A/B.
- Steps: open scoped Services; click add service; open/inspect “خدمت پایه” selector; repeat in B.
- Expected: selectable active catalog services, enabling completion of create form.
- Actual: `<select name="catalog_service" id="id_catalog_service"></select>` has zero options on both pages; no service can be selected through UI.
- HTTP:200. No JS exception needed. Network error: none required. Security impact: no exposure; workflow unavailable.
- Likely cause (source corroboration): build_form replaces the ModelChoiceField widget with fresh forms.Select after queryset choices were bound. Existing tests POST IDs directly and do not validate rendered choices. No source fix applied.
- Regression likelihood: high in new scoped service form. Screenshot: inline browser capture in QA transcript.

### QA-BUG-003 — Professional roles divert customer appointments and booking completion

- Severity: **High**. Area: Customer appointments/checkout. Roles: Multi213, Single214, Stylist215. Workspace: Customer; affected salonA booking and professional dashboard routing.
- Preconditions: active account also has Manager or Stylist profile. For the403 variant, Manager owns two salons.
- URLs: `/orders/appointments/`; UI checkout from `/orders/reservation_preview/`.
- Steps: log in to Multi213; explicitly select Customer; open My appointments. Separately complete salonA/service49/stylist215/date2026-09-27/time10:00/120000/pay-in-salon confirmation. Repeat My appointments with Single214 after Customer switch and with Stylist215 from customerPanel.
- Expected: own customer appointment list and usable customer confirmation landing, regardless of professional capability.
- Actual: Multi goes to `/dashboards/`403. Single goes to its manager dashboard200. Stylist is routed through the manager guard to the stylist dashboard200, with a misleading manager-link warning. The selected customer capability is not honored.
- Persistence: UI booking147/order146 exists and is visible in manager, stylist and API checks; the failure is the user-facing landing/appointment path, not lost data.
- HTTP: redirects (302) ending403 for Multi,200 on the wrong professional dashboard for Single/Stylist.
- Console: no JS exception needed. Network error: legitimate Multi customer flow ends403.
- Security impact: availability/context failure; no cross-role business-data exposure observed.
- Regression likelihood: high compatibility risk between legacy profile-priority guard and new multirole customer capability; historical baseline not executed.
- Screenshot: browser evidence viewed inline; no separate file.
- Relevant source: `apps/orders/views.py:2512–2519`, checkout redirect near4591, multi-salon scope middleware.

### QA-BUG-004 — Valid search-click form is not recorded

- Severity: **Medium**. Area: Search analytics. Role: CustomerOnly219. Workspace: Customer. Salons: A48 and B49.
- URL: `POST /search/click/`.
- Preconditions: authenticated local session with valid CSRF token; existing public salon48/49.
- Steps: form-POST `salon_id=48&position=1&q=QA260925&target_url=/salons/qa260925-a/`. Repeat with accepted aliases `salon=49&rank=2&query=QA260925&href=/salons/qa260925-b/`. Inspect response, local server log and own click records.
- Expected: recorded=true and a SearchResultClick for the supplied valid salon, or a meaningful validation error.
- Actual: both return `{"ok":true,"recorded":false,"reason":"recording_failed"}`; zero records. Server logs `IntegrityError: null value in column "salon_id" of relation "search_searchresultclick" violates not-null constraint`.
- HTTP:200. Network error: semantic failure in JSON masked by successful HTTP status. Console: HTTP smoke, no browser JS exception applicable.
- Source corroboration: `_model_field_names` returns field.name (including "salon"), but the payload builder only assigns the foreign key when "salon_id" or "result_salon_id" exists in that set; the required FK is omitted.
- Security impact: no data exposure observed; click attribution lost. Regression likelihood: unknown; source currently modified, no historical comparison made.
- Screenshot: N/A for HTTP/server-log evidence. No fix or test-suite execution.
- Relevant source: `apps/search/views.py:1251–1254,1321–1329,1363–1374`; `apps/search/models.py:50–76`.

## 19. Files likely related to each issue

| Issue | Files |
|---|---|
| QA-BUG-001 | `templates/dashboards/multirole_manager_salon_overview.html:1,17`; the 11 standalone multirole templates; `apps/dashboards/multirole_manager_views.py:16`; `templates/dashboard_template.html:31,40,66`; `templates/partials/dashboard/navbar.html:33`. |
| QA-BUG-002 | `apps/dashboards/multirole_manager_views.py:184–191`; `apps/services/forms.py:130–135`; `templates/dashboards/multirole_manager_service_form.html:10`; `apps/dashboards/test_multirole_manager_service_forms.py` posts IDs without establishing rendered selectable choices. |
| QA-BUG-003 | `apps/orders/views.py:2512–2519`, success redirect near4591; `apps/dashboards/multirole_scope_middleware.py`. |
| QA-BUG-004 | `apps/search/views.py:1251–1254,1321–1329,1363–1374`; `apps/search/models.py:50–76`. |

## 20. Final QA status

**MANUAL_QA_FAILED**

| Result | Count |
|---|---:|
| PASS | 104 |
| FAIL | 10 |
| BLOCKED_BY_ENVIRONMENT | 3 |
| INTENTIONALLY_BLOCKED | 6 |
| NOT_APPLICABLE | 1 |
| Total matrix rows | 124 |
| Distinct Critical / High / Medium / Low product bugs | 0 / 2 / 2 / 0 |

Cleanup: Django deletion Collector was inspected before mutation; core IDs/phone ownership were asserted, notification recipients were restricted to QA users, and every nonzero SET_NULL update was checked to target a row already scheduled for QA deletion. One transaction deleted **177 QA-dependent rows**, including7 users,3 salons,4 services,2 groups,3 orders/appointments,2 local settlement records,3 QA conversations and14 authenticated QA sessions. Fresh verification returned zero for all QA root IDs, appointments, settlement IDs, conversations and notifications. Existing neighborhood records and unrelated anonymous conversations were preserved. No database sequence reset or existing-data deletion was performed. Anonymous unauthenticated session records were not broadly deleted.

The server/browser/adapter were closed. Automatic command review rejected removal of the disposable Chrome profile with reason **"blocked by policy"**. That temporary profile remains outside the project at `%TEMP%\Loomera-FinalManualQA-20260925`; no workaround was attempted.

Final branch: `feature/loomera-multirole-001`. The before/after status comparison adds exactly this report path and removes no prior status entries. No source-writing operation was performed. Status comparison is not a byte-for-byte proof across interrupted runtimes.

Final `git status --short`:

```text
 M apps/accounts/customer_communication_views.py
 M apps/accounts/models.py
 M apps/accounts/test_customer_notification_actions_security.py
 M apps/accounts/test_customer_notifications_summary_security.py
 M apps/accounts/test_customer_profile_image_security.py
 M apps/accounts/test_notification_settings_security.py
 M apps/accounts/test_stage1_auth_access.py
 M apps/accounts/urls.py
 M apps/accounts/views.py
 M apps/api/tests/test_api_v1_booking_confirm.py
 M apps/api/tests/test_api_v1_booking_draft_summary.py
 M apps/api/tests/test_api_v1_booking_draft_validation.py
 M apps/api/tests/test_api_v1_my_appointments.py
 M apps/api/v1/auth_serializers.py
 M apps/api/v1/booking_views.py
 M apps/api/v1/my_appointments_views.py
 M apps/bale_bot/menus.py
 M apps/bale_bot/tests.py
 M apps/comments_scores_favories/test_favorite_toggle_security.py
 M apps/comments_scores_favories/views.py
 M apps/dashboards/layout.py
 M apps/dashboards/manager_settings_views.py
 M apps/dashboards/urls.py
 M apps/dashboards/views.py
 M apps/help_center/action_views.py
 M apps/help_center/actions/manager_operations.py
 M apps/help_center/actions/router.py
 M apps/help_center/services.py
 M apps/help_center/views.py
 M apps/messaging/manager_bot.py
 M apps/messaging/promotion_bot.py
 M apps/messaging/roles.py
 M apps/messaging/test_bale_operator_final.py
 M apps/messaging/test_bale_operator_ux.py
 M apps/messaging/test_bale_operator_ux_phase3.py
 M apps/messaging/tests.py
 M apps/search/views.py
 M loomera/settings/base.py
 M static/js/components/help_assistant.js
 M templates/accounts/customer_panel.html
 M templates/base.html
 M templates/dashboard_template.html
 M templates/partials/dashboard/navbar.html
 M templates/partials/dashboard/sidebar.html
 M templates/partials/shell/desktop_site_header.html
 M templates/partials/shell/mobile_app_header.html
?? apps/accounts/migrations/0004_userworkspacepreference.py
?? apps/accounts/services/access.py
?? apps/accounts/services/role_intents.py
?? apps/accounts/services/workspaces.py
?? apps/accounts/test_multirole_customer.py
?? apps/accounts/test_multirole_role_flows.py
?? apps/accounts/test_multirole_services.py
?? apps/accounts/test_multirole_ui.py
?? apps/accounts/test_multirole_workspaces.py
?? apps/api/tests/test_multirole_auth_roles.py
?? apps/dashboards/multirole_finance_preview.py
?? apps/dashboards/multirole_manager_customers.py
?? apps/dashboards/multirole_manager_views.py
?? apps/dashboards/multirole_manual_booking.py
?? apps/dashboards/multirole_manual_booking_cancel.py
?? apps/dashboards/multirole_scope_middleware.py
?? apps/dashboards/multirole_settlement_ledger.py
?? apps/dashboards/test_multirole_manager_booking_cancel.py
?? apps/dashboards/test_multirole_manager_customers.py
?? apps/dashboards/test_multirole_manager_finance_readonly.py
?? apps/dashboards/test_multirole_manager_manual_booking.py
?? apps/dashboards/test_multirole_manager_operations.py
?? apps/dashboards/test_multirole_manager_scope.py
?? apps/dashboards/test_multirole_manager_service_forms.py
?? apps/dashboards/test_multirole_manager_settlement_ledger.py
?? apps/dashboards/test_multirole_manager_team_details.py
?? apps/dashboards/test_multirole_manager_team_invites.py
?? apps/dashboards/test_multirole_membership_compat.py
?? apps/help_center/multirole_scope.py
?? apps/help_center/tests/test_multirole_conversation_scope.py
?? apps/messaging/test_multirole_channel_scope.py
?? apps/search/test_multirole_manager_customer_scope.py
?? docs/qa/LOOMERA-MULTIROLE-001-FINAL-MANUAL-QA.md
?? docs/superpowers/
?? static/css/components/workspace_switcher.css
?? static/css/pages/workspace_choose.css
?? templates/accounts/add_role.html
?? templates/accounts/workspace_choose.html
?? templates/dashboards/multirole_manager_bookings.html
?? templates/dashboards/multirole_manager_customers.html
?? templates/dashboards/multirole_manager_finance_preview.html
?? templates/dashboards/multirole_manager_manual_booking.html
?? templates/dashboards/multirole_manager_manual_booking_cancel.html
?? templates/dashboards/multirole_manager_salon_overview.html
?? templates/dashboards/multirole_manager_service_form.html
?? templates/dashboards/multirole_manager_services.html
?? templates/dashboards/multirole_manager_settlement_ledger.html
?? templates/dashboards/multirole_manager_team.html
?? templates/dashboards/multirole_manager_team_member_form.html
?? templates/partials/shell/workspace_switcher.html
?? test_media/
```
