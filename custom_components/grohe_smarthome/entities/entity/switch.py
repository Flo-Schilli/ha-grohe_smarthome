import logging

from benedict import benedict
from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from custom_components.grohe_smarthome.dto.config_dtos import SwitchDto
from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice

_LOGGER = logging.getLogger(__name__)


class Switch(CoordinatorEntity, SwitchEntity):
    def __init__(
        self,
        domain: str,
        coordinator: DataUpdateCoordinator,
        device: GroheDevice,
        switch: SwitchDto,
        initial_value: dict[str, any] = None,
    ):
        super().__init__(coordinator)
        self._device = device
        self._domain = domain
        self._switch = switch
        self._coordinator = coordinator
        self._is_on: bool | None = self._get_value((initial_value or {}).get("details"))

        self._attr_name = self._switch.name
        self._attr_has_entity_name = True
        self._attr_entity_registry_enabled_default = self._switch.enabled

        if self._switch.device_class is not None:
            self._attr_device_class = SwitchDeviceClass(
                self._switch.device_class.lower()
            )

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

    def _get_value(self, full_data: dict[str, any] | None) -> bool | None:
        if full_data is not None and self._switch.keypath is not None:
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

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data is not None:
            self._is_on = self._get_value(self.coordinator.data.get("details"))
            self.async_write_ha_state()

    async def _set_state(self, state: bool) -> None:
        if self._switch.keypath is not None:
            data_to_set = benedict()
            data_to_set[self._switch.keypath] = state
            await self._coordinator.set_config(data_to_set)

    async def async_turn_on(self, **kwargs) -> None:
        _LOGGER.info("Turning on %s for %s", self._switch.name, self._device.name)
        await self._set_state(True)

    async def async_turn_off(self, **kwargs) -> None:
        _LOGGER.info("Turning off %s for %s", self._switch.name, self._device.name)
        await self._set_state(False)
