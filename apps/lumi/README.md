# Lumi v2 Tool Layer — Phase A/B/C

Incremental foundation for Lumi v2. Phase C adds optional LLM-based intent/entity
extraction for salon-scoped public read/search requests while preserving the legacy
Lumi path as the fallback.

## Safety boundary

- LLM/provider code never imports Django models.
- Tool handlers never read Django/User models; they call a `LoomeraDomainGateway` port.
- `apps/lumi` stays ORM-free. The temporary Django bridge remains in
  `apps/help_center/lumi_domain_service.py`.
- Every tool execution is checked by backend `ToolPolicy` before its handler runs.
- Tool results are plain dictionaries; ORM objects are never exposed to the model.
- Model routing is restricted to public read/search tools only.
- Server-side conversation scope injects authoritative `salon_id`; model-supplied
  salon/service/stylist IDs are not trusted.
- Service names are resolved through `get_services` before price/availability tools run.
- User ID, session ID, salon ID and arbitrary conversation metadata are not sent to the LLM.
- Provider failure, malformed JSON, low confidence or unsupported intent returns `None`,
  allowing the exact legacy deterministic/Help Center fallback to continue.
- `prepare_booking` remains registered for explicit backend use but is **not advertised
  or routable by the model in Phase C**.
- No `confirm_booking`, cancellation, refund, payment mutation, account mutation,
  specialist write, or manager write tool is registered in Beta.

## Phase C model-routable tools

- `get_services`
- `get_service_price`
- `get_contact`
- `get_availability`
- `search_booking_options`

Phase C is intentionally limited to **salon-scoped messaging contexts**. Stylist scope
continues through the existing deterministic flow until a dedicated stylist-domain
contract exists.

## Rollout flag

Phase C messaging routing must be explicitly enabled:

```env
LOOMI_V2_INTENT_ENABLED=True
LOOMI_V2_INTENT_MIN_CONFIDENCE=0.65
```

When the flag is absent/false, Lumi behaves exactly as before Phase C.

## Local tests

From the repository root:

```powershell
python -m unittest `
  apps.lumi.tests.test_tool_core `
  apps.lumi.tests.test_action_state `
  apps.lumi.tests.test_default_registry `
  apps.lumi.tests.test_intent_routing `
  apps.lumi.tests.test_intent_provider `
  -v

python manage.py check
```

Then run only the existing messaging/Lumi/Help Center automated regressions. Manual
pre-launch phases outside Lumi do not need to be repeated for this change.
