"""Countdown logic independent of transport providers."""

from datetime import datetime
from math import ceil


def countdown(
    departure: datetime, now: datetime, walking_minutes: int, warning_minutes: int
) -> dict:
    if departure.utcoffset() is None or now.utcoffset() is None:
        raise ValueError("Timezone-aware timestamps are required")
    if walking_minutes < 0 or warning_minutes < 0:
        raise ValueError("Thresholds must be non-negative")
    # Timestamps measure elapsed time correctly across DST changes.
    seconds = departure.timestamp() - now.timestamp()
    leave_seconds = seconds - walking_minutes * 60
    status = (
        "departed"
        if seconds <= 0
        else (
            "leave_now"
            if leave_seconds <= 0
            else ("prepare" if leave_seconds <= warning_minutes * 60 else "comfortable")
        )
    )
    return {
        "departure_minutes": max(0, ceil(seconds / 60)),
        "leave_minutes": max(0, ceil(leave_seconds / 60)),
        "status": status,
    }


def morning_routine(
    departure: datetime, dressing_minutes: int, shoes_minutes: int, walking_minutes: int
) -> list[dict]:
    """Return absolute stage boundaries so clients do not duplicate timing rules."""
    if departure.utcoffset() is None:
        raise ValueError("Timezone-aware timestamps are required")
    if dressing_minutes <= 0 or shoes_minutes <= 0 or walking_minutes < 0:
        raise ValueError("Preparation durations must be positive; walking must be non-negative")
    end = departure.timestamp() * 1000
    leave = end - walking_minutes * 60000
    shoes = leave - shoes_minutes * 60000
    dress = shoes - dressing_minutes * 60000
    return [
        {"id": "relax", "until": dress},
        {"id": "dress", "until": shoes},
        {"id": "shoes", "until": leave},
        {"id": "go", "until": end},
    ]
