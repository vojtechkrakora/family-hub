"""GPS normalization and conservative, trip-scoped progress inference.

Road geometry: OpenStreetMap ways 211314930/76783877/32783728 (ODbL).
Barbora coordinate: user-supplied Mapy place 2240752, inspected GPS field.
"""

import math
from datetime import datetime
from itertools import pairwise

from homeboard.providers import PRAGUE

CROSSING = (49.349325, 14.70819)
BARBORA = (49.3490900, 14.7085142)
ROAD = [
    BARBORA,
    (49.3481773, 14.7103055),
    (49.3468288, 14.7127375),
    (49.3452940, 14.7155353),
    (49.3448612, 14.7169796),
    (49.3442415, 14.7189734),
    (49.3436084, 14.7196980),
    (49.3428420, 14.7204810),
    (49.3413561, 14.7230696),
]
MAX_AGE = 75


def xy(point: tuple[float, float]) -> tuple[float, float]:
    return (
        (point[1] - BARBORA[1]) * 111_320 * math.cos(math.radians(BARBORA[0])),
        (point[0] - BARBORA[0]) * 111_320,
    )


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    ax, ay = xy(a)
    bx, by = xy(b)
    return math.hypot(ax - bx, ay - by)


def on_strkovska(point: tuple[float, float]) -> bool:
    px, py = xy(point)
    # A 40m southeast margin beyond the chapel prevents boundary jitter.
    if (px - py) / math.sqrt(2) < 40:
        return False
    for a, b in pairwise(ROAD):
        ax, ay = xy(a)
        bx, by = xy(b)
        fraction = max(
            0,
            min(
                1,
                ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2),
            ),
        )
        if math.hypot(px - ax - fraction * (bx - ax), py - ay - fraction * (by - ay)) <= 45:
            return True
    return False


def observation(payload: dict, line: str, trip: str, now: datetime) -> dict | None:
    """Match exact route, trip and direction; never match a line number alone."""
    candidates = []
    for raw in payload.get("transmitters", []):
        try:
            parts = raw["cn"].split("|")
            if (
                raw.get("cat") != 2
                or parts[0] != "3950" + line
                or parts[2] != trip
                or parts[9] != "Planá n.Luž.,Strkov"
            ):
                continue
            stamp = datetime.strptime(raw["dt"] + " " + raw["tm"], "%d.%m.%Y %H:%M:%S").replace(
                tzinfo=PRAGUE
            )
            age = now.timestamp() - stamp.timestamp()
            lat, lon = float(raw["x"]), float(raw["y"])
            if not (0 <= age <= MAX_AGE and 49.30 <= lat <= 49.45 and 14.65 <= lon <= 14.80):
                continue
            candidates.append(
                {
                    "point": (lat, lon),
                    "observed_at": stamp,
                    "in_town": parts[3].startswith("Planá n.Luž.,")
                    and parts[5].startswith("Planá n.Luž.,"),
                }
            )
        except (KeyError, ValueError, TypeError, IndexError, AttributeError):
            continue
    return candidates[0] if len(candidates) == 1 else None


class ProgressTracker:
    """One selected trip in memory; repeated or stale fixes cannot prove waiting."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.key = None
        self.last = None
        self.anchor = None
        self.since = None
        self.passed = False
        self.previous_beyond = False
        self.waiting = False

    def update(self, key: str, fix: dict | None) -> dict | None:
        if fix is None:
            self.reset()
            return None
        stamp = fix["observed_at"].timestamp()
        point = fix["point"]
        if key != self.key or (
            self.last is not None and (stamp < self.last or stamp - self.last > MAX_AGE)
        ):
            self.reset()
        self.key = key
        beyond = on_strkovska(point)
        near = distance(point, CROSSING) <= 100 and not beyond
        if self.last != stamp:
            self.passed = self.passed or (beyond and self.previous_beyond)
            self.previous_beyond = beyond
            if not near:
                self.anchor = self.since = None
                self.waiting = False
            elif self.anchor is None or distance(point, self.anchor) > 25:
                self.anchor, self.since = point, stamp
                self.waiting = False
            else:
                self.waiting = stamp - self.since >= 60
            self.last = stamp
        state = (
            "strkovska"
            if beyond and self.passed
            else "passed"
            if self.passed
            else "waiting_crossing"
            if near and self.waiting
            else "crossing"
            if near
            else "town"
            if fix["in_town"]
            else "approaching"
        )
        return {
            "state": state,
            "observed_at": fix["observed_at"].isoformat(),
            "passed_crossing": self.passed,
            "latitude": point[0],
            "longitude": point[1],
        }


def needs_fast_refresh(transport: dict | None, now: datetime) -> bool:
    """Only the next, still-future departure with fresh nearby GPS speeds polling."""
    if not transport:
        return False
    future = [
        item
        for item in transport.get("departures", [])
        if datetime.fromisoformat(item).timestamp() > now.timestamp()
    ]
    if not future:
        return False
    first = min(future, key=lambda item: datetime.fromisoformat(item).timestamp())
    progress = transport.get("departure_details", {}).get(first, {}).get("progress")
    if not progress:
        return False
    age = now.timestamp() - datetime.fromisoformat(progress["observed_at"]).timestamp()
    return 0 <= age <= MAX_AGE and progress["state"] in {
        "crossing",
        "waiting_crossing",
        "passed",
        "strkovska",
    }
