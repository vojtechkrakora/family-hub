"""Automated tests must never contact real integration endpoints."""

import pytest


@pytest.fixture(autouse=True)
def mock_sources(monkeypatch):
    monkeypatch.delenv("HOMEBOARD_AUTH_MODE", raising=False)
    for name in ("TRANSPORT", "SCHOOL", "CALENDAR"):
        monkeypatch.setenv(name + "_SOURCE", "mock")
