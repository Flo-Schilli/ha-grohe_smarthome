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
