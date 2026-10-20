# Homeboard

A local family dashboard for a Synology NAS and a living-room television.

## Current milestone: local proof of concept

The dashboard shows **fictional sample data only**: a bus departure countdown,
a visual morning routine, homework and today's family agenda.
The interface is entirely in Czech, with large local SVG illustrations for
children who cannot read: relax, get dressed, put shoes on, and leave together.
It refreshes automatically, marks connection failures and suppresses countdowns
while data is stale. The clock uses server time in Europe/Prague.

No transport, Bakaláři, calendar or TV service is connected. Demo buses depart
on quarter-hour boundaries, including nights and weekends; these are not real
timetables. Homework and agenda are synthetic examples for the current day.

## Local development (macOS)

Requires Python 3.10 or later.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn homeboard.main:app --host 127.0.0.1 --port 8091 --reload
```

Open http://localhost:8091. No frontend build or external credentials are needed.
For a household-device test, replace `127.0.0.1` with your Mac's private LAN IP
and open `http://<mac-lan-ip>:8091` from a device on the same network. Allow the
port in the local firewall if needed. Keep the computer awake during the test.

## Docker Compose / Synology

Requires Docker with the Compose plugin (Synology Container Manager on supported
NAS models). Actual NAS deployment must still be tested.

```sh
cp .env.example .env
docker compose up --build -d
docker compose ps
docker compose logs --tail 50
```

The default bind address is loopback. For access from your TV or phone, set
`HOMEBOARD_BIND_IP` in `.env` to your NAS's private LAN address, then recreate
the container with `docker compose up -d`. Open `http://<nas-lan-ip>:8091`.
Do not configure router port forwarding. There is no authentication in this
read-only, fictional-data POC. Add authentication before exposing private data
or state-changing endpoints.

Stop with `docker compose down`. No persistent data exists in this milestone.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOMEBOARD_BIND_IP` | `127.0.0.1` | Compose host bind address |
| `HOMEBOARD_PORT` | `8091` | Compose host port |
| `WALKING_MINUTES` | `1` | Time to the stop outside the house, integer 0–120 |
| `DRESSING_MINUTES` | `10` | Getting dressed, integer 1–120 |
| `SHOES_MINUTES` | `3` | Putting shoes on, integer 1–120 |

Compose reads `.env` automatically. Local Python execution reads process
environment variables, not `.env`; for example:

```sh
DRESSING_MINUTES=12 SHOES_MINUTES=3 WALKING_MINUTES=1 uvicorn homeboard.main:app --port 8091
```

Invalid settings fail at startup. Timezone is Europe/Prague. The browser polls
every 15 seconds after each completed request, with an 8-second timeout, and
updates countdowns every second. After a failed request or 45 seconds without a
successful response, existing examples stay visible with a stale-data warning.
No external fonts, assets or services are needed after dependency installation.

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
- `homeboard/providers.py`: provider boundary and explicit mock implementation.
- `homeboard/static/`: plain HTML, CSS and JavaScript.
- `tests/`: isolated automated tests.
- `docs/architecture.md`: decisions and remaining technical risks.
- `docs/tv-validation.md`: actual television validation checklist.

Next: manually open the dashboard on the LG 55SK8100PLA and validate readability
and browser behavior; then investigate and test power-on, pairing, browser launch
and overnight automation. Do not treat desktop success as proof of TV support.

## POC verification record

Verified locally on 2026-10-20:

- Python 3.10: 36 pytest tests passed; Ruff lint and formatting checks passed.
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
The demo quarter-hour schedule still rolls to the next sample bus on refresh.
Real departure selection and child-specific progress are outside this POC.

`WARNING_MINUTES` has been replaced by `DRESSING_MINUTES` and `SHOES_MINUTES`;
update any existing local environment settings. Source code and engineering
documentation remain English; all family-facing copy and sample data are Czech.
