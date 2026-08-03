"""initialize Grohe SmartHome component."""

import logging
import os.path

import httpx
from grohe import GroheClient, GroheTypes
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, HomeAssistantError
from homeassistant.helpers import httpx_client
from homeassistant.helpers.device_registry import DeviceEntry

from custom_components.grohe_smarthome.const import (
    CONF_PASSWORD,
    CONF_PLATFORM,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.grohe_smarthome.dto.config_dtos import ConfigDto
from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice
from custom_components.grohe_smarthome.entities.config_loader import ConfigLoader
from custom_components.grohe_smarthome.entities.coordinator import (
    BlueHomeCoordinator,
    BlueProfCoordinator,
    GuardCoordinator,
    ProfileCoordinator,
    SenseCoordinator,
)
from custom_components.grohe_smarthome.entities.entity_helper import EntityHelper
from custom_components.grohe_smarthome.entities.interface.coordinator_interface import (
    CoordinatorInterface,
)
from custom_components.grohe_smarthome.services import async_register_services

_LOGGER = logging.getLogger(__name__)


async def async_unload_entry(ha: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""

    _LOGGER.debug("Unloading Grohe Entry")
    unload_ok = await ha.config_entries.async_unload_platforms(entry, CONF_PLATFORM)

    if unload_ok:
        ha.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_setup_entry(ha: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Grohe SmartHome from a config entry."""

    _LOGGER.debug("Loading Grohe Entry")

    config_loader = ConfigLoader(os.path.join(os.path.dirname(__file__), "config"))

    notifications = await ha.async_add_executor_job(config_loader.load_notifications)
    config: ConfigDto = await ha.async_add_executor_job(config_loader.load_config)

    # Login to Grohe backend
    httpx_client_ha = httpx_client.get_async_client(ha)
    httpx_client_ha.cookies.clear()
    # Options
    network_options = entry.options.get("network_options", {})
    logging_options = entry.options.get("logging_options", {})
    request_timeout = network_options.get("request_timeout", 10)
    connect_timeout = network_options.get("connect_timeout", 5)
    log_response_data = logging_options.get("log_response_data", False)

    httpx_client_ha.timeout = httpx.Timeout(request_timeout, connect=connect_timeout)

    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)

    if not username or not password:
        raise HomeAssistantError("Username and password are required")

    api = GroheClient(username, password, httpx_client_ha, 120)
    await api.login()

    # Get all devices available
    devices: list[GroheDevice] = await GroheDevice.get_devices(api)

    polling = entry.options.get("polling", 900)
    coordinators: dict[str, CoordinatorInterface] = {}
    for grohe_device in devices:
        if grohe_device.type == GroheTypes.GROHE_SENSE:
            sense_coordinator = SenseCoordinator(
                ha, DOMAIN, grohe_device, api, polling, log_response_data
            )
            coordinators[grohe_device.appliance_id] = sense_coordinator
        elif grohe_device.type == GroheTypes.GROHE_SENSE_GUARD:
            device = config.get_device_config(
                EntityHelper.get_config_name_by_device_type(grohe_device)
            )
            guard_coordinator = GuardCoordinator(
                ha,
                DOMAIN,
                grohe_device,
                api,
                device.device_config,
                polling,
                log_response_data,
            )
            coordinators[grohe_device.appliance_id] = guard_coordinator
        elif grohe_device.type == GroheTypes.GROHE_BLUE_HOME:
            blue_home_coordinator = BlueHomeCoordinator(
                ha, DOMAIN, grohe_device, api, polling, log_response_data
            )
            coordinators[grohe_device.appliance_id] = blue_home_coordinator
        elif grohe_device.type == GroheTypes.GROHE_BLUE_PROFESSIONAL:
            blue_prof_coordinator = BlueProfCoordinator(
                ha, DOMAIN, grohe_device, api, polling, log_response_data
            )
            coordinators[grohe_device.appliance_id] = blue_prof_coordinator

    # Add a generic profile coordinator so that we can use general data for the user profile as well
    profile_coordinator = ProfileCoordinator(
        ha, DOMAIN, api, polling, log_response_data
    )
    coordinators[api.user_id] = profile_coordinator

    # Store devices and login information into hass object
    ha.data[DOMAIN] = {}
    ha.data[DOMAIN][entry.entry_id] = {
        "session": api,
        "devices": devices,
        "coordinator": coordinators,
        "notifications": notifications,
        "config": config,
    }

    await ha.config_entries.async_forward_entry_setups(entry, CONF_PLATFORM)

    _LOGGER.debug("Starting first refresh for all coordinators")
    await profile_coordinator.async_config_entry_first_refresh()

    for coordinator in coordinators.values():
        if coordinator != profile_coordinator:  # Avoid refreshing it twice
            await coordinator.async_config_entry_first_refresh()

    _LOGGER.debug("All coordinators initialized with fresh data")

    # Reload options on change
    async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        _LOGGER.debug("Updating Grohe Sense options")
        polling = config_entry.options.get("polling", 300)
        # Options
        network_options = config_entry.options.get("network_options", {})
        logging_options = config_entry.options.get("logging_options", {})
        request_timeout = network_options.get("request_timeout", 10)
        connect_timeout = network_options.get("connect_timeout", 5)
        log_response_data = logging_options.get("log_response_data", False)

        httpx_client_ha.timeout = httpx.Timeout(
            request_timeout, connect=connect_timeout
        )

        for entity in hass.data[DOMAIN].values():
            for coordinator in entity["coordinator"].values():
                coordinator.set_polling_interval(polling)
                coordinator.set_log_response_data(log_response_data)
                await coordinator.async_request_refresh()

    entry.async_on_unload(entry.add_update_listener(update_listener))

    async_register_services(ha, api, devices)

    return True


async def async_remove_config_entry_device(
    ha: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    try:
        _LOGGER.debug("Removing Grohe SmartHome device %s", device_entry.id)
        devices: list[GroheDevice] = ha.data[DOMAIN][config_entry.entry_id].get(
            "devices"
        )

        device_found = False
        for device in devices:
            if any(device.appliance_id in t for t in device_entry.identifiers):
                device_found = True
                _LOGGER.debug("Removing device %s", device.appliance_id)

        devices[:] = [
            device
            for device in devices
            if not any(device.appliance_id in t for t in device_entry.identifiers)
        ]

        _LOGGER.debug(
            "All remaining device %s",
            str(ha.data[DOMAIN][config_entry.entry_id].get("devices")),
        )

        if not device_found:
            _LOGGER.warning(
                "Tried to remove Grohe SmartHome device %s, but it was not found in the list of actual devices",
                device_entry.name,
            )

        return True

    except Exception as e:
        _LOGGER.error(
            "Error removing Grohe SmartHome device %s: %s", device_entry.id, str(e)
        )
        return False
