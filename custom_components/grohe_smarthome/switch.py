import logging

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .dto.runtime_data import GroheConfigEntry
from .entities.entity.switch import Switch
from .entities.entity_helper import EntityHelper

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: GroheConfigEntry, async_add_entities
):
    _LOGGER.debug(f"Adding switch entities from config entry {entry}")

    runtime_data = entry.runtime_data
    devices = runtime_data.devices
    coordinators = runtime_data.coordinator
    helper: EntityHelper = EntityHelper(runtime_data.config, DOMAIN)

    entities: list[Switch] = []
    for device in devices:
        coordinator = coordinators.get(device.appliance_id)
        if coordinator is not None:
            entities.extend(await helper.add_switch_entities(coordinator, device))

    if entities:
        async_add_entities(entities)
