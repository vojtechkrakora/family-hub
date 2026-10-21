"""Synthetic GPS tests for direction, freshness, crossing dwell and trip isolation."""

from datetime import datetime, timedelta

from homeboard.integrations.vehicle import (
    BARBORA,
    CROSSING,
    ProgressTracker,
    observation,
    on_strkovska,
)
from homeboard.providers import PRAGUE

NOW = datetime(2026, 10, 20, 7, 30, tzinfo=PRAGUE)
BEYOND = (49.3481773, 14.7103055)


def fix(point=CROSSING, seconds=0):
    return {"point": point, "observed_at": NOW + timedelta(seconds=seconds), "in_town": True}


def test_crossing_wait_requires_moving_time_not_repeated_fix():
    tracker = ProgressTracker()
    assert tracker.update("45:1", fix())["state"] == "crossing"
    assert tracker.update("45:1", fix())["state"] == "crossing"
    assert tracker.update("45:1", fix(seconds=30))["state"] == "crossing"
    assert tracker.update("45:1", fix(seconds=60))["state"] == "waiting_crossing"


def test_movement_resets_dwell():
    tracker = ProgressTracker()
    tracker.update("a", fix())
    assert tracker.update("a", fix((49.3497, 14.7077), 60))["state"] == "crossing"


def test_two_beyond_fixes_confirm_and_latch_until_trip_change():
    tracker = ProgressTracker()
    assert not tracker.update("a", fix(BEYOND))["passed_crossing"]
    assert tracker.update("a", fix(BEYOND, 30))["state"] == "strkovska"
    assert tracker.update("a", fix(BARBORA, 60))["passed_crossing"]
    assert not tracker.update("b", fix(BEYOND, 65))["passed_crossing"]


def test_gap_and_missing_position_reset_evidence():
    tracker = ProgressTracker()
    tracker.update("a", fix())
    assert tracker.update("a", fix(seconds=90))["state"] == "crossing"
    assert tracker.update("a", None) is None
    assert tracker.update("a", fix(seconds=120))["state"] == "crossing"


def test_boundary_and_off_road_do_not_confirm_crossing():
    assert not on_strkovska(CROSSING)
    assert not on_strkovska(BARBORA)
    assert not on_strkovska((49.346, 14.720))
    assert on_strkovska(BEYOND)


def payload(**updates):
    raw = {
        "cn": "395045|45|1|Planá n.Luž.,Silon|98|Planá n.Luž.,hřbitov|98|901|Tábor,aut.nádr.|Planá n.Luž.,Strkov",
        "cat": 2,
        "x": CROSSING[0],
        "y": CROSSING[1],
        "dt": "20.10.2026",
        "tm": "07:30:00",
    }
    raw.update(updates)
    return {"transmitters": [raw]}


def test_exact_trip_direction_and_freshness():
    assert observation(payload(), "45", "1", NOW)
    assert observation(payload(), "45", "2", NOW) is None
    assert observation(payload(), "43", "1", NOW) is None
    assert observation(payload(), "45", "1", NOW + timedelta(seconds=76)) is None
    assert observation(payload(tm="07:30:01"), "45", "1", NOW) is None
    assert (
        observation(payload(cn="395045|45|1|x|0|y|0|0|Planá n.Luž.,Strkov|Tábor"), "45", "1", NOW)
        is None
    )
    assert observation(payload(x=float("nan")), "45", "1", NOW) is None


def test_duplicate_vehicle_identity_is_ambiguous():
    data = payload()
    data["transmitters"] *= 2
    assert observation(data, "45", "1", NOW) is None


def test_unassigned_vehicle_does_not_hide_matching_trip():
    data = payload()
    data["transmitters"].insert(0, {"cn": None})
    assert observation(data, "45", "1", NOW)


def test_fast_refresh_only_for_fresh_nearby_selected_bus():
    from homeboard.integrations.vehicle import needs_fast_refresh

    departure = (NOW + timedelta(minutes=5)).isoformat()
    progress = {"state": "crossing", "observed_at": NOW.isoformat()}
    data = {"departures": [departure], "departure_details": {departure: {"progress": progress}}}
    for state in ["crossing", "waiting_crossing", "passed", "strkovska"]:
        progress["state"] = state
        assert needs_fast_refresh(data, NOW)
    for state in ["town", "approaching"]:
        progress["state"] = state
        assert not needs_fast_refresh(data, NOW)
    progress["state"] = "crossing"
    assert not needs_fast_refresh(data, NOW + timedelta(seconds=76))
    assert not needs_fast_refresh(data, NOW - timedelta(seconds=1))
    assert not needs_fast_refresh(data, NOW + timedelta(minutes=5))
    assert not needs_fast_refresh(None, NOW)
    earlier = (NOW + timedelta(minutes=1)).isoformat()
    data["departures"].append(earlier)
    assert not needs_fast_refresh(data, NOW)


def test_map_coordinates_are_from_the_matched_fix():
    from homeboard.integrations.models import VehicleProgress

    progress = ProgressTracker().update("45:1", fix(BEYOND))
    data = VehicleProgress.model_validate(progress)
    assert (data.latitude, data.longitude) == BEYOND
    assert data.observed_at == NOW
