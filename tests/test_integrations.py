import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from homeboard.integrations.models import CalendarData, SchoolData, TransportData
from homeboard.integrations.service import CachedIntegration
from homeboard.main import create_app
from homeboard.providers import (
    PRAGUE,
    MockCalendarProvider,
    MockSchoolProvider,
    MockTransportProvider,
)

NOW = datetime(2026, 10, 20, 7, tzinfo=PRAGUE)


class FailingProvider:
    source = "live"

    async def fetch(self, now):
        raise RuntimeError("private-token-do-not-log")


def integrations(transport=None, school=None, calendar=None):
    return {
        "transport": CachedIntegration(
            "transport", transport or MockTransportProvider(), TransportData, 15
        ),
        "school": CachedIntegration("school", school or MockSchoolProvider(), SchoolData, 300),
        "calendar": CachedIntegration(
            "calendar", calendar or MockCalendarProvider(), CalendarData, 300
        ),
    }


def test_school_failure_isolated_and_redacted(caplog):
    with TestClient(create_app(integrations(school=FailingProvider()))) as client:
        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert data["integrations"]["school"]["status"] == "unavailable"
        assert data["integrations"]["school"]["last_success"] is None
        assert data["transport"]["departures"]
        assert data["events"]
        assert data["routine"]
        assert data["homework"] == []
        assert "private-token" not in response.text
        assert "private-token" not in caplog.text


def test_transport_failure_suppresses_action_but_preserves_other_sections():
    with TestClient(create_app(integrations(transport=FailingProvider()))) as client:
        data = client.get("/api/dashboard").json()
        assert data["transport"] is None
        assert data["routine"] == []
        assert data["homework"] and data["events"]
        assert client.get("/health").json() == {"status": "ok"}


def test_cache_ttl_failure_backoff_and_recovery(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("homeboard.integrations.service.monotonic", lambda: clock[0])

    class Provider:
        source = "live"
        calls = 0
        fail = False

        async def fetch(self, now):
            self.calls += 1
            if self.fail:
                raise TimeoutError("private-url")
            return {"homework": []}

    async def run():
        provider = Provider()
        cached = CachedIntegration("school", provider, SchoolData, 300)
        first = await cached.snapshot(NOW)
        clock[0] = 299
        assert await cached.snapshot(NOW) == first
        assert provider.calls == 1
        clock[0] = 300
        provider.fail = True
        stale = await cached.snapshot(NOW + timedelta(minutes=5))
        assert stale["status"] == "stale"
        assert stale["last_success"] == first["last_success"]
        assert stale["data"] == {"homework": []}
        clock[0] = 329
        await cached.snapshot(NOW)
        assert provider.calls == 2
        clock[0] = 330
        provider.fail = False
        recovered = await cached.snapshot(NOW + timedelta(minutes=6))
        assert recovered["status"] == "available"
        assert recovered["last_success"] != first["last_success"]
        assert provider.calls == 3

    asyncio.run(run())


def test_timeout_cancels_fetch():
    class SlowProvider:
        source = "live"
        cancelled = False

        async def fetch(self, now):
            try:
                await asyncio.sleep(60)
            finally:
                self.cancelled = True

    async def run():
        provider = SlowProvider()
        cached = CachedIntegration("school", provider, SchoolData, 300, timeout_seconds=0.01)
        result = await cached.snapshot(NOW)
        assert result["status"] == "unavailable"
        assert provider.cancelled

    asyncio.run(run())


def test_concurrent_requests_share_one_fetch():
    class Provider:
        source = "live"
        calls = 0

        async def fetch(self, now):
            self.calls += 1
            await asyncio.sleep(0.01)
            return {"homework": []}

    async def run():
        provider = Provider()
        cached = CachedIntegration("school", provider, SchoolData, 300)
        snapshots = await asyncio.gather(*(cached.snapshot(NOW) for _ in range(5)))
        assert provider.calls == 1
        assert all(item["status"] == "available" for item in snapshots)

    asyncio.run(run())


@pytest.mark.parametrize(
    "payload",
    [
        {"origin": "A", "destination": "B", "departures": ["not-a-date"]},
        {"origin": "A", "destination": "B", "departures": ["2026-10-20T07:00:00"]},
        {"origin": "A", "destination": "B", "departures": [], "token": "secret"},
    ],
)
def test_invalid_external_data_rejected(payload):
    class InvalidProvider:
        source = "scheduled"

        async def fetch(self, now):
            return payload

    with TestClient(create_app(integrations(transport=InvalidProvider()))) as client:
        data = client.get("/api/dashboard").json()
        assert data["integrations"]["transport"]["status"] == "unavailable"
        assert data["routine"] == []


def test_departures_sorted_and_past_removed():
    class ScheduleProvider:
        source = "scheduled"

        async def fetch(self, now):
            return {
                "origin": "A",
                "destination": "B",
                "departures": [
                    now + timedelta(minutes=30),
                    now - timedelta(minutes=1),
                    now + timedelta(minutes=10),
                ],
            }

    with TestClient(create_app(integrations(transport=ScheduleProvider()))) as client:
        data = client.get("/api/dashboard").json()
        assert len(data["transport"]["departures"]) == 2
        assert data["transport"]["departure_minutes"] == 10
        assert data["integrations"]["transport"]["source"] == "scheduled"


def test_empty_timetable_is_not_failure():
    class EmptyProvider:
        source = "scheduled"

        async def fetch(self, now):
            return {"origin": "A", "destination": "B", "departures": []}

    with TestClient(create_app(integrations(transport=EmptyProvider()))) as client:
        data = client.get("/api/dashboard").json()
        assert data["routine"] == []
        assert data["integrations"]["transport"]["status"] == "available"


def test_disabled_sources(monkeypatch):
    for name in ("TRANSPORT", "SCHOOL", "CALENDAR"):
        monkeypatch.setenv(name + "_SOURCE", "disabled")
    with TestClient(create_app()) as client:
        data = client.get("/api/dashboard").json()
        assert all(state["status"] == "disabled" for state in data["integrations"].values())
        assert data["transport"] is None
        assert data["routine"] == []


def test_unimplemented_source_fails_at_startup(monkeypatch):
    monkeypatch.setenv("TRANSPORT_SOURCE", "jikord")
    with pytest.raises(ValueError, match="Unsupported"):
        create_app()


def test_stale_transport_retains_metadata_but_never_generates_routine():
    source = CachedIntegration("transport", MockTransportProvider(), TransportData, 0)
    slots = integrations()
    slots["transport"] = source
    with TestClient(create_app(slots)) as client:
        first = client.get("/api/dashboard").json()
        source.provider = FailingProvider()
        failed = client.get("/api/dashboard").json()
        assert failed["integrations"]["transport"]["status"] == "stale"
        assert (
            failed["integrations"]["transport"]["last_success"]
            == first["integrations"]["transport"]["last_success"]
        )
        assert failed["routine"] == []
        assert "departure_minutes" not in failed["transport"]


def test_transport_fast_cache_interval_and_return_to_normal(monkeypatch):
    from homeboard.integrations.vehicle import needs_fast_refresh

    clock = [0.0]
    monkeypatch.setattr("homeboard.integrations.service.monotonic", lambda: clock[0])

    class NearbyProvider:
        source = "live"
        state = "crossing"
        calls = 0

        async def fetch(self, now):
            self.calls += 1
            departure = (now + timedelta(minutes=5)).isoformat()
            return {
                "origin": "Lipová alej",
                "destination": "Strkov",
                "departures": [departure],
                "departure_details": {
                    departure: {
                        "line": "45",
                        "destination": "Strkov",
                        "progress": {
                            "state": self.state,
                            "observed_at": now.isoformat(),
                            "passed_crossing": False,
                        },
                    }
                },
            }

    provider = NearbyProvider()
    cached = CachedIntegration(
        "transport",
        provider,
        TransportData,
        30,
        refresh_policy=lambda data, now: (
            10 if needs_fast_refresh(data.model_dump(mode="json"), now) else 30
        ),
    )

    async def scenario():
        await cached.snapshot(NOW)
        clock[0] = 9
        await cached.snapshot(NOW + timedelta(seconds=9))
        assert provider.calls == 1
        clock[0] = 10
        provider.state = "town"
        await cached.snapshot(NOW + timedelta(seconds=10))
        assert provider.calls == 2
        clock[0] = 20
        await cached.snapshot(NOW + timedelta(seconds=20))
        assert provider.calls == 2
        clock[0] = 40
        await cached.snapshot(NOW + timedelta(seconds=40))
        assert provider.calls == 3

    asyncio.run(scenario())
    provider.state = "crossing"
    with TestClient(create_app(integrations(transport=provider))) as client:
        assert client.get("/api/dashboard").json()["refresh_seconds"] == 10
    provider.state = "town"
    with TestClient(create_app(integrations(transport=provider))) as client:
        assert client.get("/api/dashboard").json()["refresh_seconds"] == 15


def test_calendar_includes_overnight_but_excludes_exclusive_midnight_end():
    class CalendarProvider:
        source = "live"

        async def fetch(self, now):
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return {
                "events": [
                    {
                        "title": "Overnight",
                        "calendar": "Family",
                        "starts_at": (midnight - timedelta(hours=1)).isoformat(),
                        "ends_at": (midnight + timedelta(hours=2)).isoformat(),
                    },
                    {
                        "title": "Yesterday",
                        "calendar": "Family",
                        "starts_at": (midnight - timedelta(days=1)).isoformat(),
                        "ends_at": midnight.isoformat(),
                        "all_day": True,
                    },
                    {
                        "title": "Soon",
                        "calendar": "Family",
                        "starts_at": (now + timedelta(minutes=10)).isoformat(),
                    },
                ]
            }

    with TestClient(create_app(integrations(calendar=CalendarProvider()))) as client:
        rows = client.get("/api/dashboard").json()["events"]
        assert [event["title"] for event in rows] == ["Overnight", "Soon"]
        assert rows[0]["time"] == "Probíhá"
        assert rows[1]["upcoming"]
