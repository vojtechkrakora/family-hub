from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from homeboard.domain import countdown, morning_routine
from homeboard.main import create_app
from homeboard.providers import MockProvider

PRAGUE = ZoneInfo("Europe/Prague")


@pytest.mark.parametrize(
    "seconds,minutes,leave,status",
    [
        (901, 16, 11, "comfortable"),
        (600, 10, 5, "prepare"),
        (301, 6, 1, "prepare"),
        (300, 5, 0, "leave_now"),
        (1, 1, 0, "leave_now"),
        (0, 0, 0, "departed"),
        (-1, 0, 0, "departed"),
    ],
)
def test_countdown_boundaries(seconds, minutes, leave, status):
    now = datetime(2026, 10, 20, 7, tzinfo=PRAGUE)
    result = countdown(now + timedelta(seconds=seconds), now, 5, 5)
    assert result == {"departure_minutes": minutes, "leave_minutes": leave, "status": status}


@pytest.mark.parametrize(
    "now,departure,expected",
    [
        ("2026-03-29T01:55:00+01:00", "2026-03-29T03:05:00+02:00", 10),
        ("2026-10-25T02:55:00+02:00", "2026-10-25T02:05:00+01:00", 10),
        ("2026-10-20T23:55:00+02:00", "2026-10-21T00:05:00+02:00", 10),
    ],
)
def test_clock_boundaries(now, departure, expected):
    now = datetime.fromisoformat(now).astimezone(PRAGUE)
    departure = datetime.fromisoformat(departure).astimezone(PRAGUE)
    assert countdown(departure, now, 0, 0)["departure_minutes"] == expected


def test_reject_naive_datetime():
    with pytest.raises(ValueError):
        countdown(datetime(2026, 1, 1), datetime(2026, 1, 1), 5, 5)


@pytest.mark.parametrize("value", ["-1", "121", "invalid"])
def test_invalid_config(monkeypatch, value):
    monkeypatch.setenv("WALKING_MINUTES", value)
    with pytest.raises(ValueError):
        create_app()


def test_mock_departure_stays_fixed_and_rolls_over():
    provider = MockProvider()
    now = datetime(2026, 10, 20, 23, 59, tzinfo=PRAGUE)
    first = provider.snapshot(now)
    assert first["transport"]["departures"][0] == "2026-10-21T00:00:00+02:00"
    assert provider.snapshot(now + timedelta(seconds=10))["transport"] == first["transport"]
    assert (
        provider.snapshot(now + timedelta(minutes=1))["transport"]["departures"][0]
        == "2026-10-21T00:15:00+02:00"
    )


def test_http_dashboard_and_assets(monkeypatch):
    monkeypatch.setenv("WALKING_MINUTES", "7")
    with TestClient(create_app()) as client:
        assert client.get("/health").json() == {"status": "ok", "mode": "mock"}
        assert "UKÁZKA · Smyšlené odjezdy" in client.get("/").text
        for asset in ["style.css", "app.js"]:
            assert client.get("/static/" + asset).status_code == 200
        response = client.get("/api/dashboard")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        data = response.json()
        assert data["source"] == "mock"
        assert data["walking_minutes"] == 7
        assert data["dressing_minutes"] == 10
        assert data["shoes_minutes"] == 3
        assert [stage["id"] for stage in data["routine"]] == ["relax", "dress", "shoes", "go"]
        assert data["timezone"] == "Europe/Prague"
        assert len(data["transport"]["departures"]) == 3
        assert data["transport"]["delay_minutes"] is None
        assert client.post("/api/dashboard").status_code == 405


def test_provider_failure_does_not_leak_secrets():
    class BrokenProvider:
        def snapshot(self, now):
            raise RuntimeError("secret-token")

    with TestClient(create_app(BrokenProvider())) as client:
        response = client.get("/api/dashboard")
        assert response.status_code == 503
        assert "secret-token" not in response.text
        assert client.get("/health").status_code == 200


@pytest.mark.parametrize(
    "seconds,stage",
    [
        (841, "relax"),
        (840, "dress"),
        (241, "dress"),
        (240, "shoes"),
        (61, "shoes"),
        (60, "go"),
        (1, "go"),
        (0, "waiting"),
        (-1, "waiting"),
    ],
)
def test_morning_stage_boundaries(seconds, stage):
    departure = datetime(2026, 10, 20, 7, 30, tzinfo=PRAGUE)
    routine = morning_routine(departure, 10, 3, 1)
    now_ms = (departure.timestamp() - seconds) * 1000
    current = next((item["id"] for item in routine if now_ms < item["until"]), "waiting")
    assert current == stage


@pytest.mark.parametrize("departure", ["2026-03-29T03:05:00+02:00", "2026-10-25T02:05:00+01:00"])
def test_routine_durations_across_dst(departure):
    departure = datetime.fromisoformat(departure).astimezone(PRAGUE)
    routine = morning_routine(departure, 10, 3, 1)
    boundaries = [stage["until"] for stage in routine]
    assert [boundaries[i + 1] - boundaries[i] for i in range(3)] == [600000, 180000, 60000]
    assert boundaries[-1] == departure.timestamp() * 1000


@pytest.mark.parametrize("name", ["DRESSING_MINUTES", "SHOES_MINUTES"])
@pytest.mark.parametrize("value", ["0", "-1", "121", "invalid"])
def test_invalid_preparation_settings(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        create_app()
