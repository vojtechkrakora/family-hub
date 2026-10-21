"""Read COMETT's public stop timetables, not an undocumented private API."""

import asyncio
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import holidays
import httpx
from bs4 import BeautifulSoup, SoupStrainer

from homeboard.providers import PRAGUE

BASE_URL = "https://www.comettplus.cz/cz/zastavkove-jizdni-rady-mhd/plana-nad-luznici-nad-hejtmanem-lipova-alej/smer-a-strkov/"
LINES = ("43", "45")
DATE_PATTERN = r"\d{1,2}\.\s*\d{1,2}\.\s*\d{4}"
MAX_BYTES = 2_000_000


def parse_date(value: str) -> date:
    return datetime.strptime(re.sub(r"\s+", "", value), "%d.%m.%Y").date()


def normalized(value: str) -> str:
    return " ".join(value.split())


@dataclass(frozen=True)
class Journey:
    hour: int
    minute: int
    column: int
    exclusions: tuple[tuple[date, date], ...]


@dataclass(frozen=True)
class Timetable:
    line: str
    valid_from: date
    valid_until: date | None
    journeys: tuple[Journey, ...]


def parse_exclusions(text: str) -> tuple[tuple[date, date], ...]:
    text = normalized(text)
    if not text.startswith("nejede "):
        raise ValueError("Unsupported service restriction")
    ranges = []
    for part in text.removeprefix("nejede ").split(","):
        part = part.strip()
        match = re.fullmatch(rf"od ({DATE_PATTERN}) do ({DATE_PATTERN})", part)
        if match:
            start, end = map(parse_date, match.groups())
        elif re.fullmatch(DATE_PATTERN, part):
            start = end = parse_date(part)
        else:
            raise ValueError("Unknown exclusion rule")
        if end < start:
            raise ValueError("Reversed exclusion range")
        ranges.append((start, end))
    return tuple(ranges)


def parse_timetable(html: str, line: str, fetched_day: date) -> Timetable:
    soup = BeautifulSoup(html, "html.parser", parse_only=SoupStrainer("section", id="jr-station"))
    header = soup.select_one("#jr_station_accordion")
    active = soup.select_one(".station_lines .active")
    stamp = soup.select_one(".jr-header > span")
    direction = soup.select_one(".station_lines .left_dir_box")
    validity = soup.select_one(".validity_time")
    if not all((header, active, stamp, direction, validity)):
        raise ValueError("Timetable identity missing")
    if normalized(header.get_text()) != "Zastávka Planá nad Lužnicí, Nad Hejtmanem Lipová alej":
        raise ValueError("Wrong stop")
    if (
        active.get_text(strip=True) != line
        or normalized(direction.get_text()) != "Linky (směr Strkov):"
    ):
        raise ValueError("Wrong line or direction")
    if normalized(stamp.get_text()) != "Platné k datu " + fetched_day.strftime("%d.%m.%Y").lstrip(
        "0"
    ):
        # The operator omits leading zeros from day/month on some pages.
        match = re.fullmatch(rf"Platné k datu ({DATE_PATTERN})", normalized(stamp.get_text()))
        if not match or parse_date(match.group(1)) != fetched_day:
            raise ValueError("Timetable page is for another date")
    match = re.fullmatch(
        rf"platí od ({DATE_PATTERN})(?: do ({DATE_PATTERN}))?", normalized(validity.get_text())
    )
    if not match:
        raise ValueError("Unknown validity period")
    valid_from = parse_date(match.group(1))
    valid_until = parse_date(match.group(2)) if match.group(2) else None
    if fetched_day < valid_from or (valid_until and fetched_day > valid_until):
        raise ValueError("Timetable outside validity")
    table = soup.select_one("table.jr_main")
    if table is None:
        raise ValueError("Timetable missing")
    rows = table.select("tr")
    expected = ["Pracovní dny", "Soboty", "Neděle a svátky", "Pracovní dny"]
    if [
        normalized(cell.get_text()) for cell in rows[0].find_all("td", recursive=False)
    ] != expected:
        raise ValueError("Unsupported timetable columns")
    if [normalized(cell.get_text()) for cell in rows[1].find_all("td", recursive=False)] != [
        "Hod",
        "minuty",
        "minuty",
        "minuty",
        "od 1. 7. do 31. 8.",
    ]:
        raise ValueError("Unsupported seasonal schedule")
    restrictions = {}
    for note in table.select("div.timecode"):
        code = note.find("span", recursive=False)
        body = note.select_one(".text")
        if code is None or body is None:
            raise ValueError("Malformed service restriction")
        restrictions[code.get_text(strip=True)] = parse_exclusions(body.get_text(" ", strip=True))
    journeys = []
    hours = set()
    for row in rows[2:]:
        cells = row.find_all("td", recursive=False)
        if len(cells) != 5:
            if row.select_one(".timebox"):
                raise ValueError("Malformed departure row")
            continue
        hour = int(cells[0].get_text(strip=True))
        if hour not in range(24) or hour in hours:
            raise ValueError("Invalid or repeated hour")
        hours.add(hour)
        for column, cell in enumerate(cells[1:]):
            if cell.get_text(strip=True) and not cell.select(".timebox"):
                raise ValueError("Unrecognized departure cell")
            for box in cell.select(".timebox"):
                minute_node = box.select_one(".time")
                route = box.select_one(".subline")
                if minute_node is None or route is None or route.get_text(strip=True) != "E":
                    raise ValueError("Unknown departure or route variant")
                minute = int(minute_node.get_text(strip=True))
                if minute not in range(60):
                    raise ValueError("Invalid minute")
                excluded = []
                for code in box.select(".timecode"):
                    name = code.get_text(strip=True)
                    if name not in restrictions:
                        raise ValueError("Unknown service code")
                    excluded.extend(restrictions[name])
                journeys.append(Journey(hour, minute, column, tuple(excluded)))
    if hours != set(range(24)):
        raise ValueError("Incomplete timetable")
    return Timetable(line, valid_from, valid_until, tuple(journeys))


def upcoming(tables: list[Timetable], now: datetime) -> dict:
    if now.utcoffset() is None:
        raise ValueError("Timezone-aware current time required")
    local = now.astimezone(PRAGUE)
    calendar = holidays.CZ(years=[local.year, local.year + 1])
    found = []
    for offset in range(8):
        day = local.date() + timedelta(days=offset)
        column = (
            2
            if day in calendar or day.weekday() == 6
            else 1
            if day.weekday() == 5
            else 3
            if day.month in (7, 8)
            else 0
        )
        for table in tables:
            if day < table.valid_from or (table.valid_until and day > table.valid_until):
                continue
            for journey in table.journeys:
                if journey.column != column or any(
                    start <= day <= end for start, end in journey.exclusions
                ):
                    continue
                departure = datetime.combine(day, time(journey.hour, journey.minute), PRAGUE)
                if departure.timestamp() > now.timestamp():
                    found.append((departure, table.line))
    found.sort(key=lambda item: (item[0].timestamp(), item[1]))
    # One entry per timestamp; a tie chooses the lower line number consistently.
    unique = {}
    for departure, line in found:
        unique.setdefault(departure.isoformat(), (departure, line))
    found = list(unique.values())[:20]
    return {
        "origin": "Lipová alej",
        "destination": "Strkov",
        "departures": [item.isoformat() for item, _ in found],
        "departure_details": {
            item.isoformat(): {"line": line, "destination": "Strkov"} for item, line in found
        },
        "delay_minutes": None,
    }


class ComettProvider:
    source = "scheduled"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    async def fetch(self, now: datetime) -> dict:
        day = now.astimezone(PRAGUE).date()
        async with httpx.AsyncClient(
            timeout=2.5,
            follow_redirects=False,
            transport=self.transport,
            headers={"User-Agent": "Homeboard/0.1 (personal household timetable reader)"},
        ) as client:

            async def read(line: str) -> Timetable:
                async with client.stream("GET", BASE_URL + "linka-" + line + "/") as response:
                    response.raise_for_status()
                    if "text/html" not in response.headers.get("content-type", ""):
                        raise ValueError("Expected timetable HTML")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            raise ValueError("Timetable response too large")
                return parse_timetable(body.decode("utf-8"), line, day)

            tables = await asyncio.gather(*(read(line) for line in LINES))
        return upcoming(tables, now)
