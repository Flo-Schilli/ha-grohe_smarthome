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
