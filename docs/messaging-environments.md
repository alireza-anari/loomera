# Messaging environment separation

Each deployment reads its own environment. There are no production bot identities
or tokens in the link/client configuration defaults. Staging can use
`loomera.settings.production` for secure settings; that module does not select a
production bot. Do not copy a production `.env` into a staging deployment: base
settings also read the repository `.env` for variables absent from the process.
Use separate deployment secrets, databases and cache namespaces for each server.

## Link precedence

`BALE_BOT_USERNAME` now selects the bot for both account-connect and Loomi links.
`BALE_BOT_START_URL_TEMPLATE` only customizes the link format. It supports
`{username}`, `{payload}` and `{raw_token}`. Its rendered destination must be HTTPS
on `ble.ir` and name that same bot. Otherwise the template is ignored, a warning
without tokens/URLs is logged, and the canonical username-based link is used.
Without a username, no link is generated, even if a template names a bot.
Existing fixed templates naming the correct bot still work.

Telegram account-connect and Loomi links use `TELEGRAM_BOT_USERNAME`. Bale's
template never affects Telegram. These link choices do not select API credentials:
the matching token must belong to the bot named by the username.

## Staging environment example

All values below are examples. Values in angle brackets are placeholders, not
usable secrets. Inject actual independent staging secrets through the deployment
secret manager; never print them or store them in source control.

```dotenv
DJANGO_SETTINGS_MODULE=loomera.settings.production
DEBUG=False
ALLOWED_HOSTS=staging.example.com
CSRF_TRUSTED_ORIGINS=https://staging.example.com
PUBLIC_BASE_URL=https://staging.example.com
SITE_URL=https://staging.example.com
MESSAGING_PUBLIC_BASE_URL=https://staging.example.com
MESSAGING_ENABLED=True
MESSAGING_OUTBOUND_ENABLED=True
MESSAGING_ALLOWED_PROVIDERS=telegram,bale
LOOMI_MESSAGING_ENABLED=True
LOOMI_MESSAGING_ALLOWED_PROVIDERS=telegram,bale
BALE_BOT_ENABLED=True
BALE_BOT_USERNAME=ExampleStagingBot
BALE_BOT_TOKEN=<staging-bale-bot-token>
BALE_BOT_START_URL_TEMPLATE=https://ble.ir/{username}?start={payload}
BALE_BOT_API_BASE_URL=https://tapi.bale.ai/bot
BALE_WEBHOOK_SECRET=<unique-staging-bale-webhook-secret>
BALE_WEBHOOK_REQUIRE_SECRET=True
BALE_WEBHOOK_ALLOW_QUERY_SECRET=False
BALE_WEBHOOK_ALLOW_PATH_TOKEN=False
BALE_POLLING_ENABLED=False
TELEGRAM_BOT_ENABLED=True
TELEGRAM_BOT_USERNAME=ExampleStagingBot
TELEGRAM_BOT_TOKEN=<staging-telegram-bot-token>
TELEGRAM_BOT_API_BASE_URL=https://api.telegram.org/bot
TELEGRAM_WEBHOOK_SECRET=<unique-staging-telegram-webhook-secret>
TELEGRAM_RELAY_URL=
TELEGRAM_RELAY_SECRET=
```

`BALE_BOT_START_URL_TEMPLATE=` (explicit empty value) is also supported and uses
the canonical link. Do not leave stale production values in staging secrets.
Standard provider API base URLs above are shared provider infrastructure, not
production Loomera servers; tokens choose the specific bots.

If direct Telegram access is unavailable, replace the empty relay settings with
`TELEGRAM_RELAY_URL=https://telegram-relay.staging.example.com` and
`TELEGRAM_RELAY_SECRET=<unique-staging-relay-secret>`. The relay itself must use
the staging bot token. When relay mode is enabled, this application's client
sends requests to the relay without forwarding `TELEGRAM_BOT_TOKEN`; merely
changing the application's token will NOT change a production relay's bot.

## Webhook pairing

With the example base URL the destinations are:

- Bale: `https://staging.example.com/messaging/webhooks/bale/`
- Telegram: `https://staging.example.com/messaging/webhooks/telegram/`

Both existing webhook registration commands derive destinations from
`MESSAGING_PUBLIC_BASE_URL`. Bale uses `BALE_BOT_TOKEN`; Telegram uses
`TELEGRAM_BOT_TOKEN` in direct mode or the configured relay in relay mode. Each
incoming handler validates its environment's webhook secret.

Configure the staging environment first, then register webhooks from the staging
deployment only. The existing `bale_webhook_admin --set` defaults to dry-run;
`--set --apply` performs registration. `telegram_webhook set` performs registration
immediately. No live registrations were made as part of this local change.

Verify the provider bot identity and registered destination securely before
enabling outbound traffic. The source cannot determine whether an arbitrary
operator-supplied token belongs to production without querying that provider.
Never reuse a production token in staging: registering a webhook with that token
would change the production bot's destination. Production must likewise use its
own username, token, webhook secret, base URL and (if applicable) relay.

The salon-page inline Loomi entry component was removed because the global
floating assistant is the entry point. Shared tags/components and specialist-page
entry points remain available.

Verification: `python manage.py test apps.messaging apps.telegram_bot apps.bale_bot
--noinput` passed all 246 tests using test settings and the project's Windows GIS
initialization. Coverage includes stale template precedence, portable templates,
independent environment clients/links/webhook destinations, and rejection of the
other environment's webhook secret. Provider registration calls in tests are
mocked. `git diff --check` passed.
