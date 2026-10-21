"""Independent demo adapters. All returned information is fictional."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

PRAGUE = ZoneInfo("Europe/Prague")


class MockTransportProvider:
    source = "mock"

    async def fetch(self, now: datetime) -> dict:
        next_slot = (int(now.timestamp()) // 900 + 1) * 900
        return {
            "origin": "Planá nad Lužnicí, Lipová alej",
            "destination": "Planá nad Lužnicí, náměstí",
            "departures": [datetime.fromtimestamp(next_slot + i * 900, PRAGUE) for i in range(3)],
            "delay_minutes": None,
        }


class MockSchoolProvider:
    source = "mock"

    async def fetch(self, now: datetime) -> dict:
        today = now.astimezone(PRAGUE).date()
        return {
            "homework": [
                {"subject": "Matematika", "title": "Zlomky · strana 24", "due": today},
                {"subject": "Čtení", "title": "Přečíst kapitolu", "due": today + timedelta(days=1)},
            ]
        }


class MockCalendarProvider:
    source = "mock"

    async def fetch(self, now: datetime) -> dict:
        today = now.astimezone(PRAGUE).date()
        return {
            "events": [
                {
                    "title": "Kroužek",
                    "calendar": "Děti",
                    "starts_at": datetime.combine(today, time(15, 30), PRAGUE),
                },
                {
                    "title": "Společná večeře",
                    "calendar": "Rodina",
                    "starts_at": datetime.combine(today, time(18), PRAGUE),
                },
            ]
        }
