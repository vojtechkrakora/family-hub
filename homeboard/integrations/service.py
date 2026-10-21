"""Independent refresh, timeouts and short-lived in-memory caches."""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from time import monotonic
from typing import Literal, Protocol

from homeboard.integrations.models import IntegrationData

logger = logging.getLogger("homeboard.integrations")
Source = Literal["mock", "scheduled", "live"]


class Provider(Protocol):
    source: Source

    async def fetch(self, now: datetime) -> dict:
        """Use non-blocking I/O and propagate cancellation; never return credentials."""
        ...


class CachedIntegration:
    def __init__(
        self,
        name: str,
        provider: Provider | None,
        schema: type[IntegrationData],
        refresh_seconds: float,
        timeout_seconds: float = 3,
        retry_seconds: float = 30,
        refresh_policy: Callable[[IntegrationData, datetime], float] | None = None,
    ) -> None:
        self.name = name
        self.provider = provider
        self.schema = schema
        self.refresh_seconds = refresh_seconds
        self.refresh_policy = refresh_policy
        self.timeout_seconds = timeout_seconds
        self.retry_seconds = retry_seconds
        self.data: IntegrationData | None = None
        self.last_success: datetime | None = None
        self.failed = False
        self.next_attempt = 0.0
        self.lock = asyncio.Lock()
        if provider is not None and provider.source not in ("mock", "scheduled", "live"):
            raise ValueError("Unknown integration source")

    async def snapshot(self, now: datetime) -> dict:
        if self.provider is None:
            return {"source": None, "status": "disabled", "last_success": None, "data": None}
        async with self.lock:
            if monotonic() >= self.next_attempt:
                try:
                    raw = await asyncio.wait_for(self.provider.fetch(now), self.timeout_seconds)
                    validated = self.schema.model_validate(raw)
                except Exception:  # noqa: BLE001 - Provider failures must not expose secrets or break siblings.
                    self.failed = True
                    self.next_attempt = monotonic() + self.retry_seconds
                    logger.warning('{"event":"integration_failed","integration":"%s"}', self.name)
                else:
                    self.data = validated
                    self.last_success = now
                    self.failed = False
                    interval = (
                        self.refresh_policy(validated, now)
                        if self.refresh_policy
                        else self.refresh_seconds
                    )
                    self.next_attempt = monotonic() + interval
            status = "unavailable" if self.data is None else "stale" if self.failed else "available"
            return {
                "source": self.provider.source,
                "status": status,
                "last_success": self.last_success.isoformat() if self.last_success else None,
                "data": self.data.model_dump(mode="json") if self.data is not None else None,
            }
