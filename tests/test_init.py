"""Tests for async_setup_entry error handling (test-before-setup)."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from grohe import GroheNetworkError, GroheUnauthorizedError
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grohe_smarthome import async_setup_entry
from custom_components.grohe_smarthome.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)

GROHE_CLIENT_PATH = "custom_components.grohe_smarthome.GroheClient"


def _make_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="GroheSmarthome",
        data={CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"},
    )


async def test_setup_entry_raises_auth_failed_on_invalid_credentials(hass):
    entry = _make_entry()
    entry.add_to_hass(hass)

    client = AsyncMock()
    client.login.side_effect = GroheUnauthorizedError(
        "Invalid Grohe username or password"
    )

    with (
        patch(GROHE_CLIENT_PATH, return_value=client),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await async_setup_entry(hass, entry)


async def test_setup_entry_raises_not_ready_on_network_error(hass):
    entry = _make_entry()
    entry.add_to_hass(hass)

    client = AsyncMock()
    client.login.side_effect = httpx.ConnectError("boom")

    with (
        patch(GROHE_CLIENT_PATH, return_value=client),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry)


async def test_setup_entry_raises_not_ready_on_grohe_network_error_fetching_devices(
    hass,
):
    """Regression test: a GroheNetworkError (e.g. a timed-out dashboard call) while
    fetching devices must surface as ConfigEntryNotReady, not an unhandled crash."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    client = AsyncMock()
    client.login = AsyncMock(return_value=None)
    client.get_dashboard.side_effect = GroheNetworkError(
        "GET https://.../dashboard failed: timeout"
    )

    with (
        patch(GROHE_CLIENT_PATH, return_value=client),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry)


async def test_setup_entry_raises_auth_failed_when_credentials_missing(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="GroheSmarthome", data={})
    entry.add_to_hass(hass)

    with pytest.raises(ConfigEntryAuthFailed):
        await async_setup_entry(hass, entry)


async def test_forward_entry_setups_not_called_when_first_refresh_fails(hass):
    """Platforms must not be forwarded before the coordinators have data.

    Regression test for a production outage: the initial Grohe request was
    denied, the coordinator raised ConfigEntryNotReady from inside an
    already-forwarded platform, and Home Assistant's retry then hit
    "Config entry ... has already been setup!" for every platform. The entry
    stayed nominally loaded with no coordinator running for 42 hours.

    Forwarding after the refresh keeps the failure inside async_setup_entry,
    where Home Assistant can retry it cleanly.
    """
    entry = _make_entry()
    entry.add_to_hass(hass)

    client = AsyncMock()
    client.login = AsyncMock(return_value=None)
    client.user_id = "user-1"

    forward = AsyncMock()

    with (
        patch(GROHE_CLIENT_PATH, return_value=client),
        patch(
            "custom_components.grohe_smarthome.GroheDevice.get_devices",
            AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.grohe_smarthome.ProfileCoordinator."
            "async_config_entry_first_refresh",
            AsyncMock(side_effect=ConfigEntryNotReady("Grohe denied the request")),
        ),
        patch.object(hass.config_entries, "async_forward_entry_setups", forward),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry)

    forward.assert_not_called()


async def test_forward_entry_setups_called_after_successful_refresh(hass):
    """The happy path must still register the platforms, and only afterwards."""
    entry = _make_entry()
    entry.add_to_hass(hass)

    client = AsyncMock()
    client.login = AsyncMock(return_value=None)
    client.user_id = "user-1"

    calls: list[str] = []
    forward = AsyncMock(side_effect=lambda *a, **k: calls.append("forward"))
    refresh = AsyncMock(side_effect=lambda *a, **k: calls.append("refresh"))

    with (
        patch(GROHE_CLIENT_PATH, return_value=client),
        patch(
            "custom_components.grohe_smarthome.GroheDevice.get_devices",
            AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.grohe_smarthome.ProfileCoordinator."
            "async_config_entry_first_refresh",
            refresh,
        ),
        patch.object(hass.config_entries, "async_forward_entry_setups", forward),
    ):
        await async_setup_entry(hass, entry)

    assert calls == ["refresh", "forward"], (
        f"expected refresh before forward, got {calls}"
    )
