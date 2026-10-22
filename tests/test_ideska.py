"""Synthetic public-board fixtures; no external requests in tests."""

import asyncio
from datetime import datetime

import httpx
import pytest

from homeboard.integrations.ideska import IdeskaProvider, parse_board
from homeboard.integrations.models import TransportData
from homeboard.providers import PRAGUE

NOW = datetime(2026, 10, 20, 7, 38, tzinfo=PRAGUE)


def row(line="45", clock="07:34", delay="10", destination="Planá n.Luž.,Strkov"):
    return f"""<div class="timetable-row">
    <div class="timetable-item"><div class="timetable-value"><div>{line}</div></div></div>
    <div class="timetable-item"><div class="timetable-value">{destination}</div></div>
    <div class="timetable-item"></div>
    <div class="timetable-item"><div class="timetable-value">{clock}</div></div>
    <div class="timetable-item"></div>
    <div class="timetable-item"><div class="timetable-value">{delay}</div></div>
    </div>"""


def board(rows):
    return '<span class="box-title">Planá n.Luž.,Nad Hejtmanem Lipová alej</span>' + rows


def test_delayed_departure_survives_scheduled_time_and_is_sorted():
    data = parse_board(board(row() + row("43", "07:40", "0")), NOW)
    model = TransportData.model_validate(data)
    assert [d.minute for d in model.departures] == [40, 44]
    detail = model.departure_details[model.departures[1].isoformat()]
    assert detail.scheduled_at.minute == 34
    assert detail.delay_minutes == 10


def test_missing_delay_is_not_zero_or_live():
    data = parse_board(board(row(clock="07:40", delay="")), NOW)
    assert next(iter(data["departure_details"].values()))["delay_minutes"] is None


@pytest.mark.parametrize("clock", ["7:34", "07:34"])
def test_single_and_double_digit_hours_keep_live_departures(clock):
    data = parse_board(board(row(clock=clock, delay="10")), NOW)
    assert data["departures"] == ["2026-10-20T07:44:00+02:00"]
    detail = data["departure_details"][data["departures"][0]]
    assert detail["scheduled_at"] == "2026-10-20T07:34:00+02:00"
    assert detail["delay_minutes"] == 10


def test_other_direction_and_line_are_excluded():
    assert not parse_board(board(row(destination="Tábor") + row(line="42")), NOW)["departures"]


@pytest.mark.parametrize("delay", ["?", "999", "-10"])
def test_unrecognized_delay_rejected(delay):
    with pytest.raises(ValueError):
        parse_board(board(row(delay=delay)), NOW)


def test_wrong_stop_rejected():
    with pytest.raises(ValueError):
        parse_board(board(row()).replace("Lipová alej", "jiná"), NOW)


@pytest.mark.parametrize("hour", [0, 2, 21, 22, 23])
def test_live_board_has_no_hour_of_day_cutoff(hour):
    now = NOW.replace(hour=hour, minute=10)
    data = parse_board(board(row(clock=f"{hour:02}:20", delay="0")), now)
    assert datetime.fromisoformat(data["departures"][0]) == now.replace(minute=20)


def test_next_day_departure_before_midnight():
    now = NOW.replace(hour=23, minute=55)
    data = parse_board(board(row(clock="00:10", delay="0")), now)
    assert data["departures"] == ["2026-10-21T00:10:00+02:00"]


def test_delayed_previous_day_departure_after_midnight():
    now = NOW.replace(hour=0, minute=5)
    data = parse_board(board(row(clock="23:55", delay="20")), now)
    assert data["departures"] == ["2026-10-20T00:15:00+02:00"]
    assert next(iter(data["departure_details"].values()))["scheduled_at"].startswith("2026-10-19")


def test_distant_undated_departure_is_not_guessed():
    assert not parse_board(board(row(clock="07:34", delay="0")), NOW.replace(hour=23))["departures"]


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 3, 29, 1, 50, tzinfo=PRAGUE),
        datetime(2026, 10, 25, 1, 50, tzinfo=PRAGUE),
    ],
)
def test_nonexistent_or_ambiguous_dst_time_is_not_guessed(now):
    assert not parse_board(board(row(clock="02:30", delay="0")), now)["departures"]


def test_delay_uses_elapsed_minutes_across_dst():
    now = datetime(2026, 3, 29, 1, 55, tzinfo=PRAGUE)
    data = parse_board(board(row(clock="01:50", delay="20")), now)
    assert data["departures"] == ["2026-03-29T03:10:00+02:00"]


def test_departed_bus_removed():
    assert not parse_board(board(row(delay="0")), NOW)["departures"]


def test_network_failure_uses_schedule(monkeypatch):
    async def fail(*args, **kwargs):
        raise httpx.ConnectError("Offline")

    async def fallback(now):
        return {"fallback": True}

    provider = IdeskaProvider()
    monkeypatch.setattr(httpx.AsyncClient, "post", fail)
    monkeypatch.setattr(provider.fallback, "fetch", fallback)
    assert asyncio.run(provider.fetch(NOW)) == {"fallback": True}


def test_verified_public_request_and_response(monkeypatch):
    async def post(client, url, **kwargs):
        import json

        assert url == "https://www.mpvnet.cz/jikord/tab/departures"
        assert json.loads(kwargs["json"]["StopKey"])["stopNum"] == 62683
        assert kwargs["json"]["isDepartures"] is True
        return httpx.Response(200, text=board(row()), request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    result = asyncio.run(IdeskaProvider().fetch(NOW))
    from homeboard.domain import countdown, morning_routine

    departure = datetime.fromisoformat(result["departures"][0])
    assert countdown(departure, NOW, 1, 13)["departure_minutes"] == 6
    assert morning_routine(departure, 10, 3, 1)


def test_invalid_board_uses_schedule(monkeypatch):
    async def post(client, url, **kwargs):
        return httpx.Response(
            200, text="<html>Maintenance</html>", request=httpx.Request("POST", url)
        )

    async def fallback(now):
        return {"fallback": True}

    provider = IdeskaProvider()
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    monkeypatch.setattr(provider.fallback, "fetch", fallback)
    assert asyncio.run(provider.fetch(NOW)) == {"fallback": True}


def test_position_failure_keeps_departure_estimate(monkeypatch):
    async def post(client, url, **kwargs):
        if url.endswith("/mapData"):
            raise httpx.ReadTimeout("GPS unavailable")
        html = board(row()).replace(
            "<div>45</div>", '<div>45</div><div class="timetable-direction">1</div>'
        )
        return httpx.Response(200, text=html, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    result = asyncio.run(IdeskaProvider().fetch(NOW))
    detail = next(iter(result["departure_details"].values()))
    assert detail["trip"] == "1"
    assert detail["delay_minutes"] == 10
    assert detail["progress"] is None


@pytest.mark.parametrize("hour,clock", [(21, "21:29"), (6, "6:29")])
def test_departure_fetches_and_matches_live_gps(monkeypatch, hour, clock):
    from homeboard.integrations import ideska

    now = NOW.replace(hour=hour, minute=26)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    async def post(client, url, **kwargs):
        request = httpx.Request("POST", url)
        if url.endswith("/mapData"):
            return httpx.Response(
                200,
                request=request,
                json={
                    "transmitters": [
                        {
                            "cat": 2,
                            "cn": "395045|45|81|Planá n.Luž.,Strkov|0|Planá n.Luž.,Okružní bytovky|0|0|Tábor|Planá n.Luž.,Strkov",
                            "dt": now.strftime("%d.%m.%Y"),
                            "tm": now.strftime("%H:%M:%S"),
                            "x": 49.34251,
                            "y": 14.71661,
                        }
                    ]
                },
            )
        html = board(row(clock=clock, delay="")).replace(
            "<div>45</div>", '<div>45</div><div class="timetable-direction">81</div>'
        )
        return httpx.Response(200, text=html, request=request)

    monkeypatch.setattr(ideska, "datetime", Clock)
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    result = asyncio.run(IdeskaProvider().fetch(now))
    detail = result["departure_details"][result["departures"][0]]
    assert detail["trip"] == "81"
    assert detail["progress"]["latitude"] == 49.34251
    assert detail["progress"]["longitude"] == 14.71661
