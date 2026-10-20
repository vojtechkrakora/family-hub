"""Homeboard local proof of concept."""

import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from homeboard.domain import countdown, morning_routine
from homeboard.providers import PRAGUE, DashboardProvider, MockProvider

logger = logging.getLogger("homeboard")
STATIC = Path(__file__).parent / "static"


def read_minutes(name: str, default: int) -> int:
    value = int(os.environ.get(name, default))
    if not 0 <= value <= 120:
        raise ValueError(f"{name} must be between 0 and 120")
    return value


def create_app(provider: DashboardProvider | None = None) -> FastAPI:
    app = FastAPI(title="Homeboard", docs_url=None, redoc_url=None)
    adapter = provider if provider is not None else MockProvider()
    walking = read_minutes("WALKING_MINUTES", 1)
    dressing = read_minutes("DRESSING_MINUTES", 10)
    shoes = read_minutes("SHOES_MINUTES", 3)
    if dressing == 0 or shoes == 0:
        raise ValueError("DRESSING_MINUTES and SHOES_MINUTES must be positive")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "mode": "mock"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/api/dashboard")
    def dashboard(response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        now = datetime.now(PRAGUE)
        try:
            data = adapter.snapshot(now)
        except Exception:  # noqa: BLE001 - Isolate provider failures without logging secrets.
            logger.error('{"event":"provider_unavailable"}')
            response.status_code = 503
            return {"error": "Dashboard data is unavailable"}
        departure = datetime.fromisoformat(data["transport"]["departures"][0])
        data["transport"].update(countdown(departure, now, walking, dressing + shoes))
        data.update(
            {
                "walking_minutes": walking,
                "dressing_minutes": dressing,
                "shoes_minutes": shoes,
                "routine": morning_routine(departure, dressing, shoes, walking),
                "timezone": "Europe/Prague",
                "refresh_seconds": 15,
            }
        )
        return data

    return app


app = create_app()
