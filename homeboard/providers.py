"""Demo adapter. All returned information is fictional."""

from datetime import datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

PRAGUE = ZoneInfo("Europe/Prague")


class DashboardProvider(Protocol):
    def snapshot(self, now: datetime) -> dict: ...


class MockProvider:
    def snapshot(self, now: datetime) -> dict:
        # Fixed quarter-hour slots keep departures stable between refreshes.
        next_slot = (int(now.timestamp()) // 900 + 1) * 900
        departures = [datetime.fromtimestamp(next_slot + i * 900, PRAGUE) for i in range(3)]
        today = now.astimezone(PRAGUE).date()
        return {
            "source": "mock",
            "generated_at": now.isoformat(),
            "transport": {
                "origin": "Planá nad Lužnicí, Lipová alej",
                "destination": "Planá nad Lužnicí, náměstí",
                "departures": [item.isoformat() for item in departures],
                "delay_minutes": None,
            },
            "homework": [
                {
                    "subject": "Matematika",
                    "title": "Zlomky · strana 24",
                    "due": today.isoformat(),
                },
                {
                    "subject": "Čtení",
                    "title": "Přečíst kapitolu",
                    "due": (today + timedelta(days=1)).isoformat(),
                },
            ],
            "events": [
                {"time": "15:30", "title": "Kroužek", "calendar": "Děti"},
                {"time": "18:00", "title": "Společná večeře", "calendar": "Rodina"},
            ],
        }
