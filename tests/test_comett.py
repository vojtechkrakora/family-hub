"""Synthetic fixtures mirror the observed public HTML structure, not vendor API schemas."""

import asyncio
from datetime import date, datetime

import httpx
import pytest

from homeboard.integrations.comett import ComettProvider, parse_timetable, upcoming
from homeboard.providers import PRAGUE


def timetable_html(line="45", entries=None, notes="", valid="platí od 1. 7. 2026"):
    entries = entries if entries is not None else [(7, 34, 0, ""), (8, 24, 0, "")]
    rows = []
    for hour in range(24):
        cells = []
        for column in range(4):
            content = "".join(
                f'<span class="timebox"><span class="time">{minute:02}</span>'
                f'<span class="subline">E</span>{code}</span>'
                for h, minute, col, code in entries
                if h == hour and col == column
            )
            cells.append("<td>" + content + "</td>")
        rows.append(f"<tr><td>{hour}</td>" + "".join(cells) + "</tr>")
    return f"""<section id="jr-station"><div class="jr-header"><h2 id="jr_station_accordion">Zastávka Planá nad Lužnicí, Nad Hejtmanem Lipová alej</h2><span>Platné k datu 20.10.2026</span></div>
<div class="station_lines"><div class="left_dir_box">Linky (směr Strkov):</div><span class="active">{line}</span></div>
<span class="validity_time">{valid}</span>
<table class="jr_main"><tr><td>Pracovní dny</td><td>Soboty</td><td>Neděle a svátky</td><td>Pracovní dny</td></tr>
<tr><td>Hod</td><td>minuty</td><td>minuty</td><td>minuty</td><td>od 1. 7. do 31. 8.</td></tr>
{"".join(rows)}<tr><td colspan="5">{notes}</td></tr></table></section>"""


def parse(line="45", **kwargs):
    return parse_timetable(timetable_html(line, **kwargs), line, date(2026, 10, 20))


def at(value):
    return datetime.fromisoformat(value).replace(tzinfo=PRAGUE)


def test_nearest_across_both_lines_and_exact_departure_boundary():
    tables = [parse("43", entries=[(6, 58, 0, ""), (9, 33, 0, "")]), parse()]
    early = upcoming(tables, at("2026-10-21T07:00"))
    assert early["departures"][0] == "2026-10-21T07:34:00+02:00"
    assert early["departure_details"][early["departures"][0]]["line"] == "45"
    later = upcoming(tables, at("2026-10-21T08:24"))
    assert later["departures"][0] == "2026-10-21T09:33:00+02:00"
    assert later["departure_details"][later["departures"][0]]["line"] == "43"


@pytest.mark.parametrize(
    "day,expected", [("2026-10-24", 8), ("2026-10-25", 9), ("2026-10-28", 9), ("2026-08-03", 10)]
)
def test_weekends_holidays_and_summer(day, expected):
    table = parse(entries=[(7, 0, 0, ""), (8, 0, 1, ""), (9, 0, 2, ""), (10, 0, 3, "")])
    result = upcoming([table], at(day + "T06:00"))
    assert datetime.fromisoformat(result["departures"][0]).hour == expected


def test_school_break_exclusion():
    notes = '<div class="timecode"><span>r</span><span class="text">nejede od 29.10. 2026 do 30.10. 2026, 02.11. 2026</span></div>'
    code = '<span class="timecode">r</span>'
    tables = [parse("43", entries=[(6, 58, 0, code)], notes=notes), parse()]
    for day in ["2026-10-29", "2026-10-30", "2026-11-02"]:
        result = upcoming(tables, at(day + "T06:00"))
        assert result["departure_details"][result["departures"][0]]["line"] == "45"
    ordinary = upcoming(tables, at("2026-10-27T06:00"))
    assert ordinary["departure_details"][ordinary["departures"][0]]["line"] == "43"


def test_midnight_and_dst_offsets():
    table = parse("43", entries=[(0, 38, 2, ""), (5, 2, 2, "")])
    result = upcoming([table], at("2026-10-24T23:50"))
    assert result["departures"][:2] == ["2026-10-25T00:38:00+02:00", "2026-10-25T05:02:00+01:00"]


@pytest.mark.parametrize(
    "before,after",
    [
        ("Lipová alej", "Jiná zastávka"),
        ("směr Strkov", "směr Tábor"),
        ("20.10.2026", "19.10.2026"),
        ("platí od 1. 7. 2026", "platí od 1. 1. 2027"),
        ("platí od 1. 7. 2026", "platí od 1. 7. 2026 do 1. 10. 2026"),
        ("Neděle a svátky", "Jiné dny"),
        ("od 1. 7. do 31. 8.", "od 1. 6. do 31. 8."),
        ('class="subline">E', 'class="subline">X'),
        ('class="time">34', 'class="time">99'),
        ("<td>23</td>", "<td>22</td>"),
    ],
)
def test_changed_or_invalid_source_fails_closed(before, after):
    with pytest.raises(ValueError):
        parse_timetable(timetable_html().replace(before, after), "45", date(2026, 10, 20))


def test_unknown_service_code_rejected():
    with pytest.raises(ValueError, match="Unknown service code"):
        parse(entries=[(7, 34, 0, '<span class="timecode">x</span>')])


def test_validity_end_not_extrapolated():
    table = parse(valid="platí od 1. 7. 2026 do 20. 10. 2026")
    assert upcoming([table], at("2026-10-20T23:00"))["departures"] == []


def test_http_adapter_filters_and_merges_public_pages():
    requested = []

    def handler(request):
        requested.append(str(request.url))
        line = "43" if "linka-43" in request.url.path else "45"
        return httpx.Response(
            200, headers={"content-type": "text/html; charset=utf-8"}, text=timetable_html(line)
        )

    provider = ComettProvider(httpx.MockTransport(handler))
    result = asyncio.run(provider.fetch(at("2026-10-20T07:00")))
    assert len(requested) == 2
    assert all("/cz/zastavkove-jizdni-rady-mhd/" in url for url in requested)
    assert result["departures"][0].endswith("07:34:00+02:00")
    assert result["delay_minutes"] is None
    assert provider.source == "scheduled"


@pytest.mark.parametrize(
    "status,content_type,body",
    [
        (429, "text/html", "limited"),
        (500, "text/html", "failed"),
        (302, "text/html", "redirect"),
        (200, "application/json", "{}"),
        (200, "text/html", "x" * 2_000_001),
    ],
)
def test_http_failure_or_oversize_not_presented_as_empty_schedule(status, content_type, body):
    provider = ComettProvider(
        httpx.MockTransport(
            lambda request: httpx.Response(
                status, headers={"content-type": content_type}, text=body
            )
        )
    )
    with pytest.raises((ValueError, httpx.HTTPStatusError)):
        asyncio.run(provider.fetch(at("2026-10-20T07:00")))
