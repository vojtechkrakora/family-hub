"""Homeboard HTTP application and integration composition."""

import asyncio
import base64
import binascii
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from homeboard.domain import countdown, morning_routine
from homeboard.integrations.bakalari import BakalariProvider, BakalariSettings, load_settings
from homeboard.integrations.comett import ComettProvider
from homeboard.integrations.google_calendar import GoogleCalendarProvider, load_calendar_settings
from homeboard.integrations.ideska import IdeskaProvider
from homeboard.integrations.models import CalendarData, SchoolData, TransportData
from homeboard.integrations.service import CachedIntegration, Provider
from homeboard.integrations.vehicle import needs_fast_refresh
from homeboard.providers import (
    PRAGUE,
    MockCalendarProvider,
    MockSchoolProvider,
    MockTransportProvider,
)

STATIC = Path(__file__).parent / "static"


def read_minutes(name: str, default: int) -> int:
    value = int(os.environ.get(name, default))
    if not 0 <= value <= 120:
        raise ValueError(f"{name} must be between 0 and 120")
    return value


def configured_provider(
    name: str, mock: Provider, school_settings: BakalariSettings | None = None
) -> Provider | None:
    value = os.environ.get(name + "_SOURCE", "ideska" if name == "TRANSPORT" else "mock")
    if name == "TRANSPORT" and value == "ideska":
        return IdeskaProvider()
    if name == "TRANSPORT" and value == "comett":
        return ComettProvider()
    if name == "SCHOOL" and value == "bakalari":
        return BakalariProvider(school_settings or load_settings())
    if name == "CALENDAR" and value == "google_ics":
        return GoogleCalendarProvider(load_calendar_settings())
    if value == "mock":
        return mock
    if value == "disabled":
        return None
    raise ValueError(
        f"Unsupported {name}_SOURCE; use mock, disabled, bakalari (school), google_ics (calendar), ideska or comett (transport)"
    )


def create_app(integrations: dict[str, CachedIntegration] | None = None) -> FastAPI:
    auth_mode = os.environ.get("HOMEBOARD_AUTH_MODE", "disabled")
    if auth_mode not in {"basic", "disabled"}:
        raise ValueError("HOMEBOARD_AUTH_MODE must be basic or disabled")
    app = FastAPI(title="Homeboard", docs_url=None, redoc_url=None)
    school_settings = (
        load_settings()
        if (
            os.environ.get("SCHOOL_SOURCE") == "bakalari"
            or os.environ.get("CALENDAR_SOURCE") == "google_ics"
        )
        else None
    )
    if school_settings:
        expected = ("homeboard:" + school_settings.dashboard_password.get_secret_value()).encode()

        @app.middleware("http")
        async def protect_dashboard(request: Request, call_next):
            authorized = False
            try:
                scheme, encoded = request.headers.get("Authorization", "").split(" ", 1)
                authorized = scheme.lower() == "basic" and secrets.compare_digest(
                    base64.b64decode(encoded, validate=True), expected
                )
            except (ValueError, binascii.Error):
                pass
            if auth_mode == "basic" and request.url.path != "/health" and not authorized:
                return Response(
                    "Přihlaste se do Homeboardu.",
                    status_code=401,
                    headers={
                        "WWW-Authenticate": 'Basic realm="Homeboard", charset="UTF-8"',
                        "Cache-Control": "no-store",
                    },
                )
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response

    sources = (
        integrations
        if integrations is not None
        else {
            "transport": CachedIntegration(
                "transport",
                configured_provider("TRANSPORT", MockTransportProvider()),
                TransportData,
                300 if os.environ.get("TRANSPORT_SOURCE", "ideska") == "comett" else 30,
                timeout_seconds=7,
                refresh_policy=lambda data, now: (
                    10
                    if needs_fast_refresh(data.model_dump(mode="json"), now)
                    else 300
                    if os.environ.get("TRANSPORT_SOURCE", "ideska") == "comett"
                    else 30
                ),
            ),
            "school": CachedIntegration(
                "school",
                configured_provider("SCHOOL", MockSchoolProvider(), school_settings),
                SchoolData,
                300,
                timeout_seconds=7,
                retry_seconds=300,
            ),
            "calendar": CachedIntegration(
                "calendar",
                configured_provider("CALENDAR", MockCalendarProvider()),
                CalendarData,
                300,
                timeout_seconds=25,
                retry_seconds=300,
            ),
        }
    )
    if set(sources) != {"transport", "school", "calendar"}:
        raise ValueError("Transport, school and calendar integration slots are required")
    walking = read_minutes("WALKING_MINUTES", 1)
    dressing = read_minutes("DRESSING_MINUTES", 10)
    shoes = read_minutes("SHOES_MINUTES", 3)
    if dressing == 0 or shoes == 0:
        raise ValueError("DRESSING_MINUTES and SHOES_MINUTES must be positive")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/api/dashboard")
    async def dashboard(response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        now = datetime.now(PRAGUE)
        snapshots = await asyncio.gather(*(source.snapshot(now) for source in sources.values()))
        states = dict(zip(sources, snapshots))
        now = datetime.now(PRAGUE)
        transport = states["transport"]["data"]
        routine = []
        if transport is not None:
            departures = sorted(datetime.fromisoformat(item) for item in transport["departures"])
            transport["departures"] = [
                item.isoformat() for item in departures if item.timestamp() > now.timestamp()
            ]
            if transport["departures"] and states["transport"]["status"] == "available":
                departure = datetime.fromisoformat(transport["departures"][0])
                transport.update(countdown(departure, now, walking, dressing + shoes))
                routine = morning_routine(departure, dressing, shoes, walking)
        school = states["school"]["data"]
        calendar = states["calendar"]["data"]
        events = []
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        for item in calendar["events"] if calendar else []:
            start = datetime.fromisoformat(item["starts_at"]).astimezone(PRAGUE)
            end = (
                datetime.fromisoformat(item["ends_at"]).astimezone(PRAGUE)
                if item.get("ends_at")
                else start
            )
            if start < day_end and (start >= day_start or end > day_start):
                events.append(
                    {
                        **item,
                        "time": "Celý den"
                        if item["all_day"]
                        else "Probíhá"
                        if start < day_start
                        else start.strftime("%H:%M"),
                        "upcoming": not item["all_day"]
                        and 0 <= start.timestamp() - now.timestamp() <= 3600,
                    }
                )
        events.sort(key=lambda item: datetime.fromisoformat(item["starts_at"]).timestamp())
        return {
            "generated_at": now.isoformat(),
            "integrations": {
                name: {key: value for key, value in state.items() if key != "data"}
                for name, state in states.items()
            },
            "transport": transport,
            "homework": [
                {
                    **task,
                    "urgency": "overdue"
                    if task["due"] < now.date().isoformat()
                    else "today"
                    if task["due"] == now.date().isoformat()
                    else "tomorrow"
                    if task["due"] == (now.date() + timedelta(days=1)).isoformat()
                    else "later",
                }
                for task in school["homework"]
            ]
            if school
            else [],
            "events": events,
            "walking_minutes": walking,
            "dressing_minutes": dressing,
            "shoes_minutes": shoes,
            "routine": routine,
            "timezone": "Europe/Prague",
            "refresh_seconds": 10
            if states["transport"]["status"] == "available" and needs_fast_refresh(transport, now)
            else 15,
        }

    return app


app = create_app()
