# Green Mountain Power - Home Assistant Integration

A custom Home Assistant integration that fetches hourly electricity usage from the Green Mountain Power (GMP) API and stores it as long-term statistics under the **actual usage timestamp**, not the time the data was retrieved. This is important because the GMP API runs approximately 8 hours behind real time.

## How It Works

The GMP API returns hourly energy consumption data on a delay. If you query at noon, the most recent data point might be from 4:00 AM. Normal Home Assistant sensors would record that 4:00 AM reading as a noon data point, making your energy graphs inaccurate.

This integration solves that by using Home Assistant's **external statistics API** (`async_add_external_statistics`). Each hourly reading is imported with its real timestamp, so a 4:00 AM reading appears at 4:00 AM on your Energy Dashboard -- even if it wasn't fetched until noon.

## Installation

1. Copy the `custom_components/greenmountainpower/` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings > Devices & Services > Add Integration** and search for **Green Mountain Power**.
4. Enter your GMP account number, username, and password.

## Configuration

### Initial Setup

You will be prompted for:

| Field | Description |
|---|---|
| **Account number** | Your GMP account number (found on your bill) |
| **Username** | Your GMP online account username |
| **Password** | Your GMP online account password |

### Options (Settings > Devices & Services > Green Mountain Power > Configure)

Options are presented in a two-step flow. Step 1 selects the sync mode; step 2 shows only the fields relevant to that mode.

**Step 1 -- Sync Mode:**

| Mode | Description |
|---|---|
| **Every N hours** | Fetches new data on a recurring interval (1--24 hours) |
| **Once daily at a specific time** | Fetches new data once per day at a chosen time |

**Step 2 -- Schedule & Lookback:**

| Field | Appears when | Description | Default |
|---|---|---|---|
| **Sync interval** | Every N hours | How often to fetch (slider, 1--24 hours) | 6 hours |
| **Sync time** | Once daily | What time to fetch each day (time picker) | 05:00 |
| **Sync lookback days** | Both modes | How many days of historical data to request from the API on each sync | 30 days |

The lookback window determines how far back each sync requests data. On every sync, any new or updated records within that window are merged into the local store and re-imported as statistics. Records already stored are deduplicated by their UTC timestamp key.

## Entities

All entities are grouped under a single device named **Green Mountain Power {account_number}**.

### Sensors

| Entity | Description |
|---|---|
| **Latest Hourly Usage** | The kWh consumed in the most recent hourly interval available from the API. Unit: kWh. |
| **Latest Hourly Interval Start** | The timestamp of the most recent hourly interval (useful for seeing how far behind the API is). |
| **Imported Hourly Records** | The total number of hourly records stored locally. |

Each sensor also exposes these as extra state attributes: `account_number`, `imported_hourly_records`, `last_history_refresh`, `statistic_id`, `sync_mode`, `sync_interval_hours`, `daily_sync_time`, `history_days`.

### Buttons

| Entity | Description |
|---|---|
| **Sync Now** | Triggers an immediate manual sync using the configured lookback window. Runs independently of the coordinator -- if it fails, your sensors remain unaffected. |

### Statistics (Energy Dashboard)

The primary data produced by this integration is a long-term statistic, not the sensor entities above. The statistic ID follows this format:

```
greenmountainpower:account_{account_number}_energy_consumption
```

To use it in the **Energy Dashboard**:
1. Go to **Settings > Dashboards > Energy**.
2. Under **Electricity Grid > Grid Consumption**, click **Add consumption**.
3. Search for the statistic ID shown in your sensor's `statistic_id` attribute.

Each statistic entry contains:
- **`start`** -- The real UTC timestamp of the usage hour
- **`state`** -- The kWh consumed during that hour
- **`sum`** -- The cumulative kWh total from the first recorded hour onward

## Services

### `greenmountainpower.refresh_history`

Triggers a manual sync identical to pressing the **Sync Now** button.

| Parameter | Required | Description |
|---|---|---|
| `entry_id` | No | Limit the refresh to a specific config entry (useful if you have multiple GMP accounts) |

## Architecture

### File Structure

```
custom_components/greenmountainpower/
  __init__.py       Integration setup, service registration, options reload listener
  api.py            Async GMP API client (OAuth2 auth, usage & account endpoints)
  button.py         "Sync Now" button entity
  config_flow.py    Setup wizard and two-step options flow
  const.py          Constants and default values
  coordinator.py    DataUpdateCoordinator -- scheduled syncs and statistics import
  manifest.json     Integration metadata
  models.py         Data models for storage and runtime
  sensor.py         Helper sensor entities
  services.yaml     Service definitions
  storage.py        Persistent storage wrapper (HA Store helper)
  strings.json      Translation source strings
  translations/
    en.json         English translations
```

### Data Flow

```
GMP API  -->  api.py (fetch hourly usage)
                |
                v
         coordinator.py
           |                          |
           v                          v
     storage.py (persist)    async_add_external_statistics()
     local JSON store         HA recorder long-term stats
                                      |
                                      v
                              Energy Dashboard
```

1. **Fetch**: The coordinator calls `api.py` to fetch hourly usage for the configured lookback window.
2. **Store**: New records are merged into a persistent JSON store (keyed by UTC ISO timestamp) for deduplication.
3. **Import**: All stored records are sorted chronologically, a running cumulative sum is computed, and the full list is imported as external statistics via `async_add_external_statistics`.
4. **Display**: The Energy Dashboard reads the imported statistics and displays accurate hourly energy consumption charts.

### API Client (`api.py`)

The integration communicates directly with GMP's REST API (no external library dependency).

- **Authentication**: OAuth2 Resource Owner Password Credentials grant. Tokens are fetched from `POST /api/v2/applications/token` with the client ID `C95D19408B024BD4BEB42FA66F08BCEA`. Tokens auto-refresh on 401 responses.
- **Usage endpoint**: `GET /api/v2/usage/{account}/{precision}` with `startDate` and `endDate` query params (ISO 8601). Returns JSON with `intervals[].values[]` containing `date` and `consumed` fields.
- **Account status endpoint**: `GET /api/v2/accounts/{account}/status`. Returns balance and account info.
- **Raw response preservation**: Each `UsageRecord` stores the full raw API response dict, and the first response's keys are logged at DEBUG level -- useful for discovering undocumented fields (e.g., potential cost/rate data).

### Scheduled vs. Manual Syncs

- **Scheduled syncs** (`_async_update_data`) run through Home Assistant's `DataUpdateCoordinator`. If they fail, the coordinator marks sensors as unavailable and retries on the next interval.
- **Manual syncs** (`_async_standalone_sync`, triggered by the Sync Now button or the `refresh_history` service) run independently of the coordinator. Errors are logged but never affect sensor availability.

### Timestamp Handling

The GMP API returns naive datetime strings in Eastern Time (e.g., `2026-04-13T04:00:00Z` is actually ET despite the `Z` suffix). The integration:
1. Treats naive timestamps as `America/New_York`
2. Converts to UTC for storage keys and statistics import
3. Home Assistant handles display timezone conversion automatically

### Persistent Storage

Hourly records are persisted to `.storage/greenmountainpower.{entry_id}` using Home Assistant's `Store` helper (version 3). The store contains:
- `hourly`: A dict of UTC ISO timestamp keys to `{start_time, consumed_kwh}` records
- `last_history_refresh`: The UTC timestamp of the most recent successful sync

This store serves two purposes:
1. **Deduplication**: Records fetched in overlapping lookback windows are merged by key, not duplicated.
2. **Cumulative sum consistency**: The running sum for statistics is always recalculated from the complete set of stored records, ensuring the Energy Dashboard sees a monotonically increasing total.

## Debugging

Enable debug logging by adding this to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.greenmountainpower: debug
```

This will log:
- Raw API response field names (to discover undocumented fields like cost data)
- Manual sync results (record counts)
- Any statistics import errors with the full statistic ID

## Known Limitations

- **API delay**: GMP data is approximately 8 hours behind real time. This is a GMP limitation, not an integration bug.
- **No cost/rate data**: The GMP API returns `date` and `consumed` per interval. No per-kWh pricing or cost fields have been observed. The integration preserves the raw API response -- if GMP adds cost fields in the future, they will appear in debug logs.
- **Lookback window limit**: The GMP API may not support requests spanning more than ~30 days of hourly data in a single call. The default lookback of 30 days is safe; significantly larger values may cause API errors.

## Version History

### v0.7.0
- Replaced the external `greenmountainpower` library with a built-in async API client
- Fixed "Invalid statistic_id" error (switched from `async_import_statistics` to `async_add_external_statistics`)
- Fixed `StatisticMetaData` construction to match the current HA recorder API
- Added "Sync Now" button entity
- Manual syncs no longer affect sensor availability on failure
- Two-step options flow shows only the relevant scheduling fields
- Removed full sync feature (not supported by the GMP API)
- Removed `OptionsFlowWithReload` dependency for broader HA compatibility
