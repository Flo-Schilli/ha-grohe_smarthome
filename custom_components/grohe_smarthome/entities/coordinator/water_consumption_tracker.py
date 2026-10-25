"""Persist the lifetime water consumption of a Sense Guard and keep it current with deltas.

The only way to get the lifetime total from Grohe is the aggregated-data endpoint, and a
query from the installation date to now gets slower the older the device is (9-60s, with
occasional gateway timeouts). Instead of asking for the whole history again every day,
the history is fetched once - in calendar-year chunks so a single timeout only costs one
chunk - and stored with Home Assistant's Store. After that, only the current and the
previous month are queried, once a day.

Grohe returns whole buckets of the requested grouping and ignores `from`/`to` inside
them: groupBy=YEAR for Jan 1 - Sep 30 returns the whole year so far, groupBy=MONTH for
Oct 1 - Oct 24 the whole month including today. groupBy=MONTH is also a few hundred
liters short per year compared to DAY and YEAR. So whole calendar years are queried
with YEAR and everything else with DAY (see _group_by_for).

Counting starts at the device's installation_date. Data from before it (e.g. from
before the Guard was set up again) is not included.

Stored state:
    base_total    sum of all full days up to and including base_until
    base_until    last day covered by base_total (always the last day of a month)
    months        {"YYYY-MM": total} for the months after base_until
    synced_until  last full day covered by base_total + months; None until the
                  historical fetch is complete
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any

from grohe.enum.grohe_enum import GroheGroupBy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

# Signature: (first day, last day, group_by) -> summed consumption of those full days.
FetchTotal = Callable[[date, date, GroheGroupBy], Awaitable[float]]


def _storage_key(domain: str, appliance_id: str) -> str:
    return f"{domain}_guard_water_consumption_{appliance_id}"


async def async_remove_water_consumption_store(
    hass: HomeAssistant, domain: str, appliance_id: str
) -> None:
    """Delete the stored consumption of an appliance (no-op if there is none)."""
    await Store(
        hass, STORAGE_VERSION, _storage_key(domain, appliance_id)
    ).async_remove()


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _first_of_month(day: date) -> date:
    return day.replace(day=1)


def _last_of_month(day: date) -> date:
    return _first_of_next_month(day) - timedelta(days=1)


def _first_of_next_month(day: date) -> date:
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1)


def _group_by_for(start: date, end: date) -> GroheGroupBy:
    """YEAR when the range is exactly whole calendar years, DAY otherwise."""
    if start == date(start.year, 1, 1) and end == date(end.year, 12, 31):
        return GroheGroupBy.YEAR
    return GroheGroupBy.DAY


class WaterConsumptionTracker:
    def __init__(
        self,
        hass: HomeAssistant,
        domain: str,
        appliance_id: str,
        fetch_total: FetchTotal,
    ) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, _storage_key(domain, appliance_id)
        )
        self._appliance_id = appliance_id
        self._fetch_total = fetch_total
        self._lock = asyncio.Lock()
        self._loaded = False
        self._base_total = 0.0
        self._base_until: date | None = None
        self._months: dict[str, float] = {}
        self._synced_until: date | None = None

    def total_until(self, day: date) -> float | None:
        """Total of all full days up to and including `day`, or None if not synced that far."""
        if self._synced_until is None or self._synced_until < day:
            return None
        return round(self._base_total + sum(self._months.values()), 2)

    async def async_sync(self, install_date: date) -> None:
        """Bring the stored total up to yesterday.

        Progress is saved after every successful step, so an exception (timeout, API
        error) only loses the step that failed and the next call continues from there.
        """
        async with self._lock:
            await self._async_load()
            today = dt_util.now().date()
            yesterday = today - timedelta(days=1)

            while self._synced_until is None:
                await self._async_fetch_next_history_chunk(install_date, today)

            if self._synced_until < yesterday:
                await self._async_sync_recent_months(yesterday)

    async def async_remove(self) -> None:
        await self._store.async_remove()

    async def _async_fetch_next_history_chunk(
        self, install_date: date, today: date
    ) -> None:
        history_end = _first_of_month(today) - timedelta(days=1)
        chunk_start = (
            install_date
            if self._base_until is None
            else self._base_until + timedelta(days=1)
        )

        if chunk_start > history_end:
            # Everything before the current month is covered (or the device was
            # installed this month): hand over to the monthly sync.
            self._base_until = history_end
            self._synced_until = history_end
            _LOGGER.info(
                "Historical water consumption of %s complete: %s l up to %s",
                self._appliance_id,
                round(self._base_total, 2),
                history_end,
            )
        else:
            chunk_end = min(date(chunk_start.year, 12, 31), history_end)
            _LOGGER.debug(
                "Fetching historical water consumption of %s from %s to %s",
                self._appliance_id,
                chunk_start,
                chunk_end,
            )
            self._base_total += await self._fetch(chunk_start, chunk_end)
            self._base_until = chunk_end

        await self._async_save()

    async def _async_sync_recent_months(self, yesterday: date) -> None:
        """Re-fetch every month from synced_until's month to yesterday's.

        Each month's value is overwritten, not added to, so a retry after a partial
        failure can't count anything twice. Starting at synced_until's month means the
        previous month is fetched again on the 1st and 2nd of a new month, which picks
        up values the device uploaded late.
        """
        assert self._synced_until is not None and self._base_until is not None
        fetched: dict[str, float] = {}
        month_start = _first_of_month(self._synced_until)
        while month_start <= yesterday:
            start = max(month_start, self._base_until + timedelta(days=1))
            end = min(_last_of_month(month_start), yesterday)
            if start <= end:
                fetched[_month_key(month_start)] = await self._fetch(start, end)
            month_start = _first_of_next_month(month_start)

        self._months.update(fetched)
        self._synced_until = yesterday
        self._fold_old_months(yesterday)
        await self._async_save()

    async def _fetch(self, start: date, end: date) -> float:
        return await self._fetch_total(start, end, _group_by_for(start, end))

    def _fold_old_months(self, yesterday: date) -> None:
        """Move months before the previous one into base_total; they won't be re-fetched."""
        keep_from = _month_key(_first_of_month(yesterday) - timedelta(days=1))
        for key in sorted(self._months):
            if key >= keep_from:
                break
            year, month = map(int, key.split("-"))
            self._base_total += self._months.pop(key)
            self._base_until = _last_of_month(date(year, month, 1))

    async def _async_load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        stored = await self._store.async_load()
        if not stored:
            return
        try:
            self._base_total = float(stored["base_total"])
            self._base_until = _parse_date(stored.get("base_until"))
            self._months = {k: float(v) for k, v in stored.get("months", {}).items()}
            self._synced_until = _parse_date(stored.get("synced_until"))
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.warning(
                "Stored water consumption of %s is invalid, fetching it again: %s",
                self._appliance_id,
                err,
            )
            self._base_total = 0.0
            self._base_until = None
            self._months = {}
            self._synced_until = None

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "base_total": self._base_total,
                "base_until": _format_date(self._base_until),
                "months": dict(self._months),
                "synced_until": _format_date(self._synced_until),
            }
        )


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _format_date(value: date | None) -> str | None:
    return value.isoformat() if value else None
