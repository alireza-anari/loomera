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
