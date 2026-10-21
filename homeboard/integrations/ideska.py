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


def parse_board(html: str, now: datetime) -> dict:
    now = now.astimezone(PRAGUE)
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one(".box-title")
    if title is None or "Nad Hejtmanem Lipová alej" not in title.get_text():
        raise ValueError("Unexpected departure board stop")
    # The board supplies clock times without dates. Avoid guessing at rollover.
    if not 3 <= now.hour < 21:
        raise ValueError("Undated board outside supported daytime window")
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
        hour, minute = map(int, value.split(":"))
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        raw_delay = delay_node.get_text(strip=True)
        if raw_delay and not re.fullmatch(r"-?\d{1,3}", raw_delay):
            raise ValueError("Unknown delay notation")
        delay = int(raw_delay) if raw_delay else None
        if delay is not None and not -5 <= delay <= 180:
            raise ValueError("Unexpected delay")
        expected = scheduled + timedelta(minutes=delay or 0)
        if expected.timestamp() <= now.timestamp():
            continue
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
        "departures": sorted(details),
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
                        now.date().isoformat() + ":" + first["line"] + ":" + str(first["trip"]), fix
                    )
                    return result
        except (httpx.HTTPError, ValueError):
            logging.getLogger("homeboard.integrations").warning(
                '{"event":"ideska_schedule_fallback"}'
            )
        self.tracker.reset()
        return await self.fallback.fetch(now)
