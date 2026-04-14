"""Config flow for Green Mountain Power."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_ACCOUNT_NUMBER,
    CONF_DAILY_SYNC_TIME,
    CONF_HISTORY_DAYS,
    CONF_SYNC_INTERVAL_HOURS,
    CONF_SYNC_MODE,
    DEFAULT_DAILY_SYNC_TIME,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_NAME,
    DEFAULT_SYNC_INTERVAL_HOURS,
    DEFAULT_SYNC_MODE,
    DOMAIN,
    SYNC_MODE_DAILY,
    SYNC_MODE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the user input allows us to connect."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .api import (
        GreenMountainPowerApi,
        GreenMountainPowerApiError,
        GreenMountainPowerAuthError,
    )

    client = GreenMountainPowerApi(
        session=async_get_clientsession(hass),
        account_number=int(data[CONF_ACCOUNT_NUMBER]),
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
    )
    try:
        await client.authenticate()
    except GreenMountainPowerAuthError as err:
        raise InvalidAuth from err
    except GreenMountainPowerApiError as err:
        raise CannotConnect from err


_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SYNC_MODE): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(
                        value=SYNC_MODE_INTERVAL,
                        label="Every N hours",
                    ),
                    selector.SelectOptionDict(
                        value=SYNC_MODE_DAILY,
                        label="Once daily at a specific time",
                    ),
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }
)

_HISTORY_DAYS_SCHEMA = {
    vol.Required(CONF_HISTORY_DAYS): selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=1,
            max=365,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="days",
        )
    ),
}

_INTERVAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SYNC_INTERVAL_HOURS): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=24,
                step=1,
                mode=selector.NumberSelectorMode.SLIDER,
                unit_of_measurement="hours",
            )
        ),
        **_HISTORY_DAYS_SCHEMA,
    }
)

_DAILY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DAILY_SYNC_TIME): selector.TimeSelector(),
        **_HISTORY_DAYS_SCHEMA,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Green Mountain Power."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> GMPOptionsFlow:
        """Get the options flow for this handler."""
        return GMPOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(str(user_input[CONF_ACCOUNT_NUMBER]))
            self._abort_if_unique_id_configured()

            try:
                await _validate_input(self.hass, user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error validating Green Mountain Power credentials")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"{DEFAULT_NAME} {user_input[CONF_ACCOUNT_NUMBER]}",
                    data=user_input,
                    options={
                        CONF_SYNC_MODE: DEFAULT_SYNC_MODE,
                        CONF_SYNC_INTERVAL_HOURS: DEFAULT_SYNC_INTERVAL_HOURS,
                        CONF_DAILY_SYNC_TIME: DEFAULT_DAILY_SYNC_TIME,
                        CONF_HISTORY_DAYS: DEFAULT_HISTORY_DAYS,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_ACCOUNT_NUMBER): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )


class GMPOptionsFlow(config_entries.OptionsFlow):
    """Handle options for the integration."""

    def __init__(self) -> None:
        super().__init__()
        self._options: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ):
        """Step 1: Choose sync mode."""
        if user_input is not None:
            self._options.update(user_input)
            if user_input[CONF_SYNC_MODE] == SYNC_MODE_INTERVAL:
                return await self.async_step_interval()
            return await self.async_step_daily()

        current = {
            CONF_SYNC_MODE: self.config_entry.options.get(
                CONF_SYNC_MODE, DEFAULT_SYNC_MODE
            ),
        }

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _MODE_SCHEMA, current
            ),
        )

    async def async_step_interval(
        self, user_input: dict[str, Any] | None = None
    ):
        """Step 2a: Configure interval hours and lookback days."""
        if user_input is not None:
            self._options.update(user_input)
            self._options.setdefault(
                CONF_DAILY_SYNC_TIME,
                self.config_entry.options.get(
                    CONF_DAILY_SYNC_TIME, DEFAULT_DAILY_SYNC_TIME
                ),
            )
            return self.async_create_entry(data=self._options)

        current = {
            CONF_SYNC_INTERVAL_HOURS: self.config_entry.options.get(
                CONF_SYNC_INTERVAL_HOURS, DEFAULT_SYNC_INTERVAL_HOURS
            ),
            CONF_HISTORY_DAYS: self.config_entry.options.get(
                CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS
            ),
        }

        return self.async_show_form(
            step_id="interval",
            data_schema=self.add_suggested_values_to_schema(
                _INTERVAL_SCHEMA, current
            ),
        )

    async def async_step_daily(
        self, user_input: dict[str, Any] | None = None
    ):
        """Step 2b: Configure daily sync time and lookback days."""
        if user_input is not None:
            self._options.update(user_input)
            self._options.setdefault(
                CONF_SYNC_INTERVAL_HOURS,
                self.config_entry.options.get(
                    CONF_SYNC_INTERVAL_HOURS, DEFAULT_SYNC_INTERVAL_HOURS
                ),
            )
            return self.async_create_entry(data=self._options)

        current = {
            CONF_DAILY_SYNC_TIME: self.config_entry.options.get(
                CONF_DAILY_SYNC_TIME, DEFAULT_DAILY_SYNC_TIME
            ),
            CONF_HISTORY_DAYS: self.config_entry.options.get(
                CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS
            ),
        }

        return self.async_show_form(
            step_id="daily",
            data_schema=self.add_suggested_values_to_schema(
                _DAILY_SCHEMA, current
            ),
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""
