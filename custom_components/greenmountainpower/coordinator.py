"""Data coordinator for Green Mountain Power."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import logging
import re
from zoneinfo import ZoneInfo

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    GreenMountainPowerApi,
    GreenMountainPowerApiError,
    GreenMountainPowerAuthError,
    UsagePrecision,
)
from .const import (
    CONF_ACCOUNT_NUMBER,
    CONF_DAILY_SYNC_TIME,
    CONF_HISTORY_DAYS,
    CONF_SYNC_INTERVAL_HOURS,
    CONF_SYNC_MODE,
    DEFAULT_DAILY_SYNC_TIME,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_SYNC_INTERVAL_HOURS,
    DEFAULT_SYNC_MODE,
    DOMAIN,
    FALLBACK_UPDATE_INTERVAL,
    SYNC_MODE_DAILY,
    SYNC_MODE_INTERVAL,
)
from .models import GMPStoredData, GMPUsageRecord
from .storage import GMPHistoryStore

_LOGGER = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")


@dataclass(slots=True)
class GMPData:
    """Combined Green Mountain Power data."""

    latest_hour_kwh: float | None
    latest_hour_start: datetime | None
    imported_hourly_records: int
    last_history_refresh: str | None
    statistic_id: str
    sync_mode: str
    sync_interval_hours: int
    daily_sync_time: str
    history_days: int


class GMPDataUpdateCoordinator(DataUpdateCoordinator[GMPData]):
    """Fetch data and import historical hourly statistics."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.config_entry = entry
        self.history_store = GMPHistoryStore(hass, entry)
        self._api = GreenMountainPowerApi(
            session=async_get_clientsession(hass),
            account_number=int(entry.data[CONF_ACCOUNT_NUMBER]),
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=FALLBACK_UPDATE_INTERVAL,
        )
        self._apply_schedule_options()

    def _options(self) -> dict:
        return {
            CONF_SYNC_MODE: self.config_entry.options.get(
                CONF_SYNC_MODE, DEFAULT_SYNC_MODE
            ),
            CONF_SYNC_INTERVAL_HOURS: int(
                self.config_entry.options.get(
                    CONF_SYNC_INTERVAL_HOURS, DEFAULT_SYNC_INTERVAL_HOURS
                )
            ),
            CONF_DAILY_SYNC_TIME: self.config_entry.options.get(
                CONF_DAILY_SYNC_TIME, DEFAULT_DAILY_SYNC_TIME
            ),
            CONF_HISTORY_DAYS: int(
                self.config_entry.options.get(
                    CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS
                )
            ),
        }

    def _apply_schedule_options(self) -> None:
        options = self._options()
        if options[CONF_SYNC_MODE] == SYNC_MODE_INTERVAL:
            self.update_interval = timedelta(
                hours=options[CONF_SYNC_INTERVAL_HOURS]
            )
        else:
            self.update_interval = self._compute_daily_interval(
                options[CONF_DAILY_SYNC_TIME]
            )

    def _compute_daily_interval(self, daily_time_value: str | dict) -> timedelta:
        now_et = datetime.now(_ET)
        try:
            if isinstance(daily_time_value, dict):
                target_time = time(
                    hour=int(daily_time_value["hour"]),
                    minute=int(daily_time_value.get("minute", 0)),
                )
            else:
                hour_str, minute_str = daily_time_value.split(":")
                target_time = time(hour=int(hour_str), minute=int(minute_str))
        except Exception:
            target_time = time(hour=5, minute=0)

        next_run = datetime.combine(now_et.date(), target_time, tzinfo=_ET)
        if next_run <= now_et:
            next_run += timedelta(days=1)

        interval = next_run - now_et
        return interval if interval > timedelta(minutes=1) else timedelta(minutes=1)

    async def async_refresh_history(self) -> None:
        """Manual refresh using the configured lookback window."""
        await self._async_standalone_sync(self._options()[CONF_HISTORY_DAYS])

    async def _async_standalone_sync(self, history_days: int) -> None:
        """Fetch and import statistics without affecting coordinator state.

        Errors are logged but never make sensors unavailable.
        """
        statistic_id = self._statistic_id()
        metadata = self._metadata(statistic_id)

        now_et = datetime.now(_ET)
        start_time = (now_et - timedelta(days=history_days)).replace(
            minute=0, second=0, microsecond=0
        )

        try:
            hourly_history = await self._api.get_usage(
                precision=UsagePrecision.HOURLY,
                start_time=start_time,
                end_time=now_et,
            )
        except GreenMountainPowerAuthError:
            _LOGGER.error("Authentication failed during manual sync")
            return
        except (GreenMountainPowerApiError, Exception):
            _LOGGER.exception("Failed to fetch usage data during manual sync")
            return

        stored = await self.history_store.async_load()

        for item in hourly_history:
            start_utc = self._normalize_start_time(item.start_time)
            key = start_utc.isoformat()
            stored.hourly[key] = GMPUsageRecord(
                start_time=key,
                consumed_kwh=round(item.consumed_kwh, 6),
            )

        stored.last_history_refresh = dt_util.utcnow().isoformat()

        statistics = self._build_statistics(stored)

        if statistics:
            try:
                async_add_external_statistics(self.hass, metadata, statistics)
            except HomeAssistantError as err:
                _LOGGER.error("Failed to import statistics: %s", err)
                return

        await self.history_store.async_save(stored)
        _LOGGER.info(
            "Manual sync complete: fetched %d records (%d days), "
            "%d total stored",
            len(hourly_history),
            history_days,
            len(stored.hourly),
        )

    def _statistic_id(self) -> str:
        account_number = str(self.config_entry.data[CONF_ACCOUNT_NUMBER])
        account_slug = re.sub(
            r"[^a-z0-9]+", "_", account_number.lower()
        ).strip("_")
        if not account_slug:
            account_slug = (
                self.config_entry.entry_id.replace("-", "_").lower()
            )
        return f"{DOMAIN}:account_{account_slug}_energy_consumption"

    def _metadata(self, statistic_id: str) -> StatisticMetaData:
        account_number = str(self.config_entry.data[CONF_ACCOUNT_NUMBER])
        return StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=f"Green Mountain Power {account_number} energy consumption",
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_class="energy",
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )

    def _normalize_start_time(self, start_time: datetime) -> datetime:
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=_ET)
        return dt_util.as_utc(start_time)

    def _build_statistics(
        self, stored: GMPStoredData
    ) -> list[StatisticData]:
        """Build the StatisticData list from all stored records."""
        statistics: list[StatisticData] = []
        running_sum = 0.0
        for key in sorted(stored.hourly):
            record = stored.hourly[key]
            running_sum = round(running_sum + record.consumed_kwh, 6)
            statistics.append(
                StatisticData(
                    start=datetime.fromisoformat(record.start_time),
                    state=record.consumed_kwh,
                    sum=running_sum,
                )
            )
        return statistics

    async def _async_update_data(self) -> GMPData:
        options = self._options()
        history_days = options[CONF_HISTORY_DAYS]
        statistic_id = self._statistic_id()
        metadata = self._metadata(statistic_id)

        now_et = datetime.now(_ET)
        start_time = (now_et - timedelta(days=history_days)).replace(
            minute=0, second=0, microsecond=0
        )

        try:
            hourly_history = await self._api.get_usage(
                precision=UsagePrecision.HOURLY,
                start_time=start_time,
                end_time=now_et,
            )
        except GreenMountainPowerAuthError as err:
            raise ConfigEntryAuthFailed("Authentication failed") from err
        except GreenMountainPowerApiError as err:
            raise UpdateFailed(
                f"Unable to fetch hourly usage data: {err}"
            ) from err

        stored = await self.history_store.async_load()

        for item in hourly_history:
            start_utc = self._normalize_start_time(item.start_time)
            key = start_utc.isoformat()
            stored.hourly[key] = GMPUsageRecord(
                start_time=key,
                consumed_kwh=round(item.consumed_kwh, 6),
            )

        stored.last_history_refresh = dt_util.utcnow().isoformat()

        statistics = self._build_statistics(stored)

        if statistics:
            try:
                async_add_external_statistics(self.hass, metadata, statistics)
            except HomeAssistantError as err:
                _LOGGER.error(
                    "Failed to import statistics (id=%s): %s",
                    metadata.get("statistic_id"),
                    err,
                )
                raise UpdateFailed(
                    f"Failed to import statistics: {err}"
                ) from err

        await self.history_store.async_save(stored)
        self._apply_schedule_options()

        latest_hour_kwh = None
        latest_hour_start = None
        if statistics:
            latest_hour_kwh = statistics[-1]["state"]
            latest_hour_start = statistics[-1]["start"]

        return GMPData(
            latest_hour_kwh=latest_hour_kwh,
            latest_hour_start=latest_hour_start,
            imported_hourly_records=len(stored.hourly),
            last_history_refresh=stored.last_history_refresh,
            statistic_id=statistic_id,
            sync_mode=options[CONF_SYNC_MODE],
            sync_interval_hours=options[CONF_SYNC_INTERVAL_HOURS],
            daily_sync_time=options[CONF_DAILY_SYNC_TIME],
            history_days=options[CONF_HISTORY_DAYS],
        )
