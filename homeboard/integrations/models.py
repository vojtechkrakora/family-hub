"""Internal data contracts, not assumptions about third-party response schemas."""

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class IntegrationData(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VehicleProgress(IntegrationData):
    state: Literal["approaching", "town", "crossing", "waiting_crossing", "passed", "strkovska"]
    observed_at: AwareDatetime
    passed_crossing: bool
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)


class DepartureDetails(IntegrationData):
    line: str
    destination: str
    trip: str | None = None
    progress: VehicleProgress | None = None
    scheduled_at: AwareDatetime | None = None
    delay_minutes: int | None = None
    reported_at: AwareDatetime | None = None


class TransportData(IntegrationData):
    origin: str
    destination: str
    departures: list[AwareDatetime] = Field(max_length=100)
    delay_minutes: int | None = None
    departure_details: dict[str, DepartureDetails] = Field(default_factory=dict)


class Homework(IntegrationData):
    subject: str
    title: str
    due: date


class SchoolData(IntegrationData):
    homework: list[Homework] = Field(max_length=100)


class CalendarEvent(IntegrationData):
    title: str
    calendar: str
    starts_at: AwareDatetime
    ends_at: AwareDatetime | None = None
    all_day: bool = False


class CalendarData(IntegrationData):
    events: list[CalendarEvent] = Field(max_length=100)
