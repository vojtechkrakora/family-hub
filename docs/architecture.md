# Architecture and scope

## Implemented POC

One FastAPI process serves static assets and a read-only REST API. The frontend
uses plain JavaScript, XMLHttpRequest, system fonts and flexbox to reduce browser
requirements. Serving assets via FastAPI follows its documented
[StaticFiles pattern](https://fastapi.tiangolo.com/tutorial/static-files/).
There is no frontend build step, external CDN or client-side credential.

Independent async providers supply transport, school and calendar data through
validated internal schemas. A per-source cache coordinates refresh, a per-source
deadline (seven seconds for transport/school, 25 seconds for calendar) and retry backoff. Failures are isolated; the browser receives per-source
availability, provenance and last successful sync metadata. See `integrations.md`
for contracts, operational limits and verified research references.

Countdown logic compares aware timestamps in UTC, preserving elapsed time across
Prague DST changes. The server computes absolute morning-stage boundaries; the
browser ticks locally between snapshots. Stale transport data never generates a
routine. Empty departure lists and disabled providers produce a neutral waiting
state while other dashboard sections remain visible.

All family-facing content is Czech. Local SVG pictograms avoid platform emoji
fonts. A large current-action image and marked step reinforce color changes.

The container runs as a non-root user with a read-only filesystem. Compose binds
to loopback by default. This POC has only GET endpoints and synthetic data.
Provider errors emit a JSON event containing only the integration identifier. Uvicorn access logs retain their standard format; full
structured request logging is deferred.

## Deliberately deferred

SQLite, credentials, school/calendar clients, durable caching, scheduling, school-day
rules, TV control and authentication are not implemented. Server caches and
browser retention are in memory only and do not survive restarts.
Dependencies use bounded ranges; a fully locked deployment is a hardening task.

## Validation risks

| Risk | Validation |
| --- | --- |
| Older webOS browser rendering or JavaScript support | Open on actual LG TV; inspect layout and refresh over an extended session |
| Native TV power-on and browser launch | Test actual hardware, pairing and overnight standby; see TV checklist |
| Synology CPU architecture and container support | Build/deploy on the actual NAS and check health, resource use and restart |
| Transport schedule and live data availability | Verify licensed/documented sources before writing an adapter; retain scheduled fallback |
| Unofficial school API and credential expiry | Verify against the school's endpoint with securely supplied credentials |
| Calendar privacy | Select ICS or Google authorization and store credentials server-side |

The IDESKA adapter reads the verified public departure board, adding reported
delay to scheduled time. Per-departure metadata distinguishes estimates from
schedules. It falls back to COMETT on unavailable or ambiguous board data.
The COMETT adapter reads verified public stop-timetable HTML; it is not a live
vehicle feed or a documented API. Both lines must succeed before generating a
routine. Refer to `integrations.md` for supported calendar rules and limitations.

There are no verified claims of TV control or production
reliability. The repository contains no real family records or credentials.

GPS progress is an optional enrichment of the selected IDESKA departure. A small
in-memory tracker infers crossing dwell and passage from fresh matched fixes;
no vehicle registry or location history is persisted. See integration notes for
geography attribution, thresholds and practical validation still needed.

The fixed SVG minimap is a local static asset with a small ES5 marker renderer.
It reuses normalized selected-trip GPS and polling, requires no map library or
external tile requests, and keeps display-only stale coordinates separate from
verified preparation state.

Bakaláři is an optional read-only provider with an in-memory token lifecycle and
strict normalized homework contract. Its activation also enables dashboard HTTP
Basic access control; credentials are loaded from protected local JSON or server
environment, never from frontend requests. School failures remain isolated from
transport and calendar. Public reachability, household login, normalized homework and browser access
protection were verified on 2026-10-20. Credentials remain in local configuration.

Google Calendar uses read-only private ICS feeds, normalized by maintained ICS and
recurrence libraries in a disposable parser process. That process is local work
with a deadline, not a separate deployed service. The existing authenticated
dashboard displays a Prague-local daily agenda, including events overlapping
midnight. Source URLs stay in protected server configuration. Live household feed
retrieval and authenticated rendering were verified on 2026-10-21 with three feeds.

Synology Container Manager has a standalone `compose.synology.yaml` deployment.
It binds only the two protected configuration files read-only, explicitly enables
live integrations, and loads them through `*_CONFIG_FILE` settings. It runs as
root with only `DAC_OVERRIDE` so it can read File Station-created private files;
its filesystem is read-only. Secrets are not in the container environment or
build context. Local Docker continues to use the existing helper. See
`docs/synology.md` for project creation instructions.
