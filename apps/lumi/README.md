# Lumi v2 Tool Layer (Phase A/B)

Additive foundation for the next Lumi architecture. Existing `apps.help_center`
flows remain the production path in this phase.

## Safety boundary

- LLM/provider code never imports Django models.
- Tool handlers never read Django/User models; they call a `LoomeraDomainGateway` port.
- `apps/lumi` is ORM-free. The temporary Django bridge lives in `apps/help_center/lumi_domain_service.py`, behind the domain port, until those calls move into first-class services owned by booking/salons/accounts.
- Every execution is checked by backend `ToolPolicy` before the handler runs.
- Tool results are plain dictionaries; no ORM objects are exposed to the model.
- `prepare_booking` reuses the current staging booking action and checkout preview.
- No `confirm_booking`, cancellation, refund, payment mutation, account mutation, specialist write, or manager write tool is registered in Beta.

## Tools included

- `get_my_profile`
- `get_services`
- `get_service_price`
- `get_contact`
- `get_availability`
- `search_booking_options`
- `prepare_booking`

## Local tests

From the repository root:

```powershell
python -m unittest apps.lumi.tests.test_tool_core apps.lumi.tests.test_action_state apps.lumi.tests.test_default_registry -v
python manage.py check
```

Then run the existing booking/help-center regression suite that is already used by
this repository before pushing.

## Not wired yet

**This patch intentionally does not change current UI/bot behavior yet.** The existing Help Center/Lumi router is untouched. The next phase can
connect the free LLM for intent/entity extraction and route approved intents to this
registry without changing the tool/domain contracts.
