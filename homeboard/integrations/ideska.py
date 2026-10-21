"""Unofficial adapter for the public IDESKA/MPV departure board."""

import json
import logging
import re
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from homeboard.integrations.comett import ComettProvider
from homeboard.integrations.vehicle import ProgressTracker, observation
from homeboard.providers import PRAGUE

BOARD = "https://www.mpvnet.cz/jikord/tab"
STOP = {"cat": 2, "subCat": 0, "stopNum": 62683}


def departure_time(
    clock: str, delay: int | None, now: datetime
) -> tuple[datetime, datetime] | None:
    """Resolve an undated board time only when one nearby future instant fits."""
    hour, minute = map(int, clock.split(":"))
    candidates = {}
    for offset in (-1, 0, 1):
        day = now + timedelta(days=offset)
        for fold in (0, 1):
            scheduled = day.replace(hour=hour, minute=minute, second=0, microsecond=0, fold=fold)
            # Reject nonexistent local times during the spring DST transition.
            roundtrip = datetime.fromtimestamp(scheduled.timestamp(), PRAGUE)
            if roundtrip.replace(tzinfo=None) != scheduled.replace(tzinfo=None):
                continue
            expected = datetime.fromtimestamp(scheduled.timestamp() + (delay or 0) * 60, PRAGUE)
            if 0 < expected.timestamp() - now.timestamp() <= 6 * 3600:
                candidates[scheduled.timestamp()] = (scheduled, expected)
    # Both folds of an ambiguous autumn time must not be guessed.
    return next(iter(candidates.values())) if len(candidates) == 1 else None


def parse_board(html: str, now: datetime) -> dict:
    now = now.astimezone(PRAGUE)
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one(".box-title")
    if title is None or "Nad Hejtmanem Lipová alej" not in title.get_text():
        raise ValueError("Unexpected departure board stop")
    details = {}
    for row in soup.select(".timetable-row"):
        cells = row.select(".timetable-item")
        if row.select_one(".timetable-header"):
            continue
        if len(cells) != 6:
            raise ValueError("Unexpected departure board columns")
        line_node = cells[0].select_one(".timetable-value > div")
        destination_node = cells[1].select_one(".timetable-value")
        if line_node is None or destination_node is None:
            raise ValueError("Missing departure identity")
        line = line_node.get_text(strip=True)
        destination = destination_node.get_text(" ", strip=True)
        if line not in {"43", "45"} or destination != "Planá n.Luž.,Strkov":
            continue
        clock = cells[3].select_one(".timetable-value")
        delay_node = cells[5].select_one(".timetable-value")
        if clock is None or delay_node is None:
            raise ValueError("Missing departure timing")
        value = clock.get_text(strip=True)
        if not re.fullmatch(r"\d{2}:\d{2}", value):
            raise ValueError("Unsupported dated departure")
        raw_delay = delay_node.get_text(strip=True)
        if raw_delay and not re.fullmatch(r"-?\d{1,3}", raw_delay):
            raise ValueError("Unknown delay notation")
        delay = int(raw_delay) if raw_delay else None
        if delay is not None and not -5 <= delay <= 180:
            raise ValueError("Unexpected delay")
        timing = departure_time(value, delay, now)
        if timing is None:
            continue
        scheduled, expected = timing
        trip_node = cells[0].select_one(".timetable-direction")
        trip = trip_node.get_text(strip=True) if trip_node else None
        key = expected.isoformat()
        details.setdefault(
            key,
            {
                "line": line,
                "trip": trip,
                "destination": "Strkov",
                "scheduled_at": scheduled.isoformat(),
                "delay_minutes": delay,
                "reported_at": now.isoformat() if delay is not None else None,
            },
        )
    return {
        "origin": "Lipová alej",
        "destination": "Strkov",
        "departures": sorted(details, key=lambda key: datetime.fromisoformat(key).timestamp()),
        "departure_details": details,
    }


class IdeskaProvider:
    source = "live"

    def __init__(self) -> None:
        self.fallback = ComettProvider()
        self.tracker = ProgressTracker()

    async def fetch(self, now: datetime) -> dict:
        try:
            async with httpx.AsyncClient(timeout=2, follow_redirects=False) as client:
                response = await client.post(
                    BOARD + "/departures",
                    headers={
                        "Referer": BOARD,
                        "Origin": "https://www.mpvnet.cz",
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    json={"isDepartures": True, "StopKey": json.dumps(STOP)},
                )
                response.raise_for_status()
                if len(response.content) > 1_000_000:
                    raise ValueError("Oversized board")
                result = parse_board(response.text, now)
                if result["departures"]:
                    first = result["departure_details"][result["departures"][0]]
                    fix = None
                    if first.get("trip"):
                        try:
                            positions = await client.post(
                                "https://www.mpvnet.cz/jikord/map/mapData",
                                headers={
                                    "Origin": "https://www.mpvnet.cz",
                                    "Referer": "https://www.mpvnet.cz/jikord/map",
                                    "X-Requested-With": "XMLHttpRequest",
                                },
                                json={
                                    "w": 14.65,
                                    "s": 49.30,
                                    "e": 14.80,
                                    "n": 49.45,
                                    "zoom": 14,
                                    "showStops": False,
                                },
                            )
                            positions.raise_for_status()
                            if len(positions.content) <= 1_000_000:
                                fix = observation(
                                    positions.json(),
                                    first["line"],
                                    first["trip"],
                                    datetime.now(PRAGUE),
                                )
                        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                            logging.getLogger("homeboard.integrations").warning(
                                '{"event":"vehicle_position_unavailable"}'
                            )
                    first["progress"] = self.tracker.update(
                        first["scheduled_at"] + ":" + first["line"] + ":" + str(first["trip"]), fix
                    )
                    return result
        except (httpx.HTTPError, ValueError):
            logging.getLogger("homeboard.integrations").warning(
                '{"event":"ideska_schedule_fallback"}'
            )
        self.tracker.reset()
        return await self.fallback.fetch(now)
