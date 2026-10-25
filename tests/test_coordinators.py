"""Regression tests: coordinators must raise UpdateFailed instead of swallowing errors."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from grohe import GroheForbiddenError
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.grohe_smarthome.entities.coordinator.blue_home_coordinator import (
    BlueHomeCoordinator,
)
from custom_components.grohe_smarthome.entities.coordinator.blue_prof_coordinator import (
    BlueProfCoordinator,
)
from custom_components.grohe_smarthome.entities.coordinator.guard_coordinator import (
    GuardCoordinator,
)
from custom_components.grohe_smarthome.entities.coordinator.profile_coordinator import (
    ProfileCoordinator,
)
from custom_components.grohe_smarthome.entities.coordinator.sense_coordinator import (
    SenseCoordinator,
)

DOMAIN = "grohe_smarthome"


def _make_device() -> SimpleNamespace:
    return SimpleNamespace(
        appliance_id="appliance-1",
        name="Test Device",
        type="grohe_sense",
        location_id="loc-1",
        room_id="room-1",
        stripped_sw_version=(1, 0),
    )


async def test_sense_coordinator_raises_update_failed_on_api_error(hass):
    api = MagicMock()
    api.get_appliance_details = AsyncMock(side_effect=RuntimeError("API is down"))

    coordinator = SenseCoordinator(hass, DOMAIN, _make_device(), api)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_guard_coordinator_raises_update_failed_on_api_error(hass):
    api = MagicMock()
    api.get_appliance_details = AsyncMock(side_effect=RuntimeError("API is down"))

    coordinator = GuardCoordinator(hass, DOMAIN, _make_device(), api)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_blue_prof_coordinator_raises_update_failed_on_api_error(hass):
    api = MagicMock()
    api.set_appliance_command = AsyncMock(side_effect=RuntimeError("API is down"))

    coordinator = BlueProfCoordinator(hass, DOMAIN, _make_device(), api)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_profile_coordinator_raises_update_failed_on_api_error(hass):
    api = MagicMock()
    api.get_profile_notifications = AsyncMock(side_effect=RuntimeError("API is down"))

    coordinator = ProfileCoordinator(hass, DOMAIN, api)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_blue_home_coordinator_propagates_error_on_first_fetch(hass):
    """BlueHomeCoordinator doesn't wrap in try/except; DataUpdateCoordinator itself
    turns the raw exception into UpdateFailed once wired up via async_refresh, but
    here we assert the underlying fetch simply raises rather than being swallowed."""
    api = MagicMock()
    api.get_appliance_details = AsyncMock(side_effect=RuntimeError("API is down"))

    coordinator = BlueHomeCoordinator(hass, DOMAIN, _make_device(), api)

    with pytest.raises(RuntimeError):
        await coordinator._async_update_data()


# get_initial_value() is called directly from each platform's async_setup_entry
# (via EntityHelper), *before* the coordinator's own async_config_entry_first_refresh()
# runs - so it bypasses all of the retry/backoff machinery DataUpdateCoordinator
# normally provides. A 429 (GroheRateLimitError, a GroheForbiddenError subclass) or any
# other transient failure here used to propagate raw out of async_setup_entry, crashing
# the whole platform instead of politely asking Home Assistant to retry later.


async def test_sense_coordinator_initial_value_raises_config_entry_not_ready(hass):
    api = MagicMock()
    api.get_appliance_details = AsyncMock(
        side_effect=GroheForbiddenError("429 Too Many Requests")
    )

    coordinator = SenseCoordinator(hass, DOMAIN, _make_device(), api)

    with pytest.raises(ConfigEntryNotReady):
        await coordinator.get_initial_value()


async def test_guard_coordinator_initial_value_raises_config_entry_not_ready(hass):
    api = MagicMock()
    api.get_appliance_details = AsyncMock(
        side_effect=GroheForbiddenError("429 Too Many Requests")
    )

    coordinator = GuardCoordinator(hass, DOMAIN, _make_device(), api)

    with pytest.raises(ConfigEntryNotReady):
        await coordinator.get_initial_value()


async def test_blue_prof_coordinator_initial_value_raises_config_entry_not_ready(hass):
    api = MagicMock()
    api.set_appliance_command = AsyncMock(
        side_effect=GroheForbiddenError("429 Too Many Requests")
    )

    coordinator = BlueProfCoordinator(hass, DOMAIN, _make_device(), api)

    with pytest.raises(ConfigEntryNotReady):
        await coordinator.get_initial_value()


async def test_profile_coordinator_initial_value_raises_config_entry_not_ready(hass):
    api = MagicMock()
    api.get_profile_notifications = AsyncMock(
        side_effect=GroheForbiddenError("429 Too Many Requests")
    )

    coordinator = ProfileCoordinator(hass, DOMAIN, api)

    with pytest.raises(ConfigEntryNotReady):
        await coordinator.get_initial_value()


async def test_blue_home_coordinator_initial_value_raises_config_entry_not_ready(hass):
    api = MagicMock()
    api.get_appliance_details = AsyncMock(
        side_effect=GroheForbiddenError("429 Too Many Requests")
    )

    coordinator = BlueHomeCoordinator(hass, DOMAIN, _make_device(), api)

    with pytest.raises(ConfigEntryNotReady):
        await coordinator.get_initial_value()


async def test_sense_coordinator_initial_value_survives_unexpected_error(hass):
    """A non-Grohe error (e.g. the 'NoneType' has no attribute 'get' crash actually
    observed in production after a 429) must also turn into ConfigEntryNotReady, not
    propagate raw and crash platform setup."""
    api = MagicMock()
    api.get_appliance_details = AsyncMock(
        side_effect=AttributeError("'NoneType' object has no attribute 'get'")
    )

    coordinator = SenseCoordinator(hass, DOMAIN, _make_device(), api)

    with pytest.raises(ConfigEntryNotReady):
        await coordinator.get_initial_value()


# _async_update_data() drives every *regular* refresh cycle after setup (unlike
# get_initial_value(), which only runs once during platform setup). It already had
# GroheForbiddenError handling before this fix, but that behavior wasn't under test -
# these lock in the two cases explicitly: a 429 with no cached data yet must still
# raise UpdateFailed (so HA marks entities unavailable rather than crashing), and a
# 429 with cached data must keep serving the last known data instead of failing.


async def test_sense_coordinator_update_data_raises_update_failed_on_429_without_cache(
    hass,
):
    api = MagicMock()
    api.get_appliance_details = AsyncMock(
        side_effect=GroheForbiddenError("429 Too Many Requests")
    )

    coordinator = SenseCoordinator(hass, DOMAIN, _make_device(), api)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_sense_coordinator_update_data_keeps_last_known_data_on_429(hass):
    api = MagicMock()
    api.get_appliance_details = AsyncMock(
        side_effect=GroheForbiddenError("429 Too Many Requests")
    )

    coordinator = SenseCoordinator(hass, DOMAIN, _make_device(), api)
    coordinator.data = {"details": "cached-details", "status": "cached-status"}

    result = await coordinator._async_update_data()

    assert result == {"details": "cached-details", "status": "cached-status"}


async def test_guard_coordinator_update_data_raises_update_failed_on_429_without_cache(
    hass,
):
    api = MagicMock()
    api.get_appliance_details = AsyncMock(
        side_effect=GroheForbiddenError("429 Too Many Requests")
    )

    coordinator = GuardCoordinator(hass, DOMAIN, _make_device(), api)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_guard_coordinator_update_data_keeps_last_known_data_on_429(hass):
    api = MagicMock()
    api.get_appliance_details = AsyncMock(
        side_effect=GroheForbiddenError("429 Too Many Requests")
    )

    coordinator = GuardCoordinator(hass, DOMAIN, _make_device(), api)
    coordinator.data = {"details": "cached-details"}

    result = await coordinator._async_update_data()

    assert result == {"details": "cached-details"}


async def test_blue_prof_coordinator_update_data_raises_update_failed_on_429_without_cache(
    hass,
):
    api = MagicMock()
    api.set_appliance_command = AsyncMock(
        side_effect=GroheForbiddenError("429 Too Many Requests")
    )

    coordinator = BlueProfCoordinator(hass, DOMAIN, _make_device(), api)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_blue_prof_coordinator_update_data_keeps_last_known_data_on_429(hass):
    api = MagicMock()
    api.set_appliance_command = AsyncMock(
        side_effect=GroheForbiddenError("429 Too Many Requests")
    )

    coordinator = BlueProfCoordinator(hass, DOMAIN, _make_device(), api)
    coordinator.data = {"details": "cached-details"}

    result = await coordinator._async_update_data()

    assert result == {"details": "cached-details"}


async def test_profile_coordinator_update_data_raises_update_failed_on_429_without_cache(
    hass,
):
    api = MagicMock()
    api.get_profile_notifications = AsyncMock(
        side_effect=GroheForbiddenError("429 Too Many Requests")
    )

    coordinator = ProfileCoordinator(hass, DOMAIN, api)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_profile_coordinator_update_data_keeps_last_known_data_on_429(hass):
    api = MagicMock()
    api.get_profile_notifications = AsyncMock(
        side_effect=GroheForbiddenError("429 Too Many Requests")
    )

    coordinator = ProfileCoordinator(hass, DOMAIN, api)
    coordinator.data = {"notifications": "cached-notifications"}

    result = await coordinator._async_update_data()

    assert result == {"notifications": "cached-notifications"}


async def test_blue_home_coordinator_update_data_raises_update_failed_on_429_without_cache(
    hass,
):
    """BlueHomeCoordinator only hits the API in _async_update_data when there's no
    cached data yet (once data exists, it's served from cache and refreshed by a
    separate background task instead) - so there's no "keep last known data" branch
    to test here, only the no-cache-yet case."""
    api = MagicMock()
    api.get_appliance_details = AsyncMock(
        side_effect=GroheForbiddenError("429 Too Many Requests")
    )

    coordinator = BlueHomeCoordinator(hass, DOMAIN, _make_device(), api)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_guard_total_value_does_not_fabricate_zero_on_error(hass):
    """A failed aggregate fetch must not be reported as 0.0 water consumption."""
    from datetime import date

    from grohe.enum.grohe_enum import GroheGroupBy

    api = MagicMock()
    api.get_appliance_data = AsyncMock(side_effect=TimeoutError())

    coordinator = GuardCoordinator(hass, DOMAIN, _make_device(), api)

    with pytest.raises(TimeoutError):
        await coordinator._get_total_value(date.today(), date.today(), GroheGroupBy.DAY)


async def test_guard_total_value_does_not_turn_a_missing_response_into_zero(hass):
    """The grohe library returns None for e.g. a 504 instead of raising."""
    from datetime import date

    from grohe.enum.grohe_enum import GroheGroupBy

    api = MagicMock()
    api.get_appliance_data = AsyncMock(return_value=None)

    coordinator = GuardCoordinator(hass, DOMAIN, _make_device(), api)

    with pytest.raises(UpdateFailed):
        await coordinator._get_total_value(date.today(), date.today(), GroheGroupBy.DAY)


def _guard_api_with_failing_consumption(error: Exception) -> MagicMock:
    api = MagicMock()
    api.get_appliance_details = AsyncMock(
        return_value={
            "installation_date": "2020-01-01T00:00:00+00:00",
            "status": [],
            "command": {"valve_open": True},
        }
    )
    api.get_appliance_data = AsyncMock(side_effect=error)
    return api


async def test_guard_consumption_failure_keeps_last_total_and_device_data(
    hass, hass_storage
):
    """A failing consumption fetch must neither reset the total nor fail the update.

    The valve and the other entities read the same coordinator data, so failing the
    whole update for a slow statistics endpoint would make them unavailable too.
    """
    api = _guard_api_with_failing_consumption(TimeoutError())
    coordinator = GuardCoordinator(hass, DOMAIN, _make_device(), api)
    coordinator.data = {"total_water_consumption": 133984.0}

    data = await coordinator._async_update_data()

    assert data["total_water_consumption"] == 133984.0
    assert data["details"]["command"] == {"valve_open": True}


async def test_guard_consumption_failure_without_history_reports_no_total(
    hass, hass_storage
):
    api = _guard_api_with_failing_consumption(TimeoutError())
    coordinator = GuardCoordinator(hass, DOMAIN, _make_device(), api)

    data = await coordinator._async_update_data()

    assert data["total_water_consumption"] is None
    assert data["details"]["command"] == {"valve_open": True}


async def test_guard_consumption_rate_limit_keeps_last_known_data(hass, hass_storage):
    """429s in the consumption part still go through the 'keep last data' path."""
    api = _guard_api_with_failing_consumption(GroheForbiddenError("explicit deny"))
    coordinator = GuardCoordinator(hass, DOMAIN, _make_device(), api)
    last_data = {"details": {}, "total_water_consumption": 1.0}
    coordinator.data = last_data

    assert await coordinator._async_update_data() is last_data


async def test_guard_reports_stored_total_plus_today(hass, hass_storage):
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    yesterday = dt_util.now().date() - timedelta(days=1)
    key = f"{DOMAIN}_guard_water_consumption_appliance-1"
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {
            "base_total": 1000.0,
            "base_until": (yesterday.replace(day=1) - timedelta(days=1)).isoformat(),
            "months": {f"{yesterday:%Y-%m}": 25.5},
            "synced_until": yesterday.isoformat(),
        },
    }
    api = _guard_api_with_failing_consumption(None)
    api.get_appliance_data = AsyncMock(
        return_value={"data": {"withdrawals": [{"waterconsumption": 4.5}]}}
    )
    coordinator = GuardCoordinator(hass, DOMAIN, _make_device(), api)

    data = await coordinator._async_update_data()

    assert data["total_water_consumption"] == 1030.0
    assert api.get_appliance_data.call_count == 1, "only today's value is fetched"


async def test_guard_total_value_returns_zero_when_api_reports_no_withdrawals(hass):
    """An empty result is a real zero and must still be reported as such."""
    from datetime import datetime

    from grohe.enum.grohe_enum import GroheGroupBy

    api = MagicMock()
    api.get_appliance_data = AsyncMock(return_value={"data": {"withdrawals": []}})

    coordinator = GuardCoordinator(hass, DOMAIN, _make_device(), api)

    now = datetime.now().astimezone().date()
    assert await coordinator._get_total_value(now, now, GroheGroupBy.DAY) == 0
