"""Bounded calendar normalization, also run as a disposable parser subprocess."""

import json
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import recurring_ical_events
from icalendar import Calendar

from homeboard.providers import PRAGUE


def aware(value: date | datetime, zone: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=zone) if value.tzinfo is None else value.astimezone(PRAGUE)
    return datetime.combine(value, time.min, PRAGUE)


def parse_calendar(content: str, name: str, now: datetime) -> list[dict]:
    calendar = Calendar.from_ical(content)
    if calendar.name != "VCALENDAR":
        raise ValueError("Invalid calendar root")
    zone = ZoneInfo(str(calendar.get("X-WR-TIMEZONE", "Europe/Prague")))
    components = calendar.walk("VEVENT")
    if len(components) > 10000:
        raise ValueError("Too many calendar components")
    for event in components:
        if event.errors or not event.get("UID"):
            raise ValueError("Invalid calendar component")
        start = event.get("DTSTART")
        if start is None and str(event.get("STATUS", "")).upper() != "CANCELLED":
            raise ValueError("Missing event start")
        if (
            start is not None
            and start.params.get("TZID")
            and getattr(start.dt, "tzinfo", None) is None
        ):
            raise ValueError("Unknown event timezone")
    start_day = datetime.combine(now.astimezone(PRAGUE).date(), time.min, PRAGUE)
    stop_day = start_day + timedelta(days=2)
    events = []
    # Expansion is confined to two days and a killable process, including bad RRULEs.
    for event in recurring_ical_events.of(calendar).between(start_day, stop_day):
        if str(event.get("STATUS", "")).upper() == "CANCELLED":
            continue
        raw_start = event.decoded("DTSTART")
        all_day = not isinstance(raw_start, datetime)
        start = aware(raw_start, zone)
        raw_end = event.decoded("DTEND", None)
        end = (
            aware(raw_end, zone)
            if raw_end is not None
            else start + (event.decoded("DURATION", timedelta(days=1) if all_day else timedelta()))
        )
        if end.timestamp() < start.timestamp():
            raise ValueError("Event ends before start")
        if start >= stop_day or (end <= start_day and start < start_day):
            continue
        events.append(
            {
                "title": str(event.get("SUMMARY", "Bez názvu"))[:500],
                "calendar": name,
                "starts_at": start.isoformat(),
                "ends_at": end.isoformat(),
                "all_day": all_day,
            }
        )
        if len(events) > 100:
            raise ValueError("Too many expanded events")
    return events


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        now = datetime.fromisoformat(payload["now"])
        events = []
        for feed in payload["feeds"]:
            events.extend(parse_calendar(feed["content"], feed["name"], now))
        if len(events) > 100:
            raise ValueError("Too many combined events")
        print(json.dumps({"events": events}))
    except Exception:  # noqa: BLE001 - Never emit private parser input or library errors.
        # Library errors can contain private event content. Emit no exception text.
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
