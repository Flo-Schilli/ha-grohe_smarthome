import logging

from benedict import benedict
from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from custom_components.grohe_smarthome.dto.config_dtos import NumberDto
from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice
from custom_components.grohe_smarthome.entities.helper import Helper

_LOGGER = logging.getLogger(__name__)


class Number(CoordinatorEntity, NumberEntity):
    def __init__(
        self,
        domain: str,
        coordinator: DataUpdateCoordinator,
        device: GroheDevice,
        number: NumberDto,
        initial_value: dict[str, any] = None,
    ):
        super().__init__(coordinator)
        self._device = device
        self._domain = domain
        self._number = number
        self._coordinator = coordinator
        self._attr_native_value = self._get_value((initial_value or {}).get("details"))

        self._attr_name = self._number.name
        self._attr_has_entity_name = True
        self._attr_entity_registry_enabled_default = self._number.enabled

        self._attr_native_min_value = self._number.min_value
        self._attr_native_max_value = self._number.max_value
        self._attr_native_step = self._number.step

        if self._number.unit is not None:
            self._attr_native_unit_of_measurement = Helper.get_ha_units(
                self._number.unit
            )

        if self._number.device_class is not None:
            self._attr_device_class = NumberDeviceClass(
                self._number.device_class.lower()
            )

    @property
    def unique_id(self):
        return (
            f"{self._device.appliance_id}_{self._number.name.lower().replace(' ', '_')}"
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

    def _get_value(self, full_data: dict[str, any] | None) -> float | None:
        if full_data is not None and self._number.keypath is not None:
            # We do have some data here, so let's extract it
            data = benedict(full_data)
            value: float | None = None
            try:
                value = data.get(self._number.keypath)

            except KeyError:
                _LOGGER.error(
                    f"Device: {self._device.name} ({self._device.appliance_id}) with number: {self._number.name} has no value on keypath: {self._number.keypath}"
                )

            return value

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data is not None:
            self._attr_native_value = self._get_value(
                self.coordinator.data.get("details")
            )
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        if self._number.keypath is not None:
            data_to_set = benedict()
            data_to_set[self._number.keypath] = value
            await self._coordinator.set_config(data_to_set)
