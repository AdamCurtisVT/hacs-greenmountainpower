"""Button platform for Green Mountain Power."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ACCOUNT_NUMBER, DEFAULT_NAME, DOMAIN
from .coordinator import GMPDataUpdateCoordinator

BUTTON_DESCRIPTIONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="sync_now",
        translation_key="sync_now",
        name="Sync Now",
        icon="mdi:sync",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GMPDataUpdateCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        GMPButton(coordinator, entry, description)
        for description in BUTTON_DESCRIPTIONS
    )


class GMPButton(ButtonEntity):
    """Button to trigger a GMP sync."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GMPDataUpdateCoordinator,
        entry: ConfigEntry,
        description: ButtonEntityDescription,
    ) -> None:
        self.entity_description = description
        self._coordinator = coordinator
        self._entry = entry
        account_number = str(entry.data[CONF_ACCOUNT_NUMBER])
        self._attr_unique_id = f"{account_number}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        account_number = str(self._entry.data[CONF_ACCOUNT_NUMBER])
        return DeviceInfo(
            identifiers={(DOMAIN, account_number)},
            manufacturer="Green Mountain Power",
            model="Utility Account",
            name=f"{DEFAULT_NAME} {account_number}",
        )

    async def async_press(self) -> None:
        await self._coordinator.async_refresh_history()
