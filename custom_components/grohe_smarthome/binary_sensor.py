import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .dto.config_dtos import ConfigDto
from .dto.grohe_device import GroheDevice
from .entities.entity.binary_sensor import BinarySensor
from .entities.entity_helper import EntityHelper
from .entities.interface.coordinator_interface import CoordinatorInterface

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    _LOGGER.debug(f"Adding binary sensor entities from config entry {entry}")

    data = hass.data[DOMAIN][entry.entry_id]
    devices: list[GroheDevice] = data["devices"]
    config: ConfigDto = data["config"]
    coordinators: dict[str, CoordinatorInterface] = data["coordinator"]
    helper: EntityHelper = EntityHelper(config, DOMAIN)

    entities: list[BinarySensor] = []
    for device in devices:
        coordinator = coordinators.get(device.appliance_id)
        if coordinator is not None:
            entities.extend(
                await helper.add_binary_sensor_entities(coordinator, device)
            )

    if entities:
        async_add_entities(entities)
