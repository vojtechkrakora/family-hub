"""Synthetic school responses only; never contact a school or use real credentials."""

import asyncio
import json
from datetime import datetime
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from homeboard.integrations.bakalari import (
    BakalariProvider,
    BakalariSettings,
    load_settings,
    parse_homework,
)
from homeboard.main import create_app
from homeboard.providers import PRAGUE

NOW = datetime(2026, 10, 20, 7, tzinfo=PRAGUE)
CONFIG = {
    "username": "synthetic-user",
    "password": "synthetic-school-secret",
    "dashboard_password": "synthetic-dashboard-secret",
}


def homework(**updates):
    task = {
        "ID": "fixture",
        "DateEnd": "2026-10-21T00:00:00+02:00",
        "Content": "<p>Read <b>page 12</b>.</p><script>secret()</script>",
        "Subject": {"Name": "Reading"},
        "Done": False,
        "Closed": False,
    }
    task.update(updates)
    return {"Homeworks": [task]}


def token(access="access-one", refresh="refresh-one"):
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": 3600,
        "token_type": "Bearer",
    }


def test_normalization_and_prague_date():
    result = parse_homework(homework(DateEnd="2026-10-20T22:00:00Z"), NOW)
    assert result == {
        "homework": [{"subject": "Reading", "title": "Read page 12 .", "due": "2026-10-21"}]
    }


@pytest.mark.parametrize(
    "updates", [{"Done": True}, {"Closed": True}, {"DateEnd": "2025-10-21T00:00:00+02:00"}]
)
def test_finished_closed_and_out_of_window_excluded(updates):
    assert parse_homework(homework(**updates), NOW) == {"homework": []}


@pytest.mark.parametrize(
    "updates", [{"DateEnd": "2026-10-20"}, {"Done": "false"}, {"Subject": None}]
)
def test_unknown_schema_fails_instead_of_showing_empty_homework(updates):
    with pytest.raises(ValidationError):
        parse_homework(homework(**updates), NOW)


def test_login_and_access_token_reuse():
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path == "/api/login":
            form = parse_qs(request.content.decode())
            assert form["grant_type"] == ["password"] and form["client_id"] == ["ANDR"]
            return httpx.Response(200, json=token())
        assert request.method == "GET" and request.url.path == "/api/3/homeworks"
        assert request.headers["authorization"] == "Bearer access-one"
        assert request.url.params["from"] == "2026-10-06"
        assert request.url.params["to"] == "2026-11-19"
        return httpx.Response(200, json=homework())

    provider = BakalariProvider(BakalariSettings(**CONFIG), httpx.MockTransport(respond))
    asyncio.run(provider.fetch(NOW))
    asyncio.run(provider.fetch(NOW))
    assert len(requests) == 3


def test_refresh_token_rotates_and_401_retries_once():
    calls = []

    def respond(request):
        calls.append(request.url.path)
        if request.url.path == "/api/login":
            assert parse_qs(request.content.decode())["refresh_token"] == ["refresh-one"]
            return httpx.Response(200, json=token("access-two", "refresh-two"))
        if request.headers["authorization"] == "Bearer access-one":
            return httpx.Response(401)
        return httpx.Response(200, json=homework())

    provider = BakalariProvider(BakalariSettings(**CONFIG), httpx.MockTransport(respond))
    provider.access, provider.refresh, provider.expires = "access-one", "refresh-one", float("inf")
    asyncio.run(provider.fetch(NOW))
    assert calls == ["/api/3/homeworks", "/api/login", "/api/3/homeworks"]
    assert provider.refresh == "refresh-two"


def test_expired_refresh_falls_back_to_password_once():
    grants = []

    def respond(request):
        if request.url.path == "/api/login":
            grant = parse_qs(request.content.decode())["grant_type"][0]
            grants.append(grant)
            return (
                httpx.Response(400)
                if grant == "refresh_token"
                else httpx.Response(200, json=token())
            )
        return httpx.Response(200, json=homework())

    provider = BakalariProvider(BakalariSettings(**CONFIG), httpx.MockTransport(respond))
    provider.refresh = "expired"
    asyncio.run(provider.fetch(NOW))
    assert grants == ["refresh_token", "password"]


@pytest.mark.parametrize("status", [400, 429])
def test_failed_auth_and_rate_limit_backoff(status):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, json={"error": "invalid_grant"})

    provider = BakalariProvider(BakalariSettings(**CONFIG), httpx.MockTransport(respond))
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(provider.fetch(NOW))
    with pytest.raises(ValueError, match="backoff"):
        asyncio.run(provider.fetch(NOW))
    assert len(calls) == 1


def test_no_redirects_or_credentials_forwarded():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://other.invalid/"})

    provider = BakalariProvider(BakalariSettings(**CONFIG), httpx.MockTransport(respond))
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(provider.fetch(NOW))
    assert len(calls) == 1


def test_dashboard_auth_before_school_fetch(monkeypatch):
    monkeypatch.setenv("SCHOOL_SOURCE", "bakalari")
    monkeypatch.setenv("BAKALARI_CONFIG_JSON", json.dumps(CONFIG))

    async def synthetic(self, now):
        return parse_homework(homework(DateEnd=now.isoformat()), now)

    monkeypatch.setattr(BakalariProvider, "fetch", synthetic)
    with TestClient(create_app()) as client:
        for path in ["/", "/api/dashboard", "/static/app.js"]:
            assert client.get(path).status_code == 401
            assert client.get(path, auth=("homeboard", "wrong")).status_code == 401
        assert client.get("/health").status_code == 200
        response = client.get("/api/dashboard", auth=("homeboard", CONFIG["dashboard_password"]))
        assert response.status_code == 200
        assert response.json()["homework"][0]["urgency"] == "today"
        assert response.headers["cache-control"] == "no-store"
        for secret in CONFIG.values():
            assert secret not in response.text


def test_configuration_errors_do_not_reveal_values(monkeypatch):
    monkeypatch.setenv("BAKALARI_CONFIG_JSON", json.dumps({**CONFIG, "base_url": "http://invalid"}))
    with pytest.raises(ValueError) as error:
        load_settings()
    assert "synthetic" not in str(error.value)
    assert "synthetic-school-secret" not in repr(BakalariSettings(**CONFIG))


def test_today_and_tomorrow_outrank_old_overdue_tasks():
    payload = {
        "Homeworks": [
            homework(DateEnd=date + "T00:00:00+02:00")["Homeworks"][0]
            for date in ["2026-10-19", "2026-10-22", "2026-10-21", "2026-10-20"]
        ]
    }
    assert [t["due"] for t in parse_homework(payload, NOW)["homework"]] == [
        "2026-10-20",
        "2026-10-21",
        "2026-10-19",
        "2026-10-22",
    ]


def test_server_error_retains_cached_homework_without_logging_secrets(caplog):
    from homeboard.integrations.models import SchoolData
    from homeboard.integrations.service import CachedIntegration

    failed = False

    def respond(request):
        if failed:
            return httpx.Response(503, text="synthetic-school-secret")
        return httpx.Response(200, json=token() if request.url.path == "/api/login" else homework())

    provider = BakalariProvider(BakalariSettings(**CONFIG), httpx.MockTransport(respond))
    cached = CachedIntegration("school", provider, SchoolData, 0)
    first = asyncio.run(cached.snapshot(NOW))
    failed = True
    second = asyncio.run(cached.snapshot(NOW))
    assert second["status"] == "stale"
    assert second["data"] == first["data"]
    assert "synthetic-school-secret" not in caplog.text
