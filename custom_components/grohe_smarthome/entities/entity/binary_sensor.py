import logging

from benedict import benedict
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from ...dto.config_dtos import BinarySensorDto
from ...dto.grohe_device import GroheDevice
from ..interface.coordinator_interface import CoordinatorInterface

_LOGGER = logging.getLogger(__name__)


class BinarySensor(CoordinatorEntity, BinarySensorEntity):
    def __init__(
        self,
        domain: str,
        coordinator: DataUpdateCoordinator,
        device: GroheDevice,
        binary_sensor: BinarySensorDto,
        initial_value: dict[str, any] = None,
    ):
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._device = device
        self._sensor = binary_sensor
        self._domain = domain
        self._value: bool | None = self._get_value(initial_value)

        # Needed for Sensor Entity
        self._attr_name = f"{self._device.name} {self._sensor.name}"
        self._attr_has_entity_name = False

        self._attr_entity_registry_enabled_default = self._sensor.enabled

        if self._sensor.device_class is not None:
            self._attr_device_class = BinarySensorDeviceClass(
                self._sensor.device_class.lower()
            )

        if self._sensor.category is not None:
            self._attr_entity_category = EntityCategory(self._sensor.category.lower())

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
    def unique_id(self):
        return (
            f"{self._device.appliance_id}_{self._sensor.name.lower().replace(' ', '_')}"
        )

    @property
    def is_on(self):
        return self._value

    @property
    def native_value(self):
        return self._value

    def _get_value(self, full_data: dict[str, any]) -> bool | None:
        if self._sensor.keypath is not None:
            # We do have some data here, so let's extract it
            data = benedict(full_data)
            value: bool | None = None
            try:
                value = data.get(self._sensor.keypath)

            except KeyError:
                _LOGGER.error(
                    f"Device: {self._device.name} ({self._device.appliance_id}) with binary sensor: {self._sensor.name} has no value on keypath: {self._sensor.keypath}"
                )

            _LOGGER.debug(
                f'Device: {self._device.name} ({self._device.appliance_id}) with sensor name: "{self._sensor.name}" has the following value on keypath "{self._sensor.keypath}": {value}'
            )

            return value

    @callback
    async def async_update(self):
        _LOGGER.debug(
            f"Updating binary sensor value for {self._device.name} with async_update"
        )
        if isinstance(self._coordinator, CoordinatorInterface):
            data = await self._coordinator.get_initial_value()
            self._value = self._get_value(data)

    @callback
    def _handle_coordinator_update(self) -> None:
        _LOGGER.debug(
            f"Updating binary sensor value for {self._device.name} with _handle_coordinator_update"
        )
        if (
            self._coordinator is not None
            and self._coordinator.data is not None
            and self._sensor.keypath is not None
        ):
            # We do have some data here, so let's extract it
            value = self._get_value(self._coordinator.data)
            self._value = value
