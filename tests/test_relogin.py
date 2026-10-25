"""Regression tests: a rejected access token must trigger one new login, not reauth."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from grohe import GroheUnauthorizedError
from homeassistant.exceptions import ConfigEntryAuthFailed

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
from custom_components.grohe_smarthome.entities.coordinator.relogin import (
    fetch_with_relogin,
)
from custom_components.grohe_smarthome.entities.coordinator.sense_coordinator import (
    SenseCoordinator,
)

DOMAIN = "grohe_smarthome"

DETAILS = {
    "installation_date": "2025-01-19T00:00:00+01:00",
    "status": [{"type": "connection", "value": 1}],
    # Blue Professional polls until this timestamp moves; without it every test
    # would sit out the full 10 s measurement timeout.
    "details": {"data_latest_measurement": {"timestamp": "2026-10-25T02:46:00+01:00"}},
}


def _make_device() -> SimpleNamespace:
    return SimpleNamespace(
        appliance_id="appliance-1",
        name="Test Device",
        type="grohe_sense",
        location_id="loc-1",
        room_id="room-1",
        stripped_sw_version=(1, 0),
    )


def _make_api() -> MagicMock:
    """An API whose token is stale until login() hands out a new one."""
    api = MagicMock()
    api.access_token = "stale"

    async def login():
        api.access_token = "fresh"

    api.login = AsyncMock(side_effect=login)
    return api


def _details_rejecting_stale_token(api: MagicMock) -> AsyncMock:
    async def get_appliance_details(*_args):
        if api.access_token == "stale":
            raise GroheUnauthorizedError("Unauthorized")
        return DETAILS

    return AsyncMock(side_effect=get_appliance_details)


async def test_relogin_retries_once_with_fresh_token():
    api = _make_api()
    fetch = AsyncMock(side_effect=[GroheUnauthorizedError("Unauthorized"), "data"])

    assert await fetch_with_relogin(api, fetch) == "data"
    api.login.assert_awaited_once()
    assert fetch.await_count == 2


async def test_relogin_propagates_when_login_is_rejected():
    api = _make_api()
    api.login = AsyncMock(
        side_effect=GroheUnauthorizedError("Invalid Grohe username or password")
    )
    fetch = AsyncMock(side_effect=GroheUnauthorizedError("Unauthorized"))

    with pytest.raises(GroheUnauthorizedError):
        await fetch_with_relogin(api, fetch)
    assert fetch.await_count == 1


async def test_relogin_propagates_when_fresh_token_is_rejected_too():
    api = _make_api()
    fetch = AsyncMock(side_effect=GroheUnauthorizedError("Unauthorized"))

    with pytest.raises(GroheUnauthorizedError):
        await fetch_with_relogin(api, fetch)
    api.login.assert_awaited_once()
    assert fetch.await_count == 2


async def test_relogin_logs_in_only_once_for_concurrent_failures():
    """All coordinators share one client and fail in the same polling round."""
    api = _make_api()
    fetch = _details_rejecting_stale_token(api)

    results = await asyncio.gather(*(fetch_with_relogin(api, fetch) for _ in range(6)))

    assert results == [DETAILS] * 6
    api.login.assert_awaited_once()


@pytest.mark.parametrize(
    "coordinator_cls",
    [SenseCoordinator, GuardCoordinator, BlueProfCoordinator, BlueHomeCoordinator],
)
async def test_update_data_recovers_from_stale_token(hass, coordinator_cls):
    api = _make_api()
    api.get_appliance_details = _details_rejecting_stale_token(api)
    api.get_appliance_pressure_measurement = AsyncMock(return_value=None)
    api.get_appliance_data = AsyncMock(return_value={"data": {"withdrawals": []}})
    api.set_appliance_command = AsyncMock(return_value=None)

    coordinator = coordinator_cls(hass, DOMAIN, _make_device(), api)

    data = await coordinator._async_update_data()

    assert data["details"] == DETAILS
    api.login.assert_awaited_once()


@pytest.mark.parametrize(
    "coordinator_cls",
    [SenseCoordinator, GuardCoordinator, BlueProfCoordinator, BlueHomeCoordinator],
)
async def test_initial_value_recovers_from_stale_token(hass, coordinator_cls):
    api = _make_api()
    api.get_appliance_details = _details_rejecting_stale_token(api)
    api.get_appliance_pressure_measurement = AsyncMock(return_value=None)
    api.get_appliance_data = AsyncMock(return_value={"data": {"withdrawals": []}})
    api.set_appliance_command = AsyncMock(return_value=None)

    coordinator = coordinator_cls(hass, DOMAIN, _make_device(), api)

    data = await coordinator.get_initial_value()

    assert data["details"] == DETAILS
    api.login.assert_awaited_once()


async def test_profile_coordinator_recovers_from_stale_token(hass):
    api = _make_api()

    async def notifications(_limit):
        if api.access_token == "stale":
            raise GroheUnauthorizedError("Unauthorized")
        return []

    api.get_profile_notifications = AsyncMock(side_effect=notifications)

    coordinator = ProfileCoordinator(hass, DOMAIN, api)

    await coordinator._async_update_data()

    api.login.assert_awaited_once()


async def test_update_data_still_raises_auth_failed_for_bad_credentials(hass):
    api = _make_api()
    api.login = AsyncMock(
        side_effect=GroheUnauthorizedError("Invalid Grohe username or password")
    )
    api.get_appliance_details = AsyncMock(
        side_effect=GroheUnauthorizedError("Unauthorized")
    )

    coordinator = SenseCoordinator(hass, DOMAIN, _make_device(), api)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
