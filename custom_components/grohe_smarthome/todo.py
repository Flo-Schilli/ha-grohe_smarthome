import logging

from grohe import GroheClient
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .dto.config_dtos import ConfigDto, NotificationsDto
from .dto.grohe_device import GroheDevice
from .entities.entity.todo import Todo
from .entities.entity_helper import EntityHelper
from .entities.interface.coordinator_interface import CoordinatorInterface

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    _LOGGER.debug(f"Adding todo entities from config entry {entry}")

    data = hass.data[DOMAIN][entry.entry_id]
    api: GroheClient = data["session"]
    devices: list[GroheDevice] = data["devices"]
    config: ConfigDto = data["config"]
    coordinators: dict[str, CoordinatorInterface] = data["coordinator"]
    notification_config: NotificationsDto = data["notifications"]
    helper: EntityHelper = EntityHelper(config, DOMAIN)

    entities: list[Todo] = []
    for device in devices:
        if coordinators.get(api.user_id) is not None:
            entity = await helper.add_todo_entities(
                coordinators.get(api.user_id), device, notification_config
            )
            entities.extend(entity)

    if entities:
        async_add_entities(entities)
