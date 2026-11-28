# Mock Google server (Gmail + Calendar)

A fake Google that behaves like the real one: the same URLs, JSON shapes, error bodies and OAuth flow for the calls
SolNexus makes, served from synthetic data. The master service, the contract tests and local demos talk to it exactly
as they would talk to Google, so the whole Google Workspace pipeline runs with **no Google account and no secrets**.

Code that uses it does not know it is talking to a mock. It only has two addresses, both Google's by default: where
the API lives and where access tokens are refreshed. Point them here and nothing else changes.

It only starts with `MOCK_ENVIRONMENT` set to `local`, `ci` or `dev`. It must never run where real data flows, where
it could be mistaken for Google.

## Run it

```bash
docker compose --profile mock up -d google-workspace-mock
curl http://127.0.0.1:18090/_mock/health        # {"status":"ok","environment":"local","dataset":"synthetic_soltech"}
```

The interactive API docs are at http://127.0.0.1:18090/_mock/docs. The port is bound to localhost only.

## Point a client at it

| Address | Real Google | The mock (from the host / inside Compose) |
|---|---|---|
| Gmail API | `https://gmail.googleapis.com/gmail/v1/users/me` | `http://127.0.0.1:18090/gmail/v1/users/me` / `http://google-workspace-mock:8090/gmail/v1/users/me` |
| Calendar API | `https://www.googleapis.com/calendar/v3` | `…:18090/calendar/v3` / `http://google-workspace-mock:8090/calendar/v3` |
| OAuth token endpoint | `https://oauth2.googleapis.com/token` | `…:18090/token` / `http://google-workspace-mock:8090/token` |

The master takes these as `api_root` and `token_uri` (`GmailClient.from_token_file`). The token address must be passed
as configuration: google-auth ignores any `token_uri` inside a token file, by design.

Use an ordinary authorized-user token file with the mock's fixed, public, fake credentials. They unlock nothing but this
mock:

```json
{"type": "authorized_user",
 "client_id": "solnexus-mock-client.apps.example.test",
 "client_secret": "mock-client-secret-not-a-real-secret",
 "refresh_token": "mock-refresh-token-not-a-real-secret"}
```

## What it serves

| Endpoint | Behaves like Google |
|---|---|
| `POST /token` | Refresh-token grant. Errors in OAuth's format: `invalid_client`, `invalid_grant` (wrong or revoked), `invalid_scope` |
| `GET /gmail/v1/users/{me}/profile` | Address and current `historyId` |
| `GET /gmail/v1/users/{me}/messages` | Newest first; spam and trash hidden unless `includeSpamTrash`; `labelIds` must all match; `q` with `newer_than:`/`older_than:`; paging |
| `GET /gmail/v1/users/{me}/messages/{id}` | `format=raw` (base64url RFC 822, unpadded) or `minimal`; 404 once deleted |
| `GET /gmail/v1/users/{me}/history` | Changes after `startHistoryId` (added, deleted), type and label filters, paging; **404 when the start is older than retained history** (history gap) |
| `GET /calendar/v3/calendars/{primary}/events` | `singleEvents=true`; full sync (last page carries `nextSyncToken`), incremental sync with `syncToken` including cancellations in minimal form; **410 `fullSyncRequired`** for an expired token; `timeMin`/`timeMax` on full syncs |

Every API call needs an access token from `/token`: unknown or expired → 401 (clients refresh), a token without the
API's scope → 403 `insufficientPermissions` (e.g. consented for Gmail only).

## Change it while it runs (`/_mock/*`)

Control routes answer `{"success": true, "data": …}` or `{"success": false, "error": "CODE", "message": …, "status": N}`.
Bodies use the same strict schema as the [datasets](datasets/README.md).

| Route | Does |
|---|---|
| `POST /_mock/reset` | Back to the seed: data, cursors, scripted changes, tokens, revocation, faults, delays |
| `POST /_mock/scripted-changes/next` | Apply the dataset's next scripted change (409 when all are applied) |
| `POST /_mock/gmail/messages` · `DELETE /_mock/gmail/messages/{id}` | New mail arrives · mail is deleted |
| `POST /_mock/calendar/events` · `…/{id}/reschedule` · `…/{id}/cancel` | Book (series allowed) · move · cancel |
| `POST /_mock/gmail/expire-history` | Every Gmail cursor becomes too old → 404 → client does a full resync |
| `POST /_mock/calendar/expire-sync-tokens` | Every sync token expires → 410 → client does a full sync |
| `POST /_mock/oauth/revoke` | Consent revoked: tokens stop working, refresh is `invalid_grant` (until reset) |
| `POST /_mock/oauth/expire-access-tokens` | Access tokens expire: 401, the client refreshes and carries on |
| `GET` · `POST` · `DELETE /_mock/faults` | List · schedule · clear injected failures |
| `PUT /_mock/delays/{gmail\|calendar\|token}` | Slow responses for one target (`{"delay_ms": 300}`) |
| `GET /_mock/state` | Counts and cursor positions only, for assertions |

Fault recipes (`target` is `gmail`, `calendar` or `token`; `times` is how many upcoming requests fail):

```bash
M=http://127.0.0.1:18090/_mock
curl -X POST $M/faults -H 'Content-Type: application/json' -d '{"target":"gmail","kind":"rate_limit","times":2,"retry_after_seconds":5}'
curl -X POST $M/faults -H 'Content-Type: application/json' -d '{"target":"gmail","kind":"daily_quota"}'
curl -X POST $M/faults -H 'Content-Type: application/json' -d '{"target":"calendar","kind":"service_unavailable","times":3}'
curl -X POST $M/faults -H 'Content-Type: application/json' -d '{"target":"token","kind":"invalid_grant"}'
```

API fault kinds: `rate_limit` (429), `user_rate_limit` (403), `daily_quota` (403), `backend_error` (500),
`service_unavailable` (503), `expired_access_token` (401). Token fault kinds: `invalid_grant` (400, permanent) and
`token_server_error` (500, retryable).

## Settings

Validated at startup. Every problem is reported at once, grouped by variable with a fix, then the process exits 1.

| Variable | Default | Meaning |
|---|---|---|
| `MOCK_ENVIRONMENT` | `local` | `local`, `ci` or `dev`. Anything else refuses to start |
| `MOCK_DATASET` | `synthetic_soltech` | Dataset file name in `datasets/` (bare name only) |
| `MOCK_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `MOCK_RESPONSE_DELAY_MS` | `0` | Delay before every Google-shaped response (0–30000) |
| `MOCK_ACCESS_TOKEN_TTL_SECONDS` | `3600` | Access token lifetime (1–86400); short values exercise refresh |
| `MOCK_OAUTH_GRANTED_SCOPES` | `gmail.readonly` + `calendar.events.readonly` | What the fake refresh token was consented for (full scope URLs, space- or comma-separated) |

## Data and time

The [synthetic SolTech dataset](datasets/README.md) seeds 10 messages and 13 calendar events, plus 6 scripted changes.
The mock's clock starts at the dataset's `seeded_at` and then moves forward in real time, so relative queries such as
`newer_than:30d` match the same messages whenever you run. Restarting or `POST /_mock/reset` returns to the seed;
nothing is persisted.

## Tests

```bash
docker compose --profile test run --rm google-workspace-mock-tests        # ruff + unit tests (no network, no database)
docker compose --profile test run --rm google-workspace-contract-tests    # the master's real code against this mock
```

The contract tests also need `SOLNEXUS_TEST_DATABASE_URL` (the throwaway `*_ingest_test` database, see
[data-platform/README.md](../../../data-platform/README.md#tests)) and skip without it. CI runs both in the
**Google Workspace** job, with the mock started from its real image.

## Known differences from real Google

The mock implements what SolNexus uses and fails loudly (400) on the rest instead of returning wrong data.

| Area | Difference |
|---|---|
| Gmail search | `q` supports only `newer_than:` and `older_than:` |
| Gmail message formats | Only `raw` and `minimal` |
| Gmail paging | Offset-based within one request's result, so concurrent changes can shift a page boundary (Calendar paging is snapshot- and key-based and does not have this) |
| Calendar | `singleEvents=true` is required; recurring series exist only as occurrences; only `DAILY`/`WEEKLY` with `COUNT` rules |
| Cancelled events | Also carry `updated`; Google guarantees only `id` and `status`, so clients must not depend on more |
| Bounded full sync | Returns `nextSyncToken` even with `timeMin`; still to be verified against Google (calendar contract, open decisions) |
| Scope | One mailbox, one calendar, one OAuth client; no Directory, Drive or write APIs |

## Code map

| File | Role |
|---|---|
| `mock_app.py` | App factory, startup (settings → dataset → dry run → state), error handlers |
| `mock_settings.py` | Environment settings and the shared startup report |
| `mock_dataset.py` · `datasets/` | Dataset schema · seed data |
| `mock_state.py` | Mailbox with history, calendar with versions, the clock, scripted changes, reset |
| `mock_oauth.py` | Token endpoint and per-API access checks |
| `mock_faults.py` | Scheduled failures and delays |
| `mock_paging.py` | Opaque page and sync tokens |
| `google_errors.py` | Google's and OAuth's error formats |
| `routes_gmail.py` · `routes_calendar.py` · `routes_mock_control.py` | Gmail API · Calendar API · `/_mock` controls |
