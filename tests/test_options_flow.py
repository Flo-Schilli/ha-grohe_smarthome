"""Tests for the Grohe SmartHome options flow."""

import pytest
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grohe_smarthome.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)


def _make_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="GroheSmarthome",
        data={CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"},
    )


async def test_options_flow_shows_form_with_defaults(hass):
    entry = _make_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_saves_valid_options(hass):
    entry = _make_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "polling": 120,
            "logging_options": {"log_response_data": True},
            "network_options": {"request_timeout": 15, "connect_timeout": 7},
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["polling"] == 120
    assert result["data"]["logging_options"]["log_response_data"] is True
    assert result["data"]["network_options"]["request_timeout"] == 15


async def test_options_flow_rejects_polling_below_minimum(hass):
    entry = _make_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "polling": 5,
                "logging_options": {"log_response_data": False},
                "network_options": {"request_timeout": 10, "connect_timeout": 5},
            },
        )
