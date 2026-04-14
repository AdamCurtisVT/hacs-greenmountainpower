"""The Green Mountain Power integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, SERVICE_REFRESH_HISTORY
from .coordinator import GMPDataUpdateCoordinator
from .models import GMPRuntimeData

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.SENSOR]


async def _register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""

    async def _handle_refresh_history(service_call: ServiceCall) -> None:
        entry_id = service_call.data.get("entry_id")
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry_id and entry.entry_id != entry_id:
                continue
            await entry.runtime_data.coordinator.async_refresh_history()

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_HISTORY):
        hass.services.async_register(DOMAIN, SERVICE_REFRESH_HISTORY, _handle_refresh_history)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    await _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await _register_services(hass)

    coordinator = GMPDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = GMPRuntimeData(coordinator=coordinator)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
