"""Sensor platform for Green Mountain Power."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ACCOUNT_NUMBER, DEFAULT_NAME, DOMAIN
from .coordinator import GMPData, GMPDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class GMPSensorDescription(SensorEntityDescription):
    """Describe a GMP sensor."""

    value_fn: Callable[[GMPData], Any]


def _common_attrs(data: GMPData, account_number: str) -> dict[str, Any]:
    return {
        "account_number": account_number,
        "imported_hourly_records": data.imported_hourly_records,
        "last_history_refresh": data.last_history_refresh,
        "statistic_id": data.statistic_id,
        "sync_mode": data.sync_mode,
        "sync_interval_hours": data.sync_interval_hours,
        "daily_sync_time": data.daily_sync_time,
        "history_days": data.history_days,
    }


SENSOR_DESCRIPTIONS: tuple[GMPSensorDescription, ...] = (
    GMPSensorDescription(
        key="latest_hourly_usage",
        translation_key="latest_hourly_usage",
        name="Latest Hourly Usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        icon="mdi:transmission-tower",
        value_fn=lambda data: data.latest_hour_kwh,
    ),
    GMPSensorDescription(
        key="latest_hourly_interval_start",
        translation_key="latest_hourly_interval_start",
        name="Latest Hourly Interval Start",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-start",
        value_fn=lambda data: data.latest_hour_start,
    ),
    GMPSensorDescription(
        key="imported_hourly_records",
        translation_key="imported_hourly_records",
        name="Imported Hourly Records",
        icon="mdi:database-clock",
        value_fn=lambda data: data.imported_hourly_records,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GMPDataUpdateCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        GMPSensor(coordinator, entry, description) for description in SENSOR_DESCRIPTIONS
    )


class GMPSensor(CoordinatorEntity[GMPDataUpdateCoordinator], SensorEntity):
    """Representation of a GMP sensor."""

    entity_description: GMPSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GMPDataUpdateCoordinator,
        entry: ConfigEntry,
        description: GMPSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
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

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        account_number = str(self._entry.data[CONF_ACCOUNT_NUMBER])
        return _common_attrs(data, account_number)
