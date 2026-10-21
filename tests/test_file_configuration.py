"""File-only household configuration must retain protection after recreation."""

import json

import pytest
from fastapi.testclient import TestClient

from homeboard.main import create_app


@pytest.fixture
def private_files(tmp_path, monkeypatch):
    school = tmp_path / "bakalari.json"
    calendar = tmp_path / "calendar.json"
    school.write_text(
        json.dumps(
            {
                "base_url": "https://school.example.invalid",
                "username": "synthetic-user",
                "password": "synthetic-school-password",
                "dashboard_password": "synthetic-dashboard-password",
            }
        )
    )
    calendar.write_text(
        json.dumps(
            {
                "calendars": [
                    {
                        "name": "Synthetic",
                        "url": "https://calendar.google.com/calendar/ical/synthetic/basic.ics",
                    }
                ]
            }
        )
    )
    for key in ("BAKALARI_CONFIG_JSON", "GOOGLE_CALENDAR_CONFIG_JSON"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BAKALARI_CONFIG_FILE", str(school))
    monkeypatch.setenv("GOOGLE_CALENDAR_CONFIG_FILE", str(calendar))
    monkeypatch.setenv("SCHOOL_SOURCE", "bakalari")
    monkeypatch.setenv("CALENDAR_SOURCE", "google_ics")
    return school, calendar


def test_file_only_configuration_retains_auth_on_recreation(private_files):
    for _ in range(2):
        with TestClient(create_app()) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/").status_code == 401
            assert client.get("/api/dashboard").status_code == 401
            assert (
                client.get("/", auth=("homeboard", "synthetic-dashboard-password")).status_code
                == 200
            )


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("invalid", [False, True])
def test_missing_or_invalid_private_file_fails_closed(private_files, index, invalid):
    path = private_files[index]
    if invalid:
        path.write_text("INVALID-PRIVATE-CONTENT")
    else:
        path.unlink()
    with pytest.raises(ValueError) as error:
        create_app()
    assert "PRIVATE-CONTENT" not in str(error.value)
