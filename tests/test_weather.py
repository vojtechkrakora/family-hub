"""Synthetic model forecasts, never household data or external requests."""

import asyncio
from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from homeboard.integrations.models import WeatherData
from homeboard.integrations.service import CachedIntegration
from homeboard.integrations.weather import WeatherProvider, clothing, parse_weather
from homeboard.main import create_app
from homeboard.providers import PRAGUE

NOW = datetime(2026, 10, 22, 7, 30, tzinfo=PRAGUE)


def forecast(now=NOW):
    start = int(now.timestamp()) // 3600 * 3600
    return {
        "current": {
            "time": int(now.timestamp()),
            "temperature_2m": 9,
            "apparent_temperature": 8,
            "weather_code": 3,
        },
        "hourly": {
            "time": [start + i * 3600 for i in range(5)],
            "apparent_temperature": [8, 6, 9, 10, 12],
            "precipitation_probability": [0, 10, 60, 20, 0],
            "precipitation": [0, 0, 0, 0, 0],
        },
    }


@pytest.mark.parametrize(
    "feels,expected",
    [
        (-5, ["winter-coat", "hat"]),
        (5, ["jacket", "hat"]),
        (7, ["jacket"]),
        (12, ["hoodie"]),
        (20, ["tshirt"]),
    ],
)
def test_layers_and_thresholds(feels, expected):
    assert clothing(feels, False) == expected
    assert clothing(feels, True) == expected + ["raincoat"]


def test_forecast_uses_coldest_upcoming_feels_like_and_rain_probability():
    result = WeatherData.model_validate(parse_weather(forecast(), NOW))
    assert result.minimum_feels_like == 6
    assert result.clothing == ["jacket", "hat", "raincoat"]


@pytest.mark.parametrize(
    "now",
    [datetime(2026, 10, 22, 23, 30, tzinfo=PRAGUE), datetime(2026, 10, 25, 2, 30, tzinfo=PRAGUE)],
)
def test_timestamp_window_across_midnight_and_dst(now):
    assert parse_weather(forecast(now), now)["wet"]


@pytest.mark.parametrize("bad", [None, float("nan"), 1000, True])
def test_invalid_temperature_rejected(bad):
    payload = forecast()
    payload["current"]["temperature_2m"] = bad
    with pytest.raises((ValueError, TypeError)):
        parse_weather(payload, NOW)


def test_old_model_and_incomplete_forecast_are_rejected():
    payload = forecast()
    payload["current"]["time"] -= 7200
    with pytest.raises(ValueError):
        parse_weather(payload, NOW)
    payload = forecast()
    payload["hourly"]["time"] = []
    with pytest.raises(ValueError):
        parse_weather(payload, NOW)


def test_weather_failure_keeps_bus_dashboard_working(monkeypatch):
    monkeypatch.setenv("WEATHER_SOURCE", "open_meteo")

    async def fail(self, now):
        raise httpx.ReadTimeout("offline")

    monkeypatch.setattr(WeatherProvider, "fetch", fail)
    with TestClient(create_app()) as client:
        data = client.get("/api/dashboard").json()
        assert data["integrations"]["weather"]["status"] == "unavailable"
        assert data["weather"] is None
        assert data["transport"]["departures"]


def test_last_forecast_is_cached_and_marked_stale(monkeypatch):
    clock = [0]
    monkeypatch.setattr("homeboard.integrations.service.monotonic", lambda: clock[0])

    class Provider:
        source = "live"

        async def fetch(self, now):
            if clock[0]:
                raise ValueError("offline")
            return parse_weather(forecast(), now)

    cached = CachedIntegration("weather", Provider(), WeatherData, 900)

    async def run():
        good = await cached.snapshot(NOW)
        clock[0] = 901
        old = await cached.snapshot(NOW)
        assert old["data"] == good["data"]
        assert old["status"] == "stale"

    asyncio.run(run())
