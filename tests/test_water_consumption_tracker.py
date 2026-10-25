"""Tests for the persisted, incrementally updated Sense Guard water consumption."""

from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
from grohe.enum.grohe_enum import GroheGroupBy
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grohe_smarthome import async_remove_entry
from custom_components.grohe_smarthome.entities.coordinator.water_consumption_tracker import (
    WaterConsumptionTracker,
)

DOMAIN = "grohe_smarthome"
APPLIANCE_ID = "appliance-1"
STORAGE_KEY = f"{DOMAIN}_guard_water_consumption_{APPLIANCE_ID}"
INSTALL_DATE = date(2024, 3, 15)


def _one_liter_per_day():
    """Fake aggregated-data fetch: 1 l on every day from INSTALL_DATE up to today.

    Like the real endpoint, it returns whole buckets of the requested grouping: the
    range is widened to the start of the first and the end of the last year/month, and
    the last bucket includes today. Totals are then simply day counts.
    """

    async def fetch(date_from: date, date_to: date, group_by: GroheGroupBy) -> float:
        if group_by == GroheGroupBy.YEAR:
            date_from = date(date_from.year, 1, 1)
            date_to = date(date_to.year, 12, 31)
        elif group_by == GroheGroupBy.MONTH:
            date_from = date_from.replace(day=1)
            date_to = (date_to.replace(day=28) + timedelta(days=4)).replace(
                day=1
            ) - timedelta(days=1)
        first = max(date_from, INSTALL_DATE)
        last = min(date_to, dt_util.now().date())
        return max(float((last - first).days + 1), 0.0)

    return AsyncMock(side_effect=fetch)


def _days(date_from: date, date_to: date) -> float:
    return float((date_to - date_from).days + 1)


def _calls(fetch: AsyncMock) -> list[tuple]:
    return [c.args for c in fetch.call_args_list]


def _tracker(hass, fetch: AsyncMock) -> WaterConsumptionTracker:
    return WaterConsumptionTracker(hass, DOMAIN, APPLIANCE_ID, fetch)


@pytest.fixture
def today(freezer):
    """Freeze 'now' at noon of a given local day."""

    def move_to(day: date) -> date:
        freezer.move_to(f"{day.isoformat()} 12:00:00")
        return day

    return move_to


async def test_history_is_fetched_once_in_year_chunks(hass, hass_storage, today):
    today(date(2026, 10, 25))
    fetch = _one_liter_per_day()
    tracker = _tracker(hass, fetch)

    await tracker.async_sync(INSTALL_DATE)

    assert _calls(fetch) == [
        (date(2024, 3, 15), date(2024, 12, 31), GroheGroupBy.DAY),
        (date(2025, 1, 1), date(2025, 12, 31), GroheGroupBy.YEAR),
        (date(2026, 1, 1), date(2026, 9, 30), GroheGroupBy.DAY),
        (date(2026, 10, 1), date(2026, 10, 24), GroheGroupBy.DAY),
    ]
    assert tracker.total_until(date(2026, 10, 24)) == _days(
        INSTALL_DATE, date(2026, 10, 24)
    )
    assert hass_storage[STORAGE_KEY]["data"]["synced_until"] == "2026-10-24"

    fetch.reset_mock()
    await tracker.async_sync(INSTALL_DATE)
    assert fetch.call_count == 0, "a second sync on the same day must not fetch again"


async def test_history_resumes_after_a_failed_chunk(hass, hass_storage, today):
    today(date(2026, 10, 25))
    fetch = _one_liter_per_day()
    real_fetch = fetch.side_effect

    async def fail_2025_once(date_from, date_to, group_by):
        if date_from == date(2025, 1, 1) and not fail_2025_once.failed:
            fail_2025_once.failed = True
            raise TimeoutError
        return await real_fetch(date_from, date_to, group_by)

    fail_2025_once.failed = False
    fetch.side_effect = fail_2025_once
    tracker = _tracker(hass, fetch)

    with pytest.raises(TimeoutError):
        await tracker.async_sync(INSTALL_DATE)
    assert tracker.total_until(date(2026, 10, 24)) is None
    assert hass_storage[STORAGE_KEY]["data"]["base_until"] == "2024-12-31"

    fetch.reset_mock()
    await tracker.async_sync(INSTALL_DATE)

    assert _calls(fetch)[0][0] == date(2025, 1, 1), "2024 must not be fetched again"
    assert tracker.total_until(date(2026, 10, 24)) == _days(
        INSTALL_DATE, date(2026, 10, 24)
    )


async def test_restart_uses_stored_total_without_fetching(hass, hass_storage, today):
    today(date(2026, 10, 25))
    await _tracker(hass, _one_liter_per_day()).async_sync(INSTALL_DATE)

    fetch = _one_liter_per_day()
    restarted = _tracker(hass, fetch)
    await restarted.async_sync(INSTALL_DATE)

    assert fetch.call_count == 0
    assert restarted.total_until(date(2026, 10, 24)) == _days(
        INSTALL_DATE, date(2026, 10, 24)
    )


async def test_daily_sync_only_refetches_the_current_month(hass, hass_storage, today):
    today(date(2026, 10, 25))
    fetch = _one_liter_per_day()
    tracker = _tracker(hass, fetch)
    await tracker.async_sync(INSTALL_DATE)

    today(date(2026, 10, 26))
    fetch.reset_mock()
    await tracker.async_sync(INSTALL_DATE)

    assert _calls(fetch) == [(date(2026, 10, 1), date(2026, 10, 25), GroheGroupBy.DAY)]
    assert tracker.total_until(date(2026, 10, 25)) == _days(
        INSTALL_DATE, date(2026, 10, 25)
    ), "the month is overwritten, not added on top"


async def test_month_rollover_finalizes_the_previous_month(hass, hass_storage, today):
    today(date(2026, 10, 25))
    fetch = _one_liter_per_day()
    tracker = _tracker(hass, fetch)
    await tracker.async_sync(INSTALL_DATE)

    expected_calls = {
        date(2026, 11, 1): [(date(2026, 10, 1), date(2026, 10, 31))],
        date(2026, 11, 2): [
            (date(2026, 10, 1), date(2026, 10, 31)),
            (date(2026, 11, 1), date(2026, 11, 1)),
        ],
        date(2026, 11, 3): [(date(2026, 11, 1), date(2026, 11, 2))],
    }
    for day, calls in expected_calls.items():
        today(day)
        fetch.reset_mock()
        await tracker.async_sync(INSTALL_DATE)

        assert [c[:2] for c in _calls(fetch)] == calls, day
        yesterday = day - timedelta(days=1)
        assert tracker.total_until(yesterday) == _days(INSTALL_DATE, yesterday)


async def test_long_gap_folds_old_months_into_the_base(hass, hass_storage, today):
    today(date(2026, 10, 25))
    fetch = _one_liter_per_day()
    tracker = _tracker(hass, fetch)
    await tracker.async_sync(INSTALL_DATE)

    today(date(2027, 1, 10))
    await tracker.async_sync(INSTALL_DATE)

    stored = hass_storage[STORAGE_KEY]["data"]
    assert sorted(stored["months"]) == ["2026-12", "2027-01"]
    assert stored["base_until"] == "2026-11-30"
    assert tracker.total_until(date(2027, 1, 9)) == _days(
        INSTALL_DATE, date(2027, 1, 9)
    )


async def test_failed_daily_sync_keeps_state_and_retries(hass, hass_storage, today):
    today(date(2026, 10, 25))
    fetch = _one_liter_per_day()
    tracker = _tracker(hass, fetch)
    await tracker.async_sync(INSTALL_DATE)
    real_fetch = fetch.side_effect

    today(date(2026, 10, 26))
    fetch.side_effect = TimeoutError
    with pytest.raises(TimeoutError):
        await tracker.async_sync(INSTALL_DATE)

    assert tracker.total_until(date(2026, 10, 25)) is None
    assert hass_storage[STORAGE_KEY]["data"]["synced_until"] == "2026-10-24"

    fetch.side_effect = real_fetch
    await tracker.async_sync(INSTALL_DATE)
    assert tracker.total_until(date(2026, 10, 25)) == _days(
        INSTALL_DATE, date(2026, 10, 25)
    )


async def test_device_installed_this_month_needs_no_history(hass, hass_storage, today):
    today(date(2026, 10, 25))
    fetch = _one_liter_per_day()
    tracker = _tracker(hass, fetch)

    await tracker.async_sync(date(2026, 10, 20))

    assert _calls(fetch) == [(date(2026, 10, 1), date(2026, 10, 24), GroheGroupBy.DAY)]


async def test_invalid_stored_data_is_fetched_again(hass, hass_storage, today):
    today(date(2026, 10, 25))
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {"base_total": "garbage"},
    }
    fetch = _one_liter_per_day()
    tracker = _tracker(hass, fetch)

    await tracker.async_sync(INSTALL_DATE)

    assert tracker.total_until(date(2026, 10, 24)) == _days(
        INSTALL_DATE, date(2026, 10, 24)
    )


async def test_remove_deletes_the_store(hass, hass_storage, today):
    today(date(2026, 10, 25))
    tracker = _tracker(hass, _one_liter_per_day())
    await tracker.async_sync(INSTALL_DATE)
    assert STORAGE_KEY in hass_storage

    await tracker.async_remove()

    assert STORAGE_KEY not in hass_storage


async def test_removing_the_config_entry_deletes_the_stores(hass, hass_storage, today):
    today(date(2026, 10, 25))
    await _tracker(hass, _one_liter_per_day()).async_sync(INSTALL_DATE)
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, APPLIANCE_ID)}
    )

    await async_remove_entry(hass, entry)

    assert STORAGE_KEY not in hass_storage
