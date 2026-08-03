import logging

from benedict import benedict
from homeassistant.components.button import ButtonEntity
from homeassistant.const import STATE_UNKNOWN
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.grohe_smarthome.dto.config_dtos import ButtonDto
from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice
from custom_components.grohe_smarthome.entities.interface.coordinator_button_interface import (
    CoordinatorButtonInterface,
)

_LOGGER = logging.getLogger(__name__)


class Button(ButtonEntity):
    def __init__(
        self,
        domain: str,
        coordinator: DataUpdateCoordinator,
        device: GroheDevice,
        button: ButtonDto,
    ):
        self._device = device
        self._domain = domain
        self._button = button
        self._is_closed = STATE_UNKNOWN
        self._coordinator = coordinator

        # Needed for ValveEntity
        self._attr_icon = "mdi:water"

        self._attr_name = f"{self._device.name} {self._button.name}"
        self._attr_has_entity_name = False

    @property
    def unique_id(self):
        return (
            f"{self._device.appliance_id}_{self._button.name.lower().replace(' ', '_')}"
        )

    @property
    def device_info(self) -> DeviceInfo | None:
        return DeviceInfo(
            identifiers={(self._domain, self._device.appliance_id)},
            name=self._device.name,
            manufacturer="Grohe",
            model=self._device.device_name,
            sw_version=self._device.sw_version,
            suggested_area=self._device.room_name,
        )

    async def async_press(self) -> None:
        if (
            isinstance(self._coordinator, CoordinatorButtonInterface)
            and self._button.commands is not None
        ):
            data_to_set = benedict()
            for command in self._button.commands:
                if command.keypath is not None and command.value is not None:
                    data_to_set[command.keypath] = command.value

            _LOGGER.debug(
                f"Sending the following commands {data_to_set} to device {self._device.name}"
            )
            await self._coordinator.send_command(data_to_set)
