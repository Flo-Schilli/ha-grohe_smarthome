"""Service handlers for the Grohe SmartHome integration."""

import logging
from datetime import datetime, timedelta

import voluptuous as vol
from grohe import GroheClient, GroheGroupBy, GroheTapType, GroheTypes
from homeassistant.core import (
    HomeAssistant,
    HomeAssistantError,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import httpx_client
from voluptuous import All, Length

from custom_components.grohe_smarthome.const import DOMAIN
from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice

_LOGGER = logging.getLogger(__name__)


def find_device_by_device_id(
    hass: HomeAssistant, devices: list[GroheDevice], device_id: str
) -> GroheDevice | None:
    """Find Grohe device by device id."""

    registry = dr.async_get(hass)
    entry = registry.async_get(device_id)
    grohe_appliance_id = next(iter(entry.identifiers))[1]
    return next(
        (device for device in devices if device.appliance_id == grohe_appliance_id),
        None,
    )


def async_register_services(
    ha: HomeAssistant, api: GroheClient, devices: list[GroheDevice]
) -> None:
    """Register all Grohe SmartHome services."""

    async def handle_dashboard_export(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug("Export data for params: %s", call.data)
        try:
            return await api.get_dashboard()
        except Exception as e:
            raise HomeAssistantError(str(e)) from e

    async def handle_get_appliance_data(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug("Get data for params: %s", call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])
        group_by_str = (
            call.data.get("group_by").lower() if call.data.get("group_by") else None
        )
        date_from_in = (
            call.data.get("date_from") if call.data.get("date_from") else None
        )
        date_to_in = call.data.get("date_to") if call.data.get("date_to") else None

        if device:
            try:
                if group_by_str is None:
                    group_by = (
                        GroheGroupBy.DAY
                        if device.type == GroheTypes.GROHE_SENSE
                        else GroheGroupBy.HOUR
                    )
                else:
                    group_by = GroheGroupBy(group_by_str)

                if date_from_in is None:
                    date_from = datetime.now().astimezone() - timedelta(hours=1)
                else:
                    date_from = datetime.strptime(date_from_in, "%Y-%m-%d")

                if date_to_in is None:
                    date_to = datetime.now().astimezone()
                else:
                    date_to = datetime.strptime(date_to_in, "%Y-%m-%d")

                return await api.get_appliance_data(
                    device.location_id,
                    device.room_id,
                    device.appliance_id,
                    date_from,
                    date_to,
                    group_by,
                    False,
                )
            except Exception as e:
                raise HomeAssistantError(str(e)) from e
        else:
            raise HomeAssistantError("Device not found")

    async def handle_get_appliance_details(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug("Get details for params: %s", call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])

        if device:
            try:
                return await api.get_appliance_details(
                    device.location_id, device.room_id, device.appliance_id
                )
            except Exception as e:
                raise HomeAssistantError(str(e)) from e
        else:
            raise HomeAssistantError("Device not found")

    async def handle_get_appliance_command(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug("Get possible commands for params: %s", call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])

        if device:
            try:
                data = await api.get_appliance_command(
                    device.location_id, device.room_id, device.appliance_id
                )
                if data is None:
                    return {}
                else:
                    return data
            except Exception as e:
                raise HomeAssistantError(str(e)) from e
        else:
            raise HomeAssistantError("Device not found")

    async def handle_set_appliance_command(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug("Set commands for params: %s", call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])
        commands = call.data.get("commands")

        data_to_send = {"command": commands}
        if device:
            try:
                data = await api.set_appliance_command(
                    device.location_id,
                    device.room_id,
                    device.appliance_id,
                    device.type,
                    data_to_send,
                )
                if data is None:
                    return {}
                else:
                    return data
            except Exception as e:
                raise HomeAssistantError(str(e)) from e
        else:
            raise HomeAssistantError("Device not found")

    async def handle_tap_water(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug("Tap water for params: %s", call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])
        water_type = call.data.get("water_type")
        water_amount = call.data.get("amount")

        if device and (
            device.type == GroheTypes.GROHE_BLUE_HOME
            or device.type == GroheTypes.GROHE_BLUE_PROFESSIONAL
        ):
            try:
                mapped_water_type = GroheTapType[water_type.upper()]
                data_to_send = {
                    "command": {
                        "tap_type": mapped_water_type.value,
                        "tap_amount": water_amount,
                    }
                }
                data = await api.set_appliance_command(
                    device.location_id,
                    device.room_id,
                    device.appliance_id,
                    device.type,
                    data_to_send,
                )
                if data is None:
                    return {}
                else:
                    return data
            except Exception as e:
                raise HomeAssistantError(str(e)) from e
        else:
            raise HomeAssistantError(
                "Device does not exist or device is not a Grohe Blue Home or Grohe Blue Professional device"
            )

    async def handle_get_appliance_status(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug("Get status for params: %s", call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])

        if device:
            try:
                data = await api.get_appliance_status(
                    device.location_id, device.room_id, device.appliance_id
                )
                if data is None:
                    return {}
                elif isinstance(data, list) and len(data) > 0:
                    return {"status": data}
                else:
                    return data
            except Exception as e:
                raise HomeAssistantError(str(e)) from e
        else:
            raise HomeAssistantError("Device not found")

    async def handle_get_appliance_notifications(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug("Get notifications for params: %s", call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])

        if device:
            try:
                data = await api.get_appliance_notifications(
                    device.location_id, device.room_id, device.appliance_id
                )

                if data is None:
                    return {}
                elif isinstance(data, list) and len(data) > 0:
                    return {
                        "notifications": [dict(notification) for notification in data]
                    }
                else:
                    return {}
            except Exception as e:
                raise HomeAssistantError(str(e)) from e
        else:
            raise HomeAssistantError("Device not found")

    async def handle_get_appliance_pressure_measurement(
        call: ServiceCall,
    ) -> ServiceResponse:
        _LOGGER.debug("Get pressure measurement for params: %s", call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])

        if device:
            try:
                data = await api.get_appliance_pressure_measurement(
                    device.location_id, device.room_id, device.appliance_id
                )

                if data is None:
                    return {}
                elif isinstance(data, list) and len(data) > 0:
                    return {
                        "pressure_measurements": [
                            dict(measurement) for measurement in data
                        ]
                    }
                else:
                    return data
            except Exception as e:
                raise HomeAssistantError(str(e)) from e
        else:
            raise HomeAssistantError("Device not found")

    async def handle_get_profile_notifications(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug("Get profile notifications for params: %s", call.data)
        limit = call.data.get("limit")
        if limit is None:
            limit = 50

        try:
            data = await api.get_profile_notifications(limit)

            if data is None:
                return {}
            elif isinstance(data, list) and len(data) > 0:
                return {"notifications": [dict(notification) for notification in data]}
            else:
                return data
        except Exception as e:
            raise HomeAssistantError(str(e)) from e

    async def handle_set_snooze(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug("Set snooze for params: %s", call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])
        duration = call.data.get("duration")

        if device and (device.type == GroheTypes.GROHE_SENSE_GUARD):
            try:
                data = await api.set_snooze(
                    device.location_id, device.room_id, device.appliance_id, duration
                )
                if data is None:
                    return {}
                else:
                    return data
            except Exception as e:
                raise HomeAssistantError(str(e)) from e
        else:
            raise HomeAssistantError(
                "Device does not exist or device is not a Grohe Sense Guard device"
            )

    async def handle_disable_snooze(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug("Disable snooze for params: %s", call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])

        if device and (device.type == GroheTypes.GROHE_SENSE_GUARD):
            try:
                data = await api.disable_snooze(
                    device.location_id, device.room_id, device.appliance_id
                )
                if data is None:
                    return {}
                else:
                    return data
            except Exception as e:
                raise HomeAssistantError(str(e)) from e
        else:
            raise HomeAssistantError(
                "Device does not exist or device is not a Grohe Sense Guard device"
            )

    async def handle_login_and_get_tokens(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug(
            "Login and get tokens for username: %s", call.data.get("username")
        )
        username = call.data.get("username")
        password = call.data.get("password")
        if username is None or password is None:
            raise HomeAssistantError("Username and password are required")

        httpx_client_temp = httpx_client.get_async_client(ha)
        httpx_client_temp.cookies.clear()

        temp_api = GroheClient(username, password, httpx_client_temp)
        await temp_api.login()
        try:
            dashboard = await temp_api.get_dashboard()
        except Exception:
            dashboard = None

        tokens = temp_api.get_tokens()

        return {"tokens": tokens.to_dict(), "dashboard": dashboard}

    ha.services.async_register(
        DOMAIN,
        "get_dashboard",
        handle_dashboard_export,
        schema=None,
        supports_response=SupportsResponse.ONLY,
    )
    ha.services.async_register(
        DOMAIN,
        "get_tokens_from_username",
        handle_login_and_get_tokens,
        schema=vol.Schema(
            {
                vol.Required("username"): str,
                vol.Required("password"): str,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )

    ha.services.async_register(
        DOMAIN,
        "get_appliance_data",
        handle_get_appliance_data,
        schema=vol.Schema(
            {
                vol.Required("device_id"): All([str], Length(min=1)),
                vol.Optional("group_by"): str,
                vol.Optional("date_from"): str,
                vol.Optional("date_to"): str,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )

    ha.services.async_register(
        DOMAIN,
        "get_appliance_details",
        handle_get_appliance_details,
        schema=vol.Schema(
            {
                vol.Required("device_id"): All([str], Length(min=1)),
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )

    ha.services.async_register(
        DOMAIN,
        "get_appliance_command",
        handle_get_appliance_command,
        schema=vol.Schema(
            {
                vol.Required("device_id"): All([str], Length(min=1)),
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )

    ha.services.async_register(
        DOMAIN,
        "get_appliance_status",
        handle_get_appliance_status,
        schema=vol.Schema(
            {
                vol.Required("device_id"): All([str], Length(min=1)),
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )

    ha.services.async_register(
        DOMAIN,
        "get_appliance_notifications",
        handle_get_appliance_notifications,
        schema=vol.Schema(
            {
                vol.Required("device_id"): All([str], Length(min=1)),
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )

    ha.services.async_register(
        DOMAIN,
        "get_appliance_pressure_measurement",
        handle_get_appliance_pressure_measurement,
        schema=vol.Schema(
            {
                vol.Required("device_id"): All([str], Length(min=1)),
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )

    ha.services.async_register(
        DOMAIN,
        "set_appliance_command",
        handle_set_appliance_command,
        schema=vol.Schema(
            {
                vol.Required("device_id"): All([str], Length(min=1)),
                vol.Required("commands"): dict,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )

    ha.services.async_register(
        DOMAIN,
        "get_profile_notifications",
        handle_get_profile_notifications,
        schema=vol.Schema(
            {
                vol.Optional("limit"): int,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )

    ha.services.async_register(
        DOMAIN,
        "tap_water",
        handle_tap_water,
        schema=vol.Schema(
            {
                vol.Required("device_id"): All([str], Length(min=1)),
                vol.Required("water_type"): str,
                vol.Required("amount"): int,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )

    ha.services.async_register(
        DOMAIN,
        "set_snooze",
        handle_set_snooze,
        schema=vol.Schema(
            {
                vol.Optional("duration"): int,
                vol.Required("device_id"): All([str], Length(min=1)),
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )

    ha.services.async_register(
        DOMAIN,
        "disable_snooze",
        handle_disable_snooze,
        schema=vol.Schema(
            {
                vol.Required("device_id"): All([str], Length(min=1)),
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
