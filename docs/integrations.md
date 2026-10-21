# Integration preparation

Research checked on 2026-10-20. Reading documentation is not a successful
integration test. The IDESKA departure board is enabled by default, with a COMETT scheduled fallback.
Both scheduled pages and the IDESKA departure board have been checked against live public responses.

## Implemented foundation

Three independent provider slots supply transport, school and calendar data.
Each async provider implements `fetch(now)` and declares `source` as `mock`,
`scheduled` or `live`. These describe provenance, not availability.

Internal Pydantic schemas validate normalized responses, reject unknown fields
and require timezone-aware departures/events. They are **Homeboard contracts**,
not guessed vendor response schemas. An adapter must explicitly translate a
verified external response into its contract and omit credentials.

Each integration returns `status` (`available`, `stale`, `unavailable`, `disabled`),
`source` and `last_success`. Empty data is a successful result, not a failure.
The dashboard response remains HTTP 200 for partial outages. `/health` reports
process liveness only. Cached school/calendar content stays visible with a stale
indicator; unavailable bus data never produces a morning action prompt.

Refresh intervals are 300 seconds for COMETT, 30 for IDESKA/mock transport and 300 for school and
calendar, evaluated on dashboard requests. Fetches run concurrently, with a
7-second integration deadlines and 30-second retry delay after transport/calendar failure (300 seconds for school).
Concurrent requests share one refresh per integration. Real adapters must use
cancellable async network I/O, enforce HTTP timeouts/response-size limits, and
handle authentication, rate limiting and response decoding. These are adapter
requirements, not features already verified against a vendor.

The cache is per-process memory and disappears on restart. Use a single worker
for now. Durable SQLite caching and vendor-specific retry policies remain future
work. Integration failure logs contain only the integration identifier, never
raw exception text, response bodies, tokens or feed URLs.

`TRANSPORT_SOURCE` accepts `ideska` (default), `comett`, `mock` and `disabled`. School also accepts `bakalari`; calendar accepts `google_ics`, `mock` and `disabled`. An unsupported value fails startup; it never silently
falls back to fabricated data. The UI labels each source independently.

## Transportation: COMETT scheduled adapter

The family confirmed lines **43 and 45** from Lipová alej and the usual **07:34**
line 45 departure. Homeboard selects the earliest future service across both lines.

Sources checked with actual HTTP requests on 2026-10-20:

- [Line 43 stop timetable](https://www.comettplus.cz/cz/zastavkove-jizdni-rady-mhd/plana-nad-luznici-nad-hejtmanem-lipova-alej/smer-a-strkov/linka-43/)
- [Line 45 stop timetable](https://www.comettplus.cz/cz/zastavkove-jizdni-rady-mhd/plana-nad-luznici-nad-hejtmanem-lipova-alej/smer-a-strkov/linka-45/)

The page identifies the stop as Nad Hejtmanem Lipová alej and direction as Strkov.
We display that direction; continuation to the originally requested náměstí stop
has not been established. The operator's line 45 weekday table confirms 07:34.
Line 43's 06:58 service has date exclusions, including 29–30 October 2026.

The public [departure search](https://www.comettplus.cz/cz/odjezdy-mhd/) was also
tested using its visible GET form fields. For 2026-10-28 at 06:00, it returned
weekday-like departures inconsistent with the stop table's Sunday/holiday column.
**The implementation does not use that search result.** It selects the holiday
column using [python-holidays' Czech calendar](https://holidays.readthedocs.io/en/latest/auto_gen_docs/czechia/)
and parses published exclusions from the timetable. This discrepancy should be
rechecked against the operator before relying on holiday travel.

`comett.py` reads only the two fixed public HTML pages, concurrently, with a 2.5s
HTTP timeout, a 2 MB response cap and no automatic redirects. The shared integration
layer imposes a 7s transport deadline, refreshes at most every 5 minutes and retries failed
fetches after 30 seconds. Either missing line invalidates the combined result.
No arbitrary upstream URLs, credentials, private API endpoints or scraping of
vehicle positions are introduced.

The parser validates page identity/date, validity, four known day columns and all
24 hourly rows. Unknown routes/service codes or changed schema fail closed. The
normalized metadata distinguishes `scheduled` from `live`; no delays are claimed.
Current cached data is in memory only. A connection failure suppresses countdowns;
there is no persistent offline schedule yet. Eight days are searched, subject to
explicit validity limits; no-end-date schedules are assumed unchanged within that
window until the next fetch. Temporary disruptions are not independently checked.

## IDESKA reported delay estimates

The official [IDESKA website](https://www.ideska.info/) links to the public
[MPV departure board](https://www.mpvnet.cz/jikord/tab?cat=2&subCat=0&stopNum=62683)
and [vehicle map](https://mpvnet.cz/jikord/map). On 2026-10-20, the board returned
stop 62683, lines 43/45 toward Strkov, and a 3-minute delay for line 43 trip 163
(scheduled 14:38), with a link to its vehicle on the map.

The adapter follows the board's public JavaScript POST request to
`/jikord/tab/departures` with `isDepartures` and the JSON-encoded `StopKey`.
This is an **unofficial, undocumented web interface**, not a supported API contract.
It needs no credentials. Refresh is every 30 seconds, matching the public board.
Only lines 43/45 toward Strkov are selected. The estimate is scheduled time plus
reported delay; ordering uses that estimate, retaining delayed services after their
scheduled time. Blank delay means unknown, never zero. Unknown markup or delay
notation fails closed. The response does not supply a vehicle observation timestamp:
`reported_at` means board retrieval time, not GPS measurement time.

The UI shows an estimated time, reported delay and original schedule. Morning
preparation follows the estimate. This cannot predict when railway barriers open;
the countdown can move as new delay reports arrive. Actual stop arrival versus
departure and real-world accuracy still need morning observation on site.

On board error or empty matching services,
the adapter uses COMETT and labels the result as schedule without live delay.
There is no time-of-day cutoff for live departures or GPS. Clock-only times are
resolved against yesterday, today and tomorrow in Europe/Prague, including the
reported delay as elapsed minutes. Exactly one future instant within six hours
must fit; distant, nonexistent or ambiguous DST times are omitted. If none remain,
the dated COMETT timetable is used. The GPS tracker uses the scheduled departure
timestamp in its trip key, so crossing midnight does not reset the selected trip.
If both sources fail, cached data is marked stale and action countdowns disappear.
The 7-second transport deadline includes fallback. Departure-board freshness beyond retrieval time is not verifiable. The separate
GPS feed now provides its own observation time; see below. A local fixed SVG minimap now renders this selected position.

## Bakaláři

The community-maintained [API v3 analysis](https://github.com/bakalari-api/bakalari-api-v3)
is unofficial. Its [endpoint inventory](https://github.com/bakalari-api/bakalari-api-v3/blob/master/endpoints.md)
includes homework, actual timetable and substitutions. The older API v1 repository
explicitly redirects readers to v3. A possible Python client to evaluate is
[bakapi](https://github.com/mvolfik/bakapi); it is not installed or selected yet.

The first adapter is implemented for one account, disabled by default (`SCHOOL_SOURCE=mock`).
Public verification on 2026-10-20: `https://zsplana.bakalari.cz/api/3` returned
API 3.52.1; `/api/3/homeworks` without authentication returned 401. Authenticated login, homework retrieval and normalization were subsequently
verified with the locally configured household account on the same date.

The [community login protocol](https://github.com/bakalari-api/bakalari-api-v3/blob/master/login.md)
documents `/api/login`, `client_id=ANDR`, password and refresh-token grants.
The [homework response](https://github.com/bakalari-api/bakalari-api-v3/blob/master/moduly/homework.md)
documents `/api/3/homeworks`, date range parameters, subject, content, DateEnd,
Done and Closed. The adapter validates required fields; schema changes produce
stale/unavailable status rather than a misleading empty list. It strips HTML,
never follows attachment links, and never changes completion/read state.

Each HTTPS request has a 2-second timeout and 2 MB decoded-body cap. Redirects
are refused. The school fetch has a 25-second overall deadline. Tokens are held
only in memory, rotated on refresh, and retried once after an unauthorized
homework response. Invalid refresh tokens fall back once to password login.
Rejected credentials impose a 15-minute cooldown. Rate limits honor numeric
Retry-After within 5–60 minutes. Other school refresh/retry intervals are five
minutes. The common cache retains last-success data and logs only safe identifiers.

Setup stores credentials locally outside Git/build context. Docker receives JSON
through a process environment set by the startup helper; ordinary local execution
reads the protected file. Enabling this adapter requires a separate dashboard
password and protects HTML, assets and API with HTTP Basic authentication (health
is exempt). Use HTTPS for LAN access. Configuration errors omit input values.
No real credentials or student data have been used in automated tests.

Local credentials have been supplied through the interactive setup. Authenticated
retrieval and the actual homework shape were verified without logging response
bodies. The running household instance uses the live provider and protected dashboard. One account only; if the parent account requires child selection,
that must be verified before extending the adapter. Timetable and announcements
remain subsequent increments. See README for setup and visible-task limits.

## Calendar

Google documents a [secret iCal feed](https://support.google.com/calendar/answer/37648?hl=en-GB)
for private calendar access. Availability can depend on account/admin settings.
An ICS reader is used because the dashboard is read-only;
OAuth is an alternative if feed access is unsuitable.

The Google-only ICS adapter is now implemented (`CALENDAR_SOURCE=google_ics`),
and retrieval from three household feeds was verified on 2026-10-21, including
authenticated dashboard rendering. The combined refresh took about 13 seconds
on the deployment host. Up to five HTTPS Google
calendar feeds are configured in protected local JSON, with secret URLs never
returned to the frontend. Only calendar.google.com/www.google.com calendar/ical
paths ending in basic.ics are accepted, with no redirects, embedded credentials,
query or fragment. Other ICS hosts and OAuth remain outside this increment.

`icalendar` 6.x and `recurring-ical-events` 3.8.2 expand recurrence rules rather
than a custom partial RRULE implementation. References:
[recurrence library](https://recurring-ical-events.readthedocs.io/en/v3.8.2/).
Synthetic tests cover weekly repetition across Prague DST, EXDATE, moved and
cancelled occurrences, UTC/floating time, exclusive all-day ends, overnight overlap,
multiple calendars, invalid feeds, HTTP errors and parser termination.

Downloads run concurrently with 3-second HTTP timeouts and a 2 MB cap per feed.
One disposable parser process handles the combined feeds with a 20-second deadline;
it is killed/reaped on timeout or cancellation and emits no private error text.
At most 100 normalized events across two days are accepted. Oversized, unsupported
or malformed feeds fail closed and retain the existing shared cache as stale.
The calendar integration has a 25-second overall deadline and 5-minute refresh/retry
interval. HTTP 429 numeric Retry-After is honored within 5–60 minutes.

Only title, configured calendar label, start/end and all-day status leave the
backend. The existing Homeboard login protects the agenda; school configuration
currently supplies this password even for calendar-only operation. Secret links
and raw event bodies must not appear in logs, fixtures or diagnostic screenshots.
See README for local setup, TV limits and unsupported OAuth/non-Google feeds.

## LG webOS

[Home Assistant's webOS documentation](https://www.home-assistant.io/integrations/webostv/)
and [aiowebostv](https://github.com/home-assistant-libs/aiowebostv) are useful primary
implementation references. The current aiowebostv README requires Python 3.11+;
Homeboard's local baseline is still 3.10, while its Docker image uses 3.12.
Resolve that compatibility before adding this dependency.

TV control is separate from read-only dashboard data providers. No TV commands,
network scans, pairing attempts, wake packets or scheduling have been added.
The LG 55SK8100PLA's actual capabilities remain unverified. Next inputs are the
TV's private LAN address, firmware/webOS version and Ethernet/Wi-Fi connection;
pairing should be tested with someone at the TV. Follow `tv-validation.md`,
including overnight standby and launching the specific dashboard URL.


## GPS progress and crossing inference

The public map JavaScript's `/jikord/map/mapData` POST was verified on 2026-10-20.
It accepts viewport coordinates, zoom and `showStops`. The implemented fixed viewport
covers the local bus approach. One request per transport refresh (normally 30 seconds, 10 near/beyond the crossing) is
made only when the selected board departure has a trip identifier. GPS failure
never discards a successful departure-board result. Raw registration/vehicle data
is not returned to the frontend or logged.

Observed transmitter fields: `x` latitude, `y` longitude, `dt` local date, `tm`
local time, `cat` category, and `cn` pipe-delimited connection identity. Matching
requires category 2, exact route 395043/395045, exact trip and Strkov terminus.
An ambiguous match is rejected. These fields are unofficial and may change.
Only fixes aged 0–75 seconds are accepted; the frontend independently expires them.
Repeated timestamps cannot establish elapsed stationary time.

The user-supplied [St. Barbora place](https://mapy.com/cs/zakladni?source=base&id=2240752)
has GPS **49.3490900, 14.7085142**, read from the place's GPS control. The link's
x/y coordinates are viewport center, not the chapel location. Crossing P5647 is
approximately **49.349325, 14.70819**. Road geometry derives from
[OpenStreetMap](https://www.openstreetmap.org/way/211314930), © OpenStreetMap
contributors, licensed under [ODbL](https://www.openstreetmap.org/copyright).
The simplified geometry in `vehicle.py` is provided under that database license.

States are conservative inferences, not direct barrier telemetry:
- In Planá: both adjacent stop names in the matched connection are in Planá;
  this is not an administrative-boundary test.
- At crossing: within 100 m of P5647 before the confirmed southeast zone.
- Waiting: fresh successive observations remain within 25 m of an anchor there
  for at least 60 seconds, with no observation gap over 75 seconds. This may be
  traffic or a stop; the UI does not claim the barriers are closed.
- On Strkovská / beyond crossing: two distinct observations at least 40 m southeast
  of Barbora, within 45 m of the road polyline. Crossing confirmation persists for
  that selected trip while fresh fixes remain available, preventing GPS jitter.

History is in memory for one selected service date/line/trip. Missing, backward or
widely separated observations reset evidence. A new selected trip starts fresh.
A confirmed crossing changes `relax` to `dress`, but never rolls back shoes/leaving
or delays an earlier time-based preparation warning. The UI shows planned and
estimated times separately; unknown estimate is a dash. These are stop departure
estimates from the board, not separately measured arrivals.

Geometry thresholds and practical timing require an actual morning drive-through
check. Automated tests verify boundaries, dwell, direction, identity, stale fixes,
duplicates, trip changes and failure isolation; they cannot verify barrier state.

### Adaptive polling

Fresh GPS states `crossing`, `waiting_crossing`, `passed` and `strkovska` for the
next future departure select a 10-second transport cache lifetime and a 10-second
browser refresh interval. Town/approaching, missing/stale/future-dated GPS, no
future departure or a different selected bus use normal intervals. API failures
retain the existing 30-second backend retry backoff; browser request failures
return to 15 seconds. Each browser schedules its next request after completion.
The shared cache lock still coalesces simultaneous requests from multiple devices.


### Minimap data

The public MPV `map/showStation/62683` response was checked for platform 1:
latitude 49.340534, longitude 14.721553. The crossing marker uses the established
P5647 coordinate. The static background is generated from the OSM API bounding
box 14.690,49.334,14.737,49.380 (retrieved 2026-10-20), with simplified roads,
railways, water and woodland. No map tiles are downloaded or redistributed.
The SVG and HTML share a 400×600 linear geographic projection; this is a local
orientation map, not a distance-measurement tool. Geometry attribution and ODbL
links are included in the page, generator and SVG metadata.

Only latitude/longitude and observation time of the matched selected service are
exposed, without registration numbers or raw transmitter records. Existing GPS
freshness and identity checks remain authoritative. The frontend remembers only
the current service's most recent coordinate, greys it after 75 seconds or a
source failure, and hides it after five minutes. No coordinates are persisted.
This display state does not feed the crossing classifier or morning routine.
