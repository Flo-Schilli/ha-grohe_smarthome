"""Tests for service registration and the runtime-data lookup used by services."""

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.grohe_smarthome.const import DOMAIN
from custom_components.grohe_smarthome.services import (
    _get_runtime_data,
    async_register_services,
)

EXPECTED_SERVICES = [
    "get_dashboard",
    "get_tokens_from_username",
    "get_appliance_data",
    "get_appliance_details",
    "get_appliance_command",
    "get_appliance_status",
    "get_appliance_notifications",
    "get_appliance_pressure_measurement",
    "set_appliance_command",
    "get_profile_notifications",
    "tap_water",
    "set_snooze",
    "disable_snooze",
]


async def test_async_register_services_registers_all_services(hass):
    async_register_services(hass)

    for service in EXPECTED_SERVICES:
        assert hass.services.has_service(DOMAIN, service)


def test_get_runtime_data_raises_when_no_entry_configured(hass):
    with pytest.raises(
        HomeAssistantError, match="No Grohe SmartHome integration configured"
    ):
        _get_runtime_data(hass)


async def test_service_call_without_configured_entry_raises(hass):
    async_register_services(hass)

    with pytest.raises(
        HomeAssistantError, match="No Grohe SmartHome integration configured"
    ):
        await hass.services.async_call(
            DOMAIN, "get_dashboard", {}, blocking=True, return_response=True
        )
