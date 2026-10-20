# Architecture and scope

## Implemented POC

One FastAPI process serves static assets and a read-only REST API. The frontend
uses plain JavaScript, XMLHttpRequest, system fonts and flexbox to reduce browser
requirements. Serving assets via FastAPI follows its documented
[StaticFiles pattern](https://fastapi.tiangolo.com/tutorial/static-files/).
There is no frontend build step, external CDN or client-side credential.

`DashboardProvider` isolates data retrieval; `MockProvider` supplies fictional
examples. Countdown logic accepts aware timestamps and compares UTC timestamps,
so elapsed time stays correct across Prague DST transitions. The browser derives
Prague wall time from the response offset and refreshes that offset with each
snapshot. A failed request suppresses actionable countdowns until recovery.
The server returns rounded countdown metadata and absolute morning-stage boundaries;
the browser selects the current stage from those boundaries and ticks between
responses. Separate dressing, shoes and walking settings define the preparation
window. All family-facing content is Czech. Local SVG pictograms avoid dependence
on platform emoji fonts. A large current-action image and a marked step reinforce
color changes; neutral waiting replaces activity prompts on stale data.

The initial provider supplies a whole demo snapshot. When real integrations are
introduced, split the adapter boundary by integration and track each source's
last successful sync independently. This POC returns 503 for a provider failure;
it does not yet isolate a failing school integration from a working bus provider.

The container runs as a non-root user with a read-only filesystem. Compose binds
to loopback by default. This POC has only GET endpoints and synthetic data.
Provider errors emit a JSON event without exception contents to avoid accidental
secret disclosure. Uvicorn access logs retain their standard format; full
structured request logging is deferred.

## Deliberately deferred

SQLite, credentials, real API clients, durable caching, scheduling, school-day
rules, TV control and authentication are not implemented. In-memory browser
retention demonstrates loss-of-connection behavior but is not persistent caching.
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

There are no verified claims of TV control, live bus tracking or production
reliability. The repository contains no real family records or credentials.
