"""Read-only Google secret ICS feeds; URLs never leave the backend."""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class CalendarFeed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=60)
    url: SecretStr

    @field_validator("url")
    @classmethod
    def google_feed(cls, value: SecretStr) -> SecretStr:
        parts = urlsplit(value.get_secret_value())
        if (
            parts.scheme != "https"
            or parts.hostname not in {"calendar.google.com", "www.google.com"}
            or parts.port not in {None, 443}
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or not parts.path.startswith("/calendar/ical/")
            or not parts.path.endswith("/basic.ics")
        ):
            raise ValueError("Use a Google HTTPS iCal feed address")
        return value


class CalendarSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calendars: list[CalendarFeed] = Field(min_length=1, max_length=5)


def load_calendar_settings() -> CalendarSettings:
    try:
        raw = (
            os.environ.get("GOOGLE_CALENDAR_CONFIG_JSON")
            or Path(
                os.environ.get("GOOGLE_CALENDAR_CONFIG_FILE", ".local/calendar.json")
            ).read_text()
        )
        return CalendarSettings.model_validate_json(raw)
    except (OSError, ValueError):
        raise ValueError(
            "Missing or invalid local calendar configuration; run setup_calendar.py"
        ) from None


async def parse_feeds(feeds: list[dict], now: datetime) -> dict:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "homeboard.integrations.ics_parser",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        output, _ = await asyncio.wait_for(
            process.communicate(json.dumps({"feeds": feeds, "now": now.isoformat()}).encode()),
            timeout=20,
        )
        if process.returncode:
            raise ValueError("Calendar parsing failed")
        return json.loads(output)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


class GoogleCalendarProvider:
    source = "live"

    def __init__(
        self, settings: CalendarSettings, transport: httpx.AsyncBaseTransport | None = None
    ):
        self.settings = settings
        self.transport = transport
        self.blocked_until = 0.0

    async def fetch(self, now: datetime) -> dict:
        if monotonic() < self.blocked_until:
            raise ValueError("Calendar retry backoff active")
        async with httpx.AsyncClient(
            timeout=3, follow_redirects=False, transport=self.transport
        ) as client:

            async def download(feed: CalendarFeed) -> dict:
                async with client.stream("GET", feed.url.get_secret_value()) as response:
                    if response.status_code == 429:
                        try:
                            wait = max(
                                300, min(3600, int(response.headers.get("Retry-After", "300")))
                            )
                        except ValueError:
                            wait = 300
                        self.blocked_until = monotonic() + wait
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 2_000_000:
                            raise ValueError("Calendar feed too large")
                return {"name": feed.name, "content": body.decode("utf-8-sig")}

            tasks = [asyncio.create_task(download(feed)) for feed in self.settings.calendars]
            try:
                feeds = await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        return await parse_feeds(feeds, now)
