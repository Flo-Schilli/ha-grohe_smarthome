"""Regression tests: coordinators must raise UpdateFailed instead of swallowing errors."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
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
