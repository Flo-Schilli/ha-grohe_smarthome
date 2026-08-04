import logging
from datetime import timedelta

from benedict import benedict
from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import Throttle

from custom_components.grohe_smarthome.dto.config_dtos import SwitchDto
from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice
from custom_components.grohe_smarthome.entities.interface.coordinator_config_interface import (
    CoordinatorConfigInterface,
)

_LOGGER = logging.getLogger(__name__)

SWITCH_UPDATE_DELAY = timedelta(minutes=1)


class Switch(SwitchEntity):
    def __init__(
        self,
        domain: str,
        coordinator: DataUpdateCoordinator,
        device: GroheDevice,
        switch: SwitchDto,
    ):
        self._device = device
        self._domain = domain
        self._switch = switch
        self._is_on: bool | None = None
        self._coordinator = coordinator

        self._attr_name = self._switch.name
        self._attr_has_entity_name = True

        # Set the integration unavailable until first update was successful.
        self._attr_available = False

        self._attr_entity_registry_enabled_default = self._switch.enabled

        if self._switch.device_class is not None:
            self._attr_device_class = SwitchDeviceClass(self._switch.device_class.lower())

    @property
    def unique_id(self):
        return (
            f"{self._device.appliance_id}_{self._switch.name.lower().replace(' ', '_')}"
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

    @property
    def is_on(self) -> bool | None:
        return self._is_on

    def _get_value(self, full_data: dict[str, any]) -> bool | None:
        if self._switch.keypath is not None:
            # We do have some data here, so let's extract it
            data = benedict(full_data)
            value: bool | None = None
            try:
                value = data.get(self._switch.keypath)

            except KeyError:
                _LOGGER.error(
                    f"Device: {self._device.name} ({self._device.appliance_id}) with switch: {self._switch.name} has no value on keypath: {self._switch.keypath}"
                )

            return value

    @Throttle(SWITCH_UPDATE_DELAY)
    async def async_update(self):
        if isinstance(self._coordinator, CoordinatorConfigInterface):
            data = await self._coordinator.get_config_value()
            value = self._get_value(data)
            self._attr_available = value is not None
            self._is_on = value

            _LOGGER.debug(
                f"Updating switch value for {self._device.name}: {value} (isAvailable: {self._attr_available})"
            )

    async def _set_state(self, state: bool):
        if (
            isinstance(self._coordinator, CoordinatorConfigInterface)
            and self._switch.keypath is not None
        ):
            data_to_set = benedict()
            data_to_set[self._switch.keypath] = state
            response_data = await self._coordinator.set_config(data_to_set)

            value = self._get_value(response_data)
            _LOGGER.debug(
                f'Device: {self._device.name} ({self._device.appliance_id}) with switch name: "{self._switch.name}" has the following value on keypath "{self._switch.keypath}": {value}'
            )

            self._is_on = value

    async def async_turn_on(self, **kwargs) -> None:
        _LOGGER.info("Turning on %s for %s", self._switch.name, self._device.name)
        await self._set_state(True)

    async def async_turn_off(self, **kwargs) -> None:
        _LOGGER.info("Turning off %s for %s", self._switch.name, self._device.name)
        await self._set_state(False)
