"""Models for the Green Mountain Power integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .coordinator import GMPDataUpdateCoordinator


@dataclass(slots=True)
class GMPUsageRecord:
    """A normalized hourly usage record."""

    start_time: str
    consumed_kwh: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GMPUsageRecord":
        return cls(
            start_time=data["start_time"],
            consumed_kwh=float(data["consumed_kwh"]),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "start_time": self.start_time,
            "consumed_kwh": self.consumed_kwh,
        }


@dataclass(slots=True)
class GMPStoredData:
    """Persisted hourly usage history."""

    hourly: dict[str, GMPUsageRecord] = field(default_factory=dict)
    last_history_refresh: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "GMPStoredData":
        if not data:
            return cls()

        return cls(
            hourly={
                key: GMPUsageRecord.from_dict(value)
                for key, value in data.get("hourly", {}).items()
            },
            last_history_refresh=data.get("last_history_refresh"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "hourly": {key: value.as_dict() for key, value in self.hourly.items()},
            "last_history_refresh": self.last_history_refresh,
        }


@dataclass(slots=True)
class GMPRuntimeData:
    """Runtime data attached to the config entry."""

    coordinator: GMPDataUpdateCoordinator
