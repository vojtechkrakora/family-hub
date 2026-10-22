"""Open-Meteo model forecast for the household's town; no credentials required."""

import json
from datetime import datetime
from math import isfinite

import httpx

from homeboard.providers import PRAGUE

URL = "https://api.open-meteo.com/v1/forecast"
PARAMS = {
    "latitude": 49.35,
    "longitude": 14.72,
    "current": "temperature_2m,apparent_temperature,weather_code",
    "hourly": "apparent_temperature,precipitation_probability,precipitation",
    "forecast_days": 2,
    "timezone": "Europe/Prague",
    "timeformat": "unixtime",
}


def clothing(feels_like: float, wet: bool) -> list[str]:
    """Simple outer-layer suggestions, not a complete outfit or safety advice."""
    items = [
        "winter-coat"
        if feels_like < 5
        else "jacket"
        if feels_like < 12
        else "hoodie"
        if feels_like < 20
        else "tshirt"
    ]
    if feels_like < 7:
        items.append("hat")
    if wet:
        items.append("raincoat")
    return items


def number(value: object, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Missing weather value")
    if not isfinite(value) or not low <= value <= high:
        raise ValueError("Invalid weather value")
    return float(value)


def parse_weather(payload: dict, now: datetime) -> dict:
    current = payload["current"]
    stamp = number(current["time"], 0, 10**11)
    if not -300 <= now.timestamp() - stamp <= 3600:
        raise ValueError("Weather model time is not current")
    temperature = number(current["temperature_2m"], -60, 60)
    feels = number(current["apparent_temperature"], -80, 70)
    code = number(current["weather_code"], 0, 99)
    hourly = payload["hourly"]
    columns = [
        hourly[name]
        for name in ("time", "apparent_temperature", "precipitation_probability", "precipitation")
    ]
    if not all(isinstance(col, list) and len(col) == len(columns[0]) for col in columns):
        raise ValueError("Mismatched weather arrays")
    upcoming = []
    for time, apparent, probability, rain in zip(*columns):
        time = number(time, 0, 10**11)
        if now.timestamp() < time <= now.timestamp() + 3 * 3600:
            upcoming.append(
                (time, number(apparent, -80, 70), number(probability, 0, 100), number(rain, 0, 500))
            )
    if len(upcoming) != 3 or any(upcoming[i + 1][0] - upcoming[i][0] != 3600 for i in range(2)):
        raise ValueError("Incomplete three-hour forecast")
    low = min([feels] + [entry[1] for entry in upcoming])
    wet = code in {
        51,
        53,
        55,
        56,
        57,
        61,
        63,
        65,
        66,
        67,
        71,
        73,
        75,
        77,
        80,
        81,
        82,
        85,
        86,
        95,
        96,
        99,
    } or any(entry[2] >= 50 or entry[3] >= 0.2 for entry in upcoming)
    return {
        "temperature": temperature,
        "feels_like": feels,
        "minimum_feels_like": low,
        "wet": wet,
        "clothing": clothing(low, wet),
        "valid_until": datetime.fromtimestamp(stamp + 3600, PRAGUE).isoformat(),
    }


class WeatherProvider:
    source = "live"

    async def fetch(self, now: datetime) -> dict:
        async with (
            httpx.AsyncClient(timeout=3, follow_redirects=False) as client,
            client.stream("GET", URL, params=PARAMS) as response,
        ):
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 200_000:
                    raise ValueError("Weather response too large")
        return parse_weather(json.loads(body), now)
