# Homeboard

A local family dashboard for a Synology NAS and a living-room television.

## Current milestone: bus delay estimates

The Czech morning dashboard now selects the nearest estimated departure of lines
43 and 45 from **Planá nad Lužnicí, Nad Hejtmanem Lipová alej** using IDESKA's public departure board and COMETT's
published stop timetables as fallback. The source labels the direction **Strkov**. The common
weekday departure of line 45 is 07:34, but the dashboard always chooses the nearest
eligible bus across both lines, not a fixed morning time.

Reported delays adjust the countdown and preparation stages. The UI distinguishes
an **estimate** from a schedule without live delay. Estimates cannot predict when
railway barriers open. GPS progress now identifies the selected trip in Planá,
at the crossing, and on Strkovská beyond St. Barbora. Fresh position reports
can trigger dressing earlier; missing GPS leaves the existing time-based routine. School and calendar
remain fictional samples in the default configuration. The deployed household
instance now uses verified Bakaláři homework and Google calendar feeds; TV control is not connected. Set `TRANSPORT_SOURCE=mock` for a fully offline demonstration.

The interface uses large local SVG illustrations for children who cannot read:
relax, get dressed, put shoes on, and leave together. Separate clothing, shoes and
walking durations determine the routine. Data failures suppress action prompts.

## Local development (macOS)

Requires Python 3.10 or later.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn homeboard.main:app --host 127.0.0.1 --port 8091 --reload
```

Open http://localhost:8091. No frontend build or external credentials are needed. Internet access is needed
for the IDESKA board and COMETT timetable; use `TRANSPORT_SOURCE=mock` for offline development.
For a household-device test, replace `127.0.0.1` with your Mac's private LAN IP
and open `http://<mac-lan-ip>:8091` from a device on the same network. Allow the
port in the local firewall if needed. Keep the computer awake during the test.

## Docker Compose / Synology

For **Synology Container Manager**, use the standalone `compose.synology.yaml`
and follow [the Synology setup guide](docs/synology.md). It mounts private JSON
files read-only and preserves live integrations and dashboard protection across
recreates, without a startup helper. Set the NAS LAN IP and configure file
permissions as described in the guide. Actual NAS deployment is not yet verified.

For a **local demo** without private data, use `compose.yaml`:

```sh
cp .env.example .env
docker compose up --build -d
docker compose ps
```

The demo binds to loopback by default and uses mock school/calendar data.
For the existing local Docker deployment with private integrations, continue using
`python3 scripts/start_homeboard.py`; this helper supplies its configuration via
the environment. The Synology file-based deployment does not use this helper.
Integration caches remain in memory; private JSON files persist on the host.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOMEBOARD_BIND_IP` | `127.0.0.1` | Compose host bind address |
| `HOMEBOARD_PORT` | `8091` | Compose host port |
| `WALKING_MINUTES` | `1` | Time to the stop outside the house, integer 0–120 |
| `DRESSING_MINUTES` | `10` | Getting dressed, integer 1–120 |
| `SHOES_MINUTES` | `3` | Putting shoes on, integer 1–120 |
| `TRANSPORT_SOURCE` | `ideska` | `ideska`, `comett`, `mock` or `disabled` |
| `SCHOOL_SOURCE` | `mock` | `bakalari`, `mock` or `disabled` |
| `CALENDAR_SOURCE` | `mock` | `google_ics`, `mock` or `disabled` |

Compose reads `.env` automatically. Local Python execution reads process
environment variables, not `.env`; for example:

```sh
DRESSING_MINUTES=12 SHOES_MINUTES=3 WALKING_MINUTES=1 uvicorn homeboard.main:app --port 8091
```

Invalid settings fail at startup. Timezone is Europe/Prague. The browser polls
every 15 seconds (10 seconds near or beyond the crossing) after each completed request, with an 30-second timeout, and
updates countdowns every second. After a failed request or 45 seconds without a
successful response, existing examples stay visible with a stale-data warning.
Fonts and illustrations are local. Only the scheduled transport adapter contacts
an external site. It reads both public stop pages at most once every five minutes.

## Verification

```sh
python -m pytest
ruff check .
ruff format --check .
curl --fail http://localhost:8091/health
```

Tests cover rounding, departure and walking thresholds, morning-stage boundaries,
preparation settings, midnight, both DST
transitions, invalid settings, stable mock departures, HTTP routes and provider
failure. `/health` checks process responsiveness, not third-party integrations.
`/api/dashboard` returns the demo snapshot and countdown metadata.

## Structure and next milestone

- `homeboard/main.py`: HTTP application and configuration.
- `homeboard/domain.py`: timezone-aware countdown logic.
- `homeboard/providers.py`: separate mock transport, school and calendar adapters.
- `homeboard/integrations/`: normalized models, independent caches and fetch timeouts.
- `homeboard/static/`: plain HTML, CSS and JavaScript.
- `tests/`: isolated automated tests.
- `docs/architecture.md`: decisions and remaining technical risks.
- `docs/tv-validation.md`: actual television validation checklist.

Next: manually open the dashboard on the LG 55SK8100PLA and validate readability
and browser behavior; then investigate and test power-on, pairing, browser launch
and overnight automation. Do not treat desktop success as proof of TV support.

## POC verification record

Verified locally on 2026-10-20:

- Python 3.10: 73 pytest tests passed; Ruff lint and formatting checks passed.
- JavaScript syntax check passed with Node.js.
- Headless desktop Chrome: demo rendering, 1920×1080 and 1280×720 layouts
  without scrolling, and a 390-pixel mobile layout without horizontal overflow.
- Browser stage checks: all four morning stages and the expired-departure waiting
  state rendered correctly with loaded pictograms and Czech labels.
- Browser refresh failure: countdowns and active-stage prompts were hidden and automatically returned
  after connectivity recovered, with no JavaScript exceptions.
- Docker image built; Compose container started and HTTP health/dashboard routes
  responded successfully.

The installed Starlette test client emits a deprecation warning for its httpx
transport; tests still pass. TV/browser hardware, Synology deployment and overnight
operation have not been verified. Browser checks used local Playwright tooling;
it is not a runtime dependency or part of the pytest suite.


## Child-friendly morning routine

The stop is directly outside the house; getting children dressed is the main
preparation time. Defaults are provisional: 10 minutes for clothing, 3 for shoes,
and 1 to reach the stop. Adjust these settings to your household.

For a 07:30 departure, the current step becomes clothing at 07:16, shoes at
07:26 and leaving with an adult at 07:29. Before 07:16, the sun indicates spare
time. At each exact boundary the next step begins. The active illustration is
large, repeated in a highlighted step with a marker; color is not the only cue.
The 14 time blocks drain over the total preparation window, capped at full when
more time remains. Digital and analog clocks show Prague time. The timeline
indicates the expected activity, not whether a child has actually finished it.

On connection failure all activity prompts switch to a neutral pause icon and
countdowns disappear. An expired departure also shows a neutral waiting state.
In mock mode, the quarter-hour schedule still rolls to the next sample bus on refresh.
Child-specific progress remains outside this POC.

`WARNING_MINUTES` has been replaced by `DRESSING_MINUTES` and `SHOES_MINUTES`;
update any existing local environment settings. Source code and engineering
documentation remain English; all family-facing copy and sample data are Czech.


## Preparing real integrations

See `docs/integrations.md` for verified source references, remaining unknowns and
required setup inputs for transport, Bakaláři, calendar and TV control.

The dashboard API now includes `integrations.transport`, `integrations.school`
and `integrations.calendar` metadata with source, status and last successful sync.
Each source can be disabled independently. Unsupported provider names fail at
startup. Mocks use no credentials or external traffic. The default `ideska` provider reads the public departure board without authentication
and falls back to the COMETT timetable when needed. See the integration notes for
the clock-only board limitation outside 03:00–21:00 and unverified GPS freshness.
School/calendar failure leaves bus countdowns running; stale bus data suppresses
morning prompts. Empty schedules are handled without a server error.

The server caches each source separately in memory, refreshes on demand (300 seconds
for COMETT, 30 for IDESKA/mock transport, 300 for school/calendar), applies a 25-second calendar fetch timeout (7 seconds for transport/school) and waits
30 seconds before retrying transport/calendar failures, 300 seconds for school. Run a single application worker for now.
Tests cover timeout cancellation, concurrent requests, invalid data, independent
failures, stale-cache retention and recovery. The health response is now simply
`{"status":"ok"}`; integration availability belongs in the dashboard response.


## Timetable behavior and limitations

The reader merges lines 43 and 45 chronologically and shows the selected line plus
the next two departures. For another day, it includes the departure date. Longer
waits use hours to keep the display readable.

It checks source stop, direction, line, page date, validity, expected table layout,
route code and service restrictions. Selection respects Czech public holidays,
Saturday/Sunday columns, July–August weekdays and published date exclusions.
Missing or changed structure fails visibly rather than silently inventing times.
Both line tables must load successfully; otherwise the result is marked stale or
unavailable, since selecting from only one line might miss the nearest bus.

This is a public HTML reader, not an official API contract. It currently supports
the observed E route and the published `nejede` date/range restrictions. It searches
eight calendar days and does not extrapolate past an explicit timetable end date.
When the operator publishes no end date, future results assume the fetched schedule
continues until the next refresh. It does not independently incorporate disruption
notices or guarantee that the bus continues from Strkov to náměstí. See
`docs/integrations.md` for sources and the observed holiday-search discrepancy.

When the selected bus has fresh GPS at the crossing or farther along toward the
stop, both transport cache refresh and browser polling switch to 10 seconds.
Otherwise transport refresh remains 30 seconds (300 for COMETT) and browser polling
15 seconds. School/calendar caching is unchanged. Requests never overlap within
a browser; intervals are measured after completion, so network latency adds time.

## Fixed television minimap

A local SVG map shows the selected bus, crossing P5647 and Lipová alej stop.
Distinct bus, barrier and shelter symbols match a Czech legend beneath the map;
the markers do not rely on color alone.
It has no pan, zoom, map SDK, API key or runtime tile requests. Map data is from
OpenStreetMap (ODbL); attribution is displayed beside the map. The fixed area
covers Planá and the approach from the north. Vehicles outside it are explicitly
labelled outside the map rather than pinned to an edge.

GPS updates reuse existing transport polling. Old/missing GPS leaves the last
same-trip position grey with its age for at most five minutes; changing trips
clears it immediately. This display-only history never drives preparation prompts.
The SVG uses older-browser-compatible features, but the actual LG TV still needs
visual verification. The existing analog clock and child preparation icons remain.

To rebuild the local background, download the OSM bounding box documented in
`scripts/build_minimap.py`, then run `python scripts/build_minimap.py extract.osm`
from the repository root. Bounds and dimensions must stay aligned with the HTML
map attributes. The renderer uses Python's standard library only and updates the map URL with a
content hash so browsers cannot reuse an older background after a map change.

## Bakaláři homework setup

Public reachability was checked for ZŠ Planá nad Lužnicí on 2026-10-20: `/api/3`
reports 3.52.1 and anonymous homework requests return 401. Authenticated homework retrieval and normalization were successfully verified
with the locally configured household account on 2026-10-20. No private response
bodies or credentials were stored in the repository. Protocol
references and limitations are documented in `docs/integrations.md`.

1. Run `python3 scripts/setup_bakalari.py` in an interactive terminal. Enter the
   school username/password and a separate Homeboard password (12+ characters).
   Inputs are hidden. The script creates `.local/bakalari.json` with mode 0600
   inside a 0700 directory and refuses to overwrite an existing configuration.
   This directory is excluded from Git and Docker build context.
2. For local Docker, run `python3 scripts/start_homeboard.py`. It reads the local JSON,
   supplies it through `BAKALARI_CONFIG_JSON`, selects `SCHOOL_SOURCE=bakalari`, and
   rebuilds only Homeboard. Use this helper for subsequent Docker rebuilds with
   school integration enabled. Standard Compose without these settings uses mocks.
   Existing restart policies retain the container's configured environment.
3. Open the dashboard and log in as `homeboard` using the separate Homeboard
   password. School credentials are never used in the browser. For local Python
   development, set `SCHOOL_SOURCE=bakalari`; the server reads the same local JSON
   (override with `BAKALARI_CONFIG_FILE` if needed).

No credentials are sent during setup. Tokens remain in backend memory and are
refreshed when needed. Do not include local configuration or container environment
output in diagnostics. Access to the Docker daemon permits reading its environment.
Keep the default loopback binding; for LAN access, use a trusted HTTPS reverse proxy
because HTTP Basic authentication over plain HTTP does not encrypt the dashboard
password. `/health` remains public and contains no household data.

Homework refreshes every five minutes. Failed school requests retry after five
minutes, with a 15-minute login cooldown after rejected credentials and bounded
rate-limit backoff. Last successful data remains visible as stale after failure.
Today/tomorrow tasks are prioritized, then overdue and later tasks. The TV shows
the first four and a count of additional tasks, with full results in the protected
API. Long text is abbreviated visually to retain the fixed TV layout. Only open,
not-done tasks due in the previous 14 or next 30 days are included. No attachments,
read acknowledgements, completion actions, timetable changes or multi-child
selection are implemented in this increment.


## Google Calendar setup

The read-only Google ICS adapter was verified with three locally configured
household feeds on 2026-10-21. No Google account password or
OAuth application is needed. In desktop Google Calendar, open Settings → the
calendar → Integrate calendar → Secret address in iCal format. See
[Google's instructions](https://support.google.com/calendar/answer/37648?hl=en-GB).
Do not make the calendar public or paste the secret address into chat.

Run `python3 scripts/setup_calendar.py` in a terminal. Enter a short calendar
label and its private iCal address (hidden input). Repeat for up to five calendars,
then leave the label blank to finish. This writes `.local/calendar.json` with
mode 0600, excluded from Git and Docker build context. Existing configuration is
never overwritten. This increment reuses the existing protected Homeboard login
configuration from the school setup; there is no new dashboard password.

For local Docker, run `python3 scripts/start_homeboard.py` to enable the configured calendars while
preserving Bakaláři. The helper passes `GOOGLE_CALENDAR_CONFIG_JSON` through the
server environment and selects `CALENDAR_SOURCE=google_ics`. Local Python execution
reads `.local/calendar.json` (or `GOOGLE_CALENDAR_CONFIG_FILE`). Calendar activation
also requires the existing Homeboard login settings, even if school is disabled.

Feeds refresh every five minutes. Data is normalized to Europe/Prague with
recurrences, exceptions, cancellation, all-day and multi-day overlap support.
Floating times use the feed timezone, defaulting to Prague. The current two-day
expansion covers today's agenda and the next midnight rollover; only today's
intersecting events are displayed. DTEND is exclusive. The TV shows four events
and an additional-event count; the protected API contains the full daily list.
Upcoming appointments within an hour are highlighted. Labels identify calendars.

A feed failure marks the combined last-success calendar as stale; it does not
silently omit one calendar or affect transport/school. No durable calendar cache
is implemented. Calendar content is parsed in a disposable subprocess with a
20-second deadline, separate from HTTP requests, so recurrence expansion cannot
block the dashboard event loop. A combined live refresh took about 13 seconds
on the deployment host; dashboard requests wait for this refresh every five
minutes, while intervening requests use cached data. No private files or parser
error text are saved.
