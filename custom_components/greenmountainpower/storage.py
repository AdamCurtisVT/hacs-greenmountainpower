"""Storage helpers for the Green Mountain Power integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY_TEMPLATE, STORAGE_VERSION
from .models import GMPStoredData


class GMPHistoryStore:
    """Persisted storage for downloaded hourly usage history."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._store: Store[dict] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY_TEMPLATE.format(entry_id=entry.entry_id),
        )

    async def async_load(self) -> GMPStoredData:
        data = await self._store.async_load()
        return GMPStoredData.from_dict(data)

    async def async_save(self, data: GMPStoredData) -> None:
        await self._store.async_save(data.as_dict())
