"""Read-only Bakalari v3 adapter based on community protocol documentation."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StrictBool,
    field_validator,
)

from homeboard.providers import PRAGUE


class BakalariSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_url: str = "https://zsplana.bakalari.cz"
    username: SecretStr
    password: SecretStr
    dashboard_password: SecretStr

    @field_validator("base_url")
    @classmethod
    def secure_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
        ):
            raise ValueError("Bakalari requires an HTTPS base URL without credentials or query")
        return value.rstrip("/")

    @field_validator("username", "password", "dashboard_password")
    @classmethod
    def nonempty_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("Credentials must not be empty")
        return value

    @field_validator("dashboard_password")
    @classmethod
    def dashboard_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 12:
            raise ValueError("Dashboard password must contain at least 12 characters")
        return value


def load_settings() -> BakalariSettings:
    try:
        path = Path(os.environ.get("BAKALARI_CONFIG_FILE", ".local/bakalari.json"))
        raw = os.environ.get("BAKALARI_CONFIG_JSON") or path.read_text()
        return BakalariSettings.model_validate_json(raw)
    except (OSError, ValueError):
        # Validation exceptions may include input values. Never expose them at startup.
        raise ValueError(
            "Missing or invalid local Bakalari configuration; run setup_bakalari.py"
        ) from None


class Subject(BaseModel):
    Name: str = Field(min_length=1, max_length=200)


class Assignment(BaseModel):
    ID: str
    DateEnd: AwareDatetime
    Content: str = Field(max_length=20000)
    Subject: Subject
    Done: StrictBool
    Closed: StrictBool


class Assignments(BaseModel):
    Homeworks: list[Assignment] = Field(max_length=500)


def parse_homework(payload: dict, now: datetime) -> dict:
    today = now.astimezone(PRAGUE).date()
    rows = []
    for task in Assignments.model_validate(payload).Homeworks:
        due = task.DateEnd.astimezone(PRAGUE).date()
        if (
            task.Done
            or task.Closed
            or not today - timedelta(days=14) <= due <= today + timedelta(days=30)
        ):
            continue
        soup = BeautifulSoup(task.Content, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        title = " ".join(soup.get_text(" ", strip=True).split())
        rows.append(
            {
                "subject": task.Subject.Name,
                "title": title or "Úkol bez popisu",
                "due": due.isoformat(),
            }
        )
    rows.sort(
        key=lambda task: (
            0
            if task["due"] == today.isoformat()
            else 1
            if task["due"] == (today + timedelta(days=1)).isoformat()
            else 2
            if task["due"] < today.isoformat()
            else 3,
            task["due"],
            task["subject"],
            task["title"],
        )
    )
    return {"homework": rows[:100]}


class BakalariProvider:
    source = "live"

    def __init__(
        self, settings: BakalariSettings, transport: httpx.AsyncBaseTransport | None = None
    ):
        self.settings = settings
        self.transport = transport
        self.access = None
        self.refresh = None
        self.expires = 0.0
        self.blocked_until = 0.0

    async def request(self, client: httpx.AsyncClient, method: str, path: str, **kwargs) -> dict:
        async with client.stream(method, self.settings.base_url + path, **kwargs) as response:
            if response.status_code == 429:
                try:
                    wait = max(300, min(3600, int(response.headers.get("Retry-After", "300"))))
                except ValueError:
                    wait = 300
                self.blocked_until = monotonic() + wait
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 2_000_000:
                    raise ValueError("Oversized school response")
            result = json.loads(body)
            if not isinstance(result, dict):
                raise TypeError("Unexpected school response")
            return result

    async def authenticate(self, client: httpx.AsyncClient) -> None:
        form = {"client_id": "ANDR"}
        if self.refresh:
            form.update(grant_type="refresh_token", refresh_token=self.refresh)
        else:
            form.update(
                grant_type="password",
                username=self.settings.username.get_secret_value(),
                password=self.settings.password.get_secret_value(),
            )
        try:
            token = await self.request(client, "POST", "/api/login", data=form)
        except httpx.HTTPStatusError as error:
            if self.refresh and error.response.status_code in {400, 401}:
                self.refresh = self.access = None
                await self.authenticate(client)
                return
            if error.response.status_code in {400, 401, 403}:
                self.blocked_until = monotonic() + 900
            raise
        access, refresh, expires = (
            token.get("access_token"),
            token.get("refresh_token"),
            token.get("expires_in"),
        )
        if (
            not isinstance(access, str)
            or not access
            or not isinstance(refresh, str)
            or not refresh
            or not isinstance(expires, (int, float))
            or isinstance(expires, bool)
            or not 0 < expires <= 86400
            or str(token.get("token_type", "")).lower() != "bearer"
        ):
            raise ValueError("Invalid authentication response")
        self.access, self.refresh = access, refresh
        self.expires = monotonic() + max(0, expires - 60)

    async def fetch(self, now: datetime) -> dict:
        if monotonic() < self.blocked_until:
            raise ValueError("School retry backoff active")
        today = now.astimezone(PRAGUE).date()
        async with httpx.AsyncClient(
            timeout=2, follow_redirects=False, transport=self.transport
        ) as client:
            if not self.access or monotonic() >= self.expires:
                await self.authenticate(client)
            for attempt in range(2):
                try:
                    payload = await self.request(
                        client,
                        "GET",
                        "/api/3/homeworks",
                        headers={"Authorization": "Bearer " + self.access},
                        params={
                            "from": (today - timedelta(days=14)).isoformat(),
                            "to": (today + timedelta(days=30)).isoformat(),
                        },
                    )
                    return parse_homework(payload, now)
                except httpx.HTTPStatusError as error:
                    if error.response.status_code != 401 or attempt:
                        raise
                    self.access = None
                    await self.authenticate(client)
        raise ValueError("School authentication failed")
