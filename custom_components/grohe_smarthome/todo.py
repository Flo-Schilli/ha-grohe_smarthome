import logging

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .dto.runtime_data import GroheConfigEntry
from .entities.entity.todo import Todo
from .entities.entity_helper import EntityHelper

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: GroheConfigEntry, async_add_entities
):
    _LOGGER.debug(f"Adding todo entities from config entry {entry}")

    runtime_data = entry.runtime_data
    api = runtime_data.session
    devices = runtime_data.devices
    coordinators = runtime_data.coordinator
    notification_config = runtime_data.notifications
    helper: EntityHelper = EntityHelper(runtime_data.config, DOMAIN)

    entities: list[Todo] = []
    for device in devices:
        if coordinators.get(api.user_id) is not None:
            entity = await helper.add_todo_entities(
                coordinators.get(api.user_id), device, notification_config
            )
            entities.extend(entity)

    if entities:
        async_add_entities(entities)
