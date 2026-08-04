"""Runtime data stored on the Grohe SmartHome config entry."""

from dataclasses import dataclass

from grohe import GroheClient
from homeassistant.config_entries import ConfigEntry

from custom_components.grohe_smarthome.dto.config_dtos import (
    ConfigDto,
    NotificationsDto,
)
from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice
from custom_components.grohe_smarthome.entities.interface.coordinator_interface import (
    CoordinatorInterface,
)


@dataclass
class GroheRuntimeData:
    """Data stored on a Grohe SmartHome config entry at runtime."""

    session: GroheClient
    devices: list[GroheDevice]
    coordinator: dict[str, CoordinatorInterface]
    notifications: NotificationsDto
    config: ConfigDto


type GroheConfigEntry = ConfigEntry[GroheRuntimeData]
