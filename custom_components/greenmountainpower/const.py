"""Constants for the Green Mountain Power integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "greenmountainpower"
CONF_ACCOUNT_NUMBER = "account_number"

DEFAULT_NAME = "Green Mountain Power"

CONF_SYNC_MODE = "sync_mode"
CONF_SYNC_INTERVAL_HOURS = "sync_interval_hours"
CONF_DAILY_SYNC_TIME = "daily_sync_time"
CONF_HISTORY_DAYS = "history_days"
SYNC_MODE_INTERVAL = "interval"
SYNC_MODE_DAILY = "daily"

DEFAULT_SYNC_MODE = SYNC_MODE_DAILY
DEFAULT_SYNC_INTERVAL_HOURS = 6
DEFAULT_DAILY_SYNC_TIME = "05:00"
DEFAULT_HISTORY_DAYS = 30

FALLBACK_UPDATE_INTERVAL = timedelta(hours=24)

STORAGE_VERSION = 3
STORAGE_KEY_TEMPLATE = f"{DOMAIN}.{{entry_id}}"

SERVICE_REFRESH_HISTORY = "refresh_history"
