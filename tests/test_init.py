"""Tests for async_setup_entry error handling (test-before-setup)."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
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
    client.login.side_effect = Exception(
        "Invalid username/password or unexpected response from Grohe service"
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


async def test_setup_entry_raises_auth_failed_when_credentials_missing(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="GroheSmarthome", data={})
    entry.add_to_hass(hass)

    with pytest.raises(ConfigEntryAuthFailed):
        await async_setup_entry(hass, entry)
