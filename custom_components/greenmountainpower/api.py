"""API client for Green Mountain Power."""

from __future__ import annotations

import datetime
import enum
import logging
from dataclasses import dataclass, field

from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)

_CLIENT_ID = "C95D19408B024BD4BEB42FA66F08BCEA"
_BASE_URL = "https://api.greenmountainpower.com"
_TOKEN_URL = f"{_BASE_URL}/api/v2/applications/token"


class GreenMountainPowerApiError(Exception):
    """General API error."""


class GreenMountainPowerAuthError(GreenMountainPowerApiError):
    """Authentication error."""


class UsagePrecision(enum.Enum):
    """Usage data resolution."""

    MONTHLY = "monthly"
    DAILY = "daily"
    HOURLY = "hourly"


@dataclass(slots=True)
class UsageRecord:
    """A single usage interval from the API."""

    start_time: datetime.datetime
    consumed_kwh: float
    raw: dict = field(repr=False)


@dataclass(slots=True)
class AccountStatus:
    """Account status from the API."""

    account_number: str | None = None
    active: bool | None = None
    current_balance: float | None = None
    payoff_balance: float | None = None
    raw: dict = field(default_factory=dict, repr=False)


class GreenMountainPowerApi:
    """Async client for the Green Mountain Power API."""

    def __init__(
        self,
        session: ClientSession,
        account_number: int,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._account_number = account_number
        self._username = username
        self._password = password
        self._access_token: str | None = None
        self._token_expiry: datetime.datetime | None = None

    async def _ensure_token(self) -> None:
        """Fetch a token if we don't have a valid one."""
        if (
            self._access_token
            and self._token_expiry
            and datetime.datetime.now() < self._token_expiry
        ):
            return
        await self._fetch_token()

    async def _fetch_token(self) -> None:
        """Fetch an OAuth2 access token."""
        resp = await self._session.post(
            _TOKEN_URL,
            params={
                "grant_type": "password",
                "username": self._username,
                "password": self._password,
                "client_id": _CLIENT_ID,
            },
        )
        if resp.status == 401:
            raise GreenMountainPowerAuthError("Invalid credentials")
        if resp.status != 200:
            text = await resp.text()
            raise GreenMountainPowerApiError(
                f"Token request failed ({resp.status}): {text}"
            )

        data = await resp.json()
        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._token_expiry = datetime.datetime.now() + datetime.timedelta(
            seconds=max(expires_in - 60, 30)
        )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        """Make an authenticated request with automatic token refresh on 401."""
        await self._ensure_token()
        resp = await self._session.request(
            method, url, headers=self._headers(), **kwargs
        )

        if resp.status == 401:
            await self._fetch_token()
            resp = await self._session.request(
                method, url, headers=self._headers(), **kwargs
            )

        if resp.status == 400:
            data = await resp.json()
            raise GreenMountainPowerApiError(data.get("message", "Bad request"))
        if resp.status == 401:
            data = await resp.json()
            raise GreenMountainPowerAuthError(data.get("message", "Unauthorized"))

        resp.raise_for_status()
        return await resp.json()

    async def authenticate(self) -> None:
        """Test credentials by fetching a token."""
        await self._fetch_token()

    async def get_usage(
        self,
        precision: UsagePrecision,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
    ) -> list[UsageRecord]:
        """Fetch usage data for the given time range."""
        url = (
            f"{_BASE_URL}/api/v2/usage/"
            f"{self._account_number}/{precision.value}"
        )
        data = await self._request(
            "GET",
            url,
            params={
                "startDate": start_time.astimezone().isoformat(),
                "endDate": end_time.astimezone().isoformat(),
            },
        )

        records: list[UsageRecord] = []
        raw_keys_logged = False
        for interval in data.get("intervals", []):
            for value in interval.get("values", []):
                if not raw_keys_logged:
                    _LOGGER.debug(
                        "GMP usage API raw value keys: %s", list(value.keys())
                    )
                    raw_keys_logged = True
                try:
                    records.append(
                        UsageRecord(
                            start_time=datetime.datetime.strptime(
                                value["date"], "%Y-%m-%dT%H:%M:%SZ"
                            ),
                            consumed_kwh=float(value["consumed"]),
                            raw=value,
                        )
                    )
                except (KeyError, ValueError, TypeError):
                    continue

        return records

    async def get_account_status(self) -> AccountStatus:
        """Fetch account status."""
        url = f"{_BASE_URL}/api/v2/accounts/{self._account_number}/status"
        data = await self._request("GET", url)

        _LOGGER.debug("GMP account status raw keys: %s", list(data.keys()))

        return AccountStatus(
            account_number=data.get("accountNumber"),
            active=data.get("active"),
            current_balance=(
                float(data["currentBalance"])
                if data.get("currentBalance") is not None
                else None
            ),
            payoff_balance=(
                float(data["payoffBalance"])
                if data.get("payoffBalance") is not None
                else None
            ),
            raw=data,
        )
