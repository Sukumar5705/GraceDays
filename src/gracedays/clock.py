from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


class Clock:
    """Timezone-aware clock with an injectable date for deterministic tests."""

    def __init__(self, timezone: str = "Asia/Kolkata", fake_today: str | None = None) -> None:
        self._tz = ZoneInfo(timezone)
        self._fake_today = date.fromisoformat(fake_today) if fake_today else None

    def today(self) -> date:
        if self._fake_today is not None:
            return self._fake_today
        return datetime.now(self._tz).date()

    @property
    def timezone_name(self) -> str:
        return str(self._tz)
