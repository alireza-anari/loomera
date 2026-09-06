# Loomi messaging beta

## Audit and implementation plan

The initial working tree contained the Phase 1 Loomi module, migration 0003,
payload tests and settings, but lacked the corresponding runtime model, link
builders and dispatcher hooks. No new messaging architecture was needed.

Both Telegram and Bale authenticate and bound webhook requests, parse updates,
store provider-scoped identities/events and deduplicate before dispatch. Telegram
injects its client into the existing Bale dispatcher. Commands and connect tokens,
menu/action callbacks, role-specific text aliases, and authenticated operations
already run there. Unknown text previously went straight to the old Persian menu.
Customer, manager and stylist renderers retain their existing behavior, ownership
checks and booking engine integration. Messaging views manage account connections;
they are not the bot webhook dispatcher.

Implementation sequence: complete the missing Phase 1 integration; use existing
public-profile membership rules for scoped reads; isolate optional Loomi failures;
route operational questions to existing authenticated menus; expose public entry
links; cover both providers and regressions. Existing migration 0003 is reused,
not duplicated. No order creation or availability calculation is added to Loomi.

## Behavior and boundaries

- `/start loomi_s_<salon>` and `/start loomi_p_<stylist>` set provider-identity
  context. Connect tokens keep precedence. Invalid Loomi links clear old context.
- Existing commands, callbacks, menus, text aliases and authenticated operations
  run before Loomi. Unhandled slash commands retain the old fallback.
- Loomi only runs in private chats. It revalidates target visibility on every
  question. Inactive salons/stylists and hidden/resume-only specialists are hidden.
  Salon-only specialists require a visible relationship to an active salon.
- Public specialist services and salon associations honor the existing
  `can_show_stylist_on_salon_profile` membership rules, including legacy relations.
  Specialist services must also belong to a visible active salon.
- Services, prices and contact information are deterministic database reads.
  Private account contact fields, operational records and chat logs are not sent
  to the help assistant. Prior inbound logs include connect/action tokens and are
  deliberately not reused as AI history; the Phase 1 history setting is unused.
- Manager/stylist guidance requires an active messaging account connection and
  active user. It reuses existing role menus; a public link never grants a role.
- Booking questions supply website links only. Existing explicit bot booking and
  availability menus remain unchanged, as required for beta compatibility.
- Scoped questions outside supported public facts return an honest limitation.
  Product/help questions reuse the existing evidence-based Help Center service.
- Optional Loomi work runs in a savepoint. Failures return to existing friendly
  Persian menus without poisoning the surrounding webhook transaction. Rate
  limiter outages stop assistant work while leaving existing menus available.

## Local delivery files

| File | Purpose |
| --- | --- |
| `apps/messaging/loomi.py` | Scoped answers, public visibility, rate limiting, role guidance, safe fallback |
| `apps/messaging/models.py` | Runtime definition matching the supplied context migration |
| `apps/messaging/links.py` | Validated Telegram/Bale deep-link builders |
| `apps/bale_bot/handlers.py` | Shared provider start/fallback hooks after existing flows |
| `apps/messaging/test_loomi.py` | Database, provider, routing, security and error regressions |
| `apps/messaging/templatetags/messaging_connect.py` | Feature-controlled public entry links |
| `templates/messaging/components/loomi_links.html` | Persian provider choice component |
| `templates/pages/detail_salon.html` | Inline salon entry removed in follow-up; global floating assistant remains the entry point |
| `templates/pages/salon_stylist_profile.html` | Specialist entry point |
| `docs/loomi-messaging-beta.md` | Audit, behavior, rollout limits and manual QA |

The existing uncommitted settings, migration 0003, installer script and manifest
were preserved. No commit, push, merge, PR or branch change was made.

## Verification

- `python manage.py test apps.messaging apps.telegram_bot apps.bale_bot --noinput`:
  238 tests passed, including all messaging tests and both provider suites.
- After the final service-lookup failure refinement,
  `python manage.py test apps.messaging.test_loomi --noinput`: 35 tests passed.
- `makemigrations messaging --check --dry-run`: no changes detected.
- Both edited public profile templates and the new component compile.
- `git diff --check`: passed (only Git's existing LF/CRLF conversion notices).

Tests used the repository virtual environment, `loomera.settings.test`, Windows
GIS library initialization and Python UTF-8 mode. New cache-dependent tests use
an isolated in-memory cache. Earlier runs exposed Windows console encoding and
unavailable local Redis configuration; final runs above passed. Expected mocked
failure traces in test output demonstrate fallback handling, not failed tests.

## Deployment prerequisites and remaining limits

See [Messaging environment separation](messaging-environments.md) for staging env
examples, username/template precedence and independent webhook/relay setup.

Apply the existing messaging migration 0003 before enabling Loomi. Configure bot
usernames, existing webhook secrets/provider flags/outbound settings and the
public HTTPS site URL. Enable `LOOMI_MESSAGING_ENABLED` and allow the desired
providers. Use a shared cache with atomic add/increment (such as the existing
Redis configuration) across workers; local-memory limits are per process.

Intent matching is deterministic Persian phrase matching, not a general semantic
search engine. Unrecognized salon questions are intentionally not guessed.
Specialists working in multiple salons receive public services across their
visible salons; the compact specialist payload does not identify one salon.
Booking links open a visible salon and require the customer to finish selection
on the website. Help Center model latency and evidence quality remain dependent
on its existing configuration. Real Telegram/Bale delivery and mobile rendering
require staging QA; mocked provider tests cannot establish live delivery.

## Manual QA — run on both Telegram and Bale

1. Enable the feature in staging. Open a generated salon Loomi link in each
   provider. Start the bot and verify the welcome names that salon. The salon
   page uses the global floating assistant and has no extra inline Loomi block.
2. Ask `قیمت رنگ مو چنده؟`, `چه خدماتی دارید؟`, and `آدرس و شماره تماس؟`.
   Compare with active public database records, including stylist price overrides.
3. Open a specialist profile link. Verify its name/services and booking link.
   Hide its membership, deactivate it, then ask again: no hidden data should appear.
4. Ask `برای فردا رزرو کن`. Follow the website link; no bot-created order or
   claimed available time should appear.
5. Start with a malformed/nonexistent Loomi link after a valid salon context.
   Verify a Persian invalid-link response and no answers from the old salon.
6. Connect a manager and ask about team schedules/reports; connect a specialist
   and ask about tomorrow's schedule. Follow the existing dashboard/menu links.
   Disconnect and confirm authenticated guidance is no longer available.
7. Exercise `/start`, `/help`, `/menu`, `/search`, `/promo`, disconnect, menu
   callbacks and an authorized existing action. Confirm original behavior.
8. Exceed the Loomi quota, then use `/menu`. Disable Loomi and repeat: the old
   fallback works and public assistant links disappear.
9. Simulate Help Center/cache failure in staging. Confirm friendly fallback or
   quota response, working menus, and no webhook transaction failure.
10. Replay a webhook update and confirm it is not dispatched twice. Send a Loomi
    question in a group and confirm private context is not used.

## Beta UX follow-up: direct bots and dashboard sharing

Root cause: without a saved public context, the previous runtime only intercepted
booking words; price/service/contact questions and greetings fell through to the
generic Help Center. Cancellation questions also matched booking words too early.

The existing dispatcher is unchanged. Commands, connect tokens, callbacks,
deterministic text menus and authenticated operations still run first. Within
Loomi, unscoped account/payment/cancellation/policy questions continue to Help
Center; other supported public service/price/contact/salon/stylist questions ask
the user to choose a target. Booking/availability asks for selection without
calculating slots. Greetings introduce Loomi. These replies use the existing
`menu:customer_search`, website search, and guest/connected main-menu callbacks.
Scoped public database behavior is unchanged. Cache failure now returns the old
safe menu, while an exhausted quota still returns the quota response. Context,
service-read and Help Center errors remain inside the optional-work savepoint.

Manager and stylist Settings → Communications reuse the existing shared page.
Managers see a separate card for every active salon they own, independent of
the selected dashboard salon. Specialists see only their authenticated public
profile; hidden/inactive profiles have no share links. Query parameters never
select the share target. Each provider is gated by messaging, provider allowlist,
bot and Loomi flags plus a successfully generated HTTPS URL. Link construction
uses the existing environment-aware builders. No new model or migration exists.

Each link has a readonly selectable URL, an accessible Copy button and Open link.
Copy uses the shared utility and existing `LoomeraFeedback` system. It tries
Clipboard API, then legacy clipboard support; if both fail, it selects the visible
URL for manual copy and does not claim success. No separate toast system was added.

### Follow-up files

- `apps/messaging/loomi.py`: no-context routing and safe cache-error fallback.
- `apps/messaging/links.py`: reusable feature-gated provider list.
- `apps/messaging/templatetags/messaging_connect.py`: reuse that provider list.
- `apps/dashboards/manager_settings_views.py`: authorized manager/stylist cards.
- `templates/dashboards/manager_communication_settings.html`: shared settings integration.
- `templates/dashboards/partials/loomi_share_links.html`: per-target copy/open UI.
- `static/js/utils.js`: shared clipboard fallback utility.
- `static/js/pages/loomi_share_links.js`: copy button and existing feedback wiring.
- `apps/messaging/test_loomi.py`: direct-bot/general-help/failure regressions.
- `apps/dashboards/test_loomi_communication_settings.py`: ownership, multiple
  salons, current stylist, environment URLs, visibility and flag coverage.
- `scripts/test_loomi_clipboard.cjs`: clipboard and feedback behavior tests.
- This document: audit, results and manual QA.

### Follow-up verification

277 Django tests passed, 0 failed, with this combined run:

```text
python manage.py test apps.messaging apps.telegram_bot apps.bale_bot apps.dashboards.test_loomi_communication_settings apps.dashboards.test_telegram_communication_settings_static_guards apps.dashboards.test_beta_ux_workspace_settings_batch50_static_guards apps.dashboards.test_beta_ux_specialist_completion_batch54_static_guards --noinput
```

`node --test scripts/test_loomi_clipboard.cjs`: 5 passed, 0 failed.
`python manage.py makemigrations --check --dry-run`: No changes detected.
`git diff --check`: passed. Django used test settings, Python UTF-8 mode and the
project's Windows GIS initialization. Provider delivery was mocked; no staging or
production webhook/configuration was changed.

### Next manual QA (Telegram and Bale)

A. Use a fresh bot identity without a deep link. Send `سلام`,
`قیمت رنگ مو چنده؟`, `چه خدماتی دارید؟`, `برای فردا رزرو کن`. Expect a greeting
or target-selection guidance with existing search buttons, not a generic Help
Center refusal. Tap salon search and main menu. Then send `لومرا چیه؟`,
`چطور حساب کاربری بسازم؟`, `چطور نوبتم رو لغو کنم؟`, `قوانین پرداخت چیه؟` and
confirm product help remains available.

B. Open an active salon deep link and ask `چه خدماتی دارید؟`,
`قیمت رنگ مو چنده؟`, `آدرس؟`, `برای فردا رزرو کن`. Compare prices/contact with
public database records. Booking must open the website without creating an Order
or claiming available times. An invalid/newly inactive target must not reveal
the old salon's facts.

C. Open a specialist deep link and ask `چه خدماتی انجام میدی؟` and
`قیمت رنگ مو چنده؟`. Confirm public services/prices and membership visibility.

D. As a manager open Settings → Communications. Confirm every active owned
salon has its own named card. Copy and open each Telegram/Bale URL; verify the
bot username belongs to the current environment and the welcome names the right
salon. Changing a query-string salon ID must not add another manager's links.

E. As a specialist repeat the communications checks for your own profile. Alter
the query-string stylist ID and confirm links stay yours. On desktop and mobile,
copy then paste into a text field; expect `لینک لومی کپی شد.`. Deny clipboard
permission and verify legacy/manual selection fallback. Disable Loomi and each
bot flag in staging to verify the section/provider disappears as appropriate.

Phrase matching is deterministic and may miss unfamiliar wording. Live provider
delivery and real-device clipboard/visual behavior still need the manual checks
above. Existing public salon inline UI remains absent and the floating assistant
and specialist public-page block remain unchanged.
