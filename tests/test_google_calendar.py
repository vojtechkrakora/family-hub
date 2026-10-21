"""Synthetic ICS fixtures only; secret calendar feeds are never contacted in tests."""

import asyncio
import json
from datetime import datetime

import httpx
import pytest
from pydantic import ValidationError

from homeboard.integrations.google_calendar import (
    CalendarSettings,
    GoogleCalendarProvider,
    load_calendar_settings,
    parse_feeds,
)
from homeboard.integrations.ics_parser import parse_calendar
from homeboard.providers import PRAGUE

NOW = datetime(2026, 10, 20, 7, tzinfo=PRAGUE)
URL = "https://calendar.google.com/calendar/ical/test/private-SYNTHETIC/basic.ics"


def feed(*events, zone="Europe/Prague"):
    return "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Homeboard tests//EN",
            "X-WR-TIMEZONE:" + zone,
            *events,
            "END:VCALENDAR",
            "",
        ]
    )


def event(*lines):
    return "\r\n".join(
        ["BEGIN:VEVENT", "UID:synthetic", "SUMMARY:Test event", *lines, "END:VEVENT"]
    )


def test_utc_conversion_and_floating_time():
    for start in ["DTSTART:20261020T070000Z", "DTSTART:20261020T090000"]:
        rows = parse_calendar(feed(event(start)), "Family", NOW)
        assert rows[0]["starts_at"].endswith("09:00:00+02:00")
        assert not rows[0]["all_day"]


def test_all_day_multiday_and_exclusive_end():
    content = feed(event("DTSTART;VALUE=DATE:20261019", "DTEND;VALUE=DATE:20261021"))
    assert parse_calendar(content, "Family", NOW)[0]["all_day"]
    assert not parse_calendar(content, "Family", NOW.replace(day=21))


def test_overnight_overlap_and_duration():
    content = feed(event("DTSTART;TZID=Europe/Prague:20261019T230000", "DURATION:PT3H"))
    result = parse_calendar(content, "Family", NOW)
    assert result[0]["ends_at"].endswith("02:00:00+02:00")


def test_weekly_recurrence_stays_at_local_time_across_dst():
    content = feed(
        event(
            "DTSTART;TZID=Europe/Prague:20261018T090000",
            "DTEND;TZID=Europe/Prague:20261018T100000",
            "RRULE:FREQ=WEEKLY;COUNT=3",
        )
    )
    result = parse_calendar(content, "Family", NOW.replace(day=25))
    assert result[0]["starts_at"] == "2026-10-25T09:00:00+01:00"


def test_exdate_and_moved_occurrence():
    original = event(
        "DTSTART;TZID=Europe/Prague:20261019T090000",
        "RRULE:FREQ=DAILY;COUNT=4",
        "EXDATE;TZID=Europe/Prague:20261020T090000",
    )
    moved = event(
        "RECURRENCE-ID;TZID=Europe/Prague:20261021T090000",
        "DTSTART;TZID=Europe/Prague:20261021T110000",
    )
    result = parse_calendar(feed(original, moved), "Family", NOW)
    assert len(result) == 1
    assert result[0]["starts_at"] == "2026-10-21T11:00:00+02:00"


def test_cancelled_occurrence_is_not_resurrected():
    original = event("DTSTART;TZID=Europe/Prague:20261019T090000", "RRULE:FREQ=DAILY;COUNT=4")
    cancelled = event(
        "RECURRENCE-ID;TZID=Europe/Prague:20261020T090000",
        "DTSTART;TZID=Europe/Prague:20261020T090000",
        "STATUS:CANCELLED",
    )
    result = parse_calendar(feed(original, cancelled), "Family", NOW)
    assert [r["starts_at"][:10] for r in result] == ["2026-10-21"]


def test_empty_calendar_is_success_but_html_is_not():
    assert parse_calendar(feed(), "Family", NOW) == []
    with pytest.raises(ValueError):
        parse_calendar("<html>Login page</html>", "Family", NOW)


@pytest.mark.parametrize(
    "url",
    [
        "http://calendar.google.com/calendar/ical/a/basic.ics",
        "https://evil.invalid/calendar/ical/a/basic.ics",
        "https://calendar.google.com.evil.invalid/calendar/ical/a/basic.ics",
        "https://user:secret@calendar.google.com/calendar/ical/a/basic.ics",
    ],
)
def test_only_google_feed_hosts_allowed(url):
    with pytest.raises(ValidationError):
        CalendarSettings(calendars=[{"name": "Family", "url": url}])


def test_multiple_feeds_and_subprocess_normalization():
    requested = []

    def respond(request):
        requested.append(request)
        return httpx.Response(200, text=feed(event("DTSTART:20261020T070000Z")))

    settings = CalendarSettings(calendars=[{"name": name, "url": URL} for name in ["One", "Two"]])
    result = asyncio.run(GoogleCalendarProvider(settings, httpx.MockTransport(respond)).fetch(NOW))
    assert len(requested) == 2
    assert [e["calendar"] for e in result["events"]] == ["One", "Two"]
    assert "SYNTHETIC" not in json.dumps(result)


@pytest.mark.parametrize("status", [302, 403, 429, 503])
def test_failure_is_not_an_empty_success_and_redirects_not_followed(status):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, headers={"Location": "https://evil.invalid/"})

    settings = CalendarSettings(calendars=[{"name": "Family", "url": URL}])
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(GoogleCalendarProvider(settings, httpx.MockTransport(respond)).fetch(NOW))
    assert len(calls) == 1


def test_private_parser_errors_are_redacted():
    with pytest.raises(ValueError) as error:
        asyncio.run(parse_feeds([{"name": "Family", "content": "PRIVATE-CALENDAR-CONTENT"}], NOW))
    assert "PRIVATE" not in str(error.value)


def test_invalid_settings_do_not_expose_feed_url(monkeypatch):
    monkeypatch.setenv(
        "GOOGLE_CALENDAR_CONFIG_JSON",
        json.dumps({"calendars": [{"name": "Family", "url": "PRIVATE-URL"}]}),
    )
    with pytest.raises(ValueError) as error:
        load_calendar_settings()
    assert "PRIVATE-URL" not in str(error.value)


def test_parser_timeout_terminates_worker(monkeypatch):
    import homeboard.integrations.google_calendar as module

    class Worker:
        returncode = None
        killed = False

        async def communicate(self, data):
            raise asyncio.TimeoutError

        def kill(self):
            self.killed = True
            self.returncode = -9

        async def wait(self):
            return self.returncode

    worker = Worker()

    async def spawn(*args, **kwargs):
        return worker

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(parse_feeds([], NOW))
    assert worker.killed


def test_oversized_feed_is_rejected():
    def respond(request):
        return httpx.Response(200, content=b"x" * 2_000_001)

    settings = CalendarSettings(calendars=[{"name": "Family", "url": URL}])
    with pytest.raises(ValueError, match="too large"):
        asyncio.run(GoogleCalendarProvider(settings, httpx.MockTransport(respond)).fetch(NOW))
