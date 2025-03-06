import logging
import os.path
from datetime import datetime, timedelta
from typing import List, Dict

import httpx
from homeassistant.helpers.storage import Store
import voluptuous
from voluptuous import All, Length

from grohe import GroheClient, GroheGroupBy, GroheTypes, GroheTapType

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, HomeAssistantError
from homeassistant.helpers import device_registry, httpx_client
from custom_components.grohe_smarthome.const import DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_PLATFORM
from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice
from custom_components.grohe_smarthome.entities.config_loader import ConfigLoader
from custom_components.grohe_smarthome.entities.coordinator.blue_home_coordinator import BlueHomeCoordinator
from custom_components.grohe_smarthome.entities.coordinator.blue_prof_coordinator import BlueProfCoordinator
from custom_components.grohe_smarthome.entities.coordinator.guard_coordinator import GuardCoordinator
from custom_components.grohe_smarthome.entities.coordinator.profile_coordinator import ProfileCoordinator
from custom_components.grohe_smarthome.entities.coordinator.sense_coordinator import SenseCoordinator
from custom_components.grohe_smarthome.entities.interface.coordinator_interface import CoordinatorInterface


_LOGGER = logging.getLogger(__name__)

def find_device_by_device_id(
    hass: HomeAssistant, devices: List[GroheDevice], device_id: str
) -> GroheDevice:
    registry = device_registry.async_get(hass)
    entry = registry.async_get(device_id)
    grohe_appliance_id = next(iter(entry.identifiers))[1]
    return next(
        (device for device in devices if device.appliance_id == grohe_appliance_id),
        None,
    )


async def async_unload_entry(ha: HomeAssistant, entry: ConfigEntry):
    _LOGGER.debug("Unloading Grohe Entry")
    unload_ok = await ha.config_entries.async_unload_platforms(entry, CONF_PLATFORM)

    if unload_ok:
        ha.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_setup_entry(ha: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Loading Grohe Entry")

    config_loader = ConfigLoader(os.path.join(os.path.dirname(__file__), 'config'))

    notifications = await ha.async_add_executor_job(config_loader.load_notifications)
    config = await ha.async_add_executor_job(config_loader.load_config)

    # Login to Grohe backend
    httpx_client_ha = httpx_client.get_async_client(ha)
    httpx_client_ha.cookies.clear()
    request_timeout = entry.options.get('request_timeout', 10)
    connect_timeout = entry.options.get('connect_timeout', 5)
    log_response_data = entry.options.get('log_response_data', False)

    httpx_client_ha.timeout = httpx.Timeout(request_timeout, connect=connect_timeout)
    
    api = GroheClient(entry.data.get('username'), entry.data.get('password'), httpx_client_ha)
    await api.login()

    # Get all devices available
    devices: List[GroheDevice] = await GroheDevice.get_devices(api)

    polling = entry.options.get('polling', 300)
    coordinators: Dict[str, CoordinatorInterface] = {}
    for grohe_device in devices:
        if grohe_device.type == GroheTypes.GROHE_SENSE:
            sense_coordinator = SenseCoordinator(ha, DOMAIN, grohe_device, api, polling, log_response_data)
            coordinators[grohe_device.appliance_id] = sense_coordinator
        elif grohe_device.type == GroheTypes.GROHE_SENSE_GUARD:
            guard_coordinator = GuardCoordinator(ha, DOMAIN, grohe_device, api, polling, log_response_data)
            coordinators[grohe_device.appliance_id] = guard_coordinator
        elif grohe_device.type == GroheTypes.GROHE_BLUE_HOME:
            blue_home_coordinator = BlueHomeCoordinator(ha, DOMAIN, grohe_device, api, polling, log_response_data)
            coordinators[grohe_device.appliance_id] = blue_home_coordinator
        elif grohe_device.type == GroheTypes.GROHE_BLUE_PROFESSIONAL:
            blue_prof_coordinator = BlueProfCoordinator(ha, DOMAIN, grohe_device, api, polling, log_response_data)
            coordinators[grohe_device.appliance_id] = blue_prof_coordinator

    # Add a generic profile coordinator so that we can use general data for the user profile as well
    profile_coordinator = ProfileCoordinator(ha, DOMAIN, api, log_response_data)
    coordinators[api.user_id] = profile_coordinator

    # Store devices and login information into hass object
    ha.data[DOMAIN] = {}
    ha.data[DOMAIN][entry.entry_id] = {'session': api, 'devices': devices, 'coordinator': coordinators, 'notifications': notifications, 'config': config}

    await ha.config_entries.async_forward_entry_setups(entry, CONF_PLATFORM)

    await profile_coordinator.async_config_entry_first_refresh()

    ####### OPTIONS - FLOW RELOAD ######################################################################################
    async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        _LOGGER.debug("Updating Grohe Sense options")
        polling = config_entry.options.get('polling', 300)
        request_timeout = config_entry.options.get('request_timeout', 10)
        connect_timeout = config_entry.options.get('connect_timeout', 5)
        log_response_data = config_entry.options.get('log_response_data', False)

        httpx_client_ha.timeout = httpx.Timeout(request_timeout, connect=connect_timeout)

        for entity in hass.data[DOMAIN].values():
            for coordinator in entity["coordinator"].values():
                coordinator.set_polling_interval(polling)
                coordinator.set_log_response_data(log_response_data)
                await coordinator.async_request_refresh()

    entry.async_on_unload(entry.add_update_listener(update_listener))

    ####### SERVICES ###################################################################################################
    async def handle_dashboard_export(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug('Export data for params: %s', call.data)
        try:
            return await api.get_dashboard()
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def handle_get_appliance_data(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug('Get data for params: %s', call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])
        group_by_str = call.data.get('group_by').lower() if call.data.get('group_by') else None
        date_from_in = call.data.get('date_from') if call.data.get('date_from') else None
        date_to_in = call.data.get('date_to') if call.data.get('date_to') else None

        if device:
            try:
                if group_by_str is None:
                    group_by = GroheGroupBy.DAY if device.type == GroheTypes.GROHE_SENSE else GroheGroupBy.HOUR
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

                return await api.get_appliance_data(device.location_id, device.room_id, device.appliance_id,
                                                    date_from,
                                                    date_to, group_by, False)
            except Exception as e:
                raise HomeAssistantError(str(e))
        else:
            raise HomeAssistantError('Device not found')

    async def handle_get_appliance_details(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug('Get details for params: %s', call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])

        if device:
            try:
                return await api.get_appliance_details(device.location_id, device.room_id, device.appliance_id)
            except Exception as e:
                raise HomeAssistantError(str(e))
        else:
            raise HomeAssistantError('Device not found')

    async def handle_get_appliance_command(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug('Get possible commands for params: %s', call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])

        if device:
            try:
                data = await api.get_appliance_command(device.location_id, device.room_id, device.appliance_id)
                if data is None:
                    return {}
                else:
                    return data
            except Exception as e:
                raise HomeAssistantError(str(e))
        else:
            raise HomeAssistantError('Device not found')

    async def handle_set_appliance_command(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug('Set commands for params: %s', call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])
        commands = call.data.get('commands')

        data_to_send = {'command': commands}
        if device:
            try:
                data = await api.set_appliance_command(device.location_id, device.room_id, device.appliance_id, device.type, data_to_send)
                if data is None:
                    return {}
                else:
                    return data
            except Exception as e:
                raise HomeAssistantError(str(e))
        else:
            raise HomeAssistantError('Device not found')

    async def handle_tap_water(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug('Tap water for params: %s', call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])
        water_type = call.data.get('water_type')
        water_amount = call.data.get('amount')


        if device and (device.type == GroheTypes.GROHE_BLUE_HOME or device.type == GroheTypes.GROHE_BLUE_PROFESSIONAL):
            try:
                mapped_water_type = GroheTapType[water_type.upper()]
                data_to_send = {'command': {'tap_type': mapped_water_type.value, 'tap_amount': water_amount}}
                data = await api.set_appliance_command(device.location_id, device.room_id, device.appliance_id, device.type, data_to_send)
                if data is None:
                    return {}
                else:
                    return data
            except Exception as e:
                raise HomeAssistantError(str(e))
        else:
            raise HomeAssistantError("Device does not exist or device is not a Grohe Blue Home or Grohe Blue Professional device")

    async def handle_get_appliance_status(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug('Get status for params: %s', call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])

        if device:
            try:
                data = await api.get_appliance_status(device.location_id, device.room_id, device.appliance_id)
                if data is None:
                    return {}
                elif isinstance(data, list) and len(data) > 0:
                    return { 'status': data }
                else:
                    return data
            except Exception as e:
                raise HomeAssistantError(str(e))
        else:
            raise HomeAssistantError('Device not found')

    async def handle_get_appliance_notifications(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug('Get notifications for params: %s', call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])

        if device:
            try:
                data = await api.get_appliance_notifications(device.location_id, device.room_id, device.appliance_id)

                if data is None:
                    return {}
                elif isinstance(data, list) and len(data) > 0:
                    return {
                        'notifications': [dict(notification) for notification in data]
                    }
                else:
                    return {}
            except Exception as e:
                raise HomeAssistantError(str(e))
        else:
            raise HomeAssistantError('Device not found')

    async def handle_get_appliance_pressure_measurement(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug('Get pressure measurement for params: %s', call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])

        if device:
            try:
                data = await api.get_appliance_pressure_measurement(device.location_id, device.room_id, device.appliance_id)

                if data is None:
                    return {}
                elif isinstance(data, list) and len(data) > 0:
                    return {
                        'pressure_measurements': [dict(measurement) for measurement in data]
                    }
                else:
                    return data
            except Exception as e:
                raise HomeAssistantError(str(e))
        else:
            raise HomeAssistantError('Device not found')

    async def handle_get_profile_notifications(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug('Get profile notifications for params: %s', call.data)
        limit = call.data.get('limit')
        if limit is None:
            limit = 50

        try:
            data = await api.get_profile_notifications(limit)

            if data is None:
                return {}
            elif isinstance(data, list) and len(data) > 0:
                return {
                    'notifications': [dict(notification) for notification in data]
                }
            else:
                return data
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def handle_set_snooze(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug('Set snooze for params: %s', call.data)
        device = find_device_by_device_id(ha, devices, call.data.get('device_id')[0])
        duration = call.data.get('duration')

        if device and (device.type == GroheTypes.GROHE_SENSE_GUARD):
            try:
                data = await api.set_snooze(device.location_id, device.room_id, device.appliance_id, duration)
                if data is None:
                    return {}
                else:
                    return data
            except Exception as e:
                raise HomeAssistantError(str(e))
        else:
            raise HomeAssistantError('Device does not exist or device is not a Grohe Sense Guard device')

    async def handle_disable_snooze(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug('Disable snooze for params: %s', call.data)
        device = find_device_by_device_id(ha, devices, call.data.get("device_id")[0])

        if device and (device.type == GroheTypes.GROHE_SENSE_GUARD):
            try:
                data = await api.disable_snooze(device.location_id, device.room_id, device.appliance_id)
                if data is None:
                    return {}
                else:
                    return data
            except Exception as e:
                raise HomeAssistantError(str(e))
        else:
            raise HomeAssistantError('Device does not exist or device is not a Grohe Sense Guard device')



    ha.services.async_register(DOMAIN, 'get_dashboard', handle_dashboard_export, schema=None, supports_response=SupportsResponse.ONLY)
    ha.services.async_register(
        DOMAIN,
        'get_appliance_data',
        handle_get_appliance_data,
        schema=voluptuous.Schema({
            voluptuous.Required('device_id'): All(
                [str],
                Length(min=1)
            ),
            voluptuous.Optional('group_by'): str,
            voluptuous.Optional('date_from'): str,
            voluptuous.Optional('date_to'): str,
        }),
        supports_response=SupportsResponse.ONLY)

    ha.services.async_register(
        DOMAIN,
        'get_appliance_details',
        handle_get_appliance_details,
        schema=voluptuous.Schema({
            voluptuous.Required('device_id'): All(
                [str],
                Length(min=1)
            ),
        }),
        supports_response=SupportsResponse.ONLY)

    ha.services.async_register(
        DOMAIN,
        'get_appliance_command',
        handle_get_appliance_command,
        schema=voluptuous.Schema({
            voluptuous.Required('device_id'): All(
                [str],
                Length(min=1)
            ),
        }),
        supports_response=SupportsResponse.ONLY)

    ha.services.async_register(
        DOMAIN,
        'get_appliance_status',
        handle_get_appliance_status,
        schema=voluptuous.Schema({
            voluptuous.Required('device_id'): All(
                [str],
                Length(min=1)
            ),
        }),
        supports_response=SupportsResponse.ONLY)

    ha.services.async_register(
        DOMAIN,
        'get_appliance_notifications',
        handle_get_appliance_notifications,
        schema=voluptuous.Schema({
            voluptuous.Required('device_id'): All(
                [str],
                Length(min=1)
            ),
        }),
        supports_response=SupportsResponse.ONLY)

    ha.services.async_register(
        DOMAIN,
        'get_appliance_pressure_measurement',
        handle_get_appliance_pressure_measurement,
        schema=voluptuous.Schema({
            voluptuous.Required('device_id'): All(
                [str],
                Length(min=1)
            ),
        }),
        supports_response=SupportsResponse.ONLY)

    ha.services.async_register(
        DOMAIN,
        'set_appliance_command',
        handle_set_appliance_command,
        schema=voluptuous.Schema({
            voluptuous.Required('device_id'): All(
                [str],
                Length(min=1)
            ),
            voluptuous.Required('commands'): dict,
        }),
        supports_response=SupportsResponse.ONLY)

    ha.services.async_register(
        DOMAIN,
        'get_profile_notifications',
        handle_get_profile_notifications,
        schema=voluptuous.Schema({
            voluptuous.Optional('limit'): int,
        }),
        supports_response=SupportsResponse.ONLY)

    ha.services.async_register(
        DOMAIN,
        'tap_water',
        handle_tap_water,
        schema=voluptuous.Schema({
            voluptuous.Required('device_id'): All(
                [str],
                Length(min=1)
            ),
            voluptuous.Required('water_type'): str,
            voluptuous.Required('amount'): int,
        }),
        supports_response=SupportsResponse.ONLY)

    ha.services.async_register(
        DOMAIN,
        'set_snooze',
        handle_set_snooze,
        schema=voluptuous.Schema({
            voluptuous.Optional('duration'): int,
            voluptuous.Required('device_id'): All(
                [str],
                Length(min=1)
            ),
        }),
        supports_response=SupportsResponse.ONLY)

    ha.services.async_register(
        DOMAIN,
        'disable_snooze',
        handle_disable_snooze,
        schema=voluptuous.Schema({
            voluptuous.Required('device_id'): All(
                [str],
                Length(min=1)
            ),
        }),
        supports_response=SupportsResponse.ONLY)

    return True