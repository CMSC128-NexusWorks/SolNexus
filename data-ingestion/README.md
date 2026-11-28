# Data ingestion

Source connectors: services that read SolTech's conversation and booking sources and write what they read,
unchanged, to the `bronze` schema (plus each message's initial resolution in `app`). Each source gets its
own folder, laid out the same way, following the Glynac extraction services this design is modeled on.

| Connector | Reads | Status |
|---|---|---|
| [`google-workspace/`](google-workspace/README.md) | Gmail (Phase 1) and Google Calendar (SolTech bookings: web app → Calendly → Google Calendar) | Gmail extraction in place; Calendar, the mock server and the scan API in progress (SNX-67) |
| `facebook/`, `viber/` | Facebook Page and Viber conversations | Phase 2, only after Phase 1 acceptance |

Connectors never build silver. They write bronze; the [data platform](../data-platform/README.md) orchestrates
them and builds silver with dbt. Table structure is owned by the API's Alembic migrations
([docs/database.md](../docs/database.md)).
