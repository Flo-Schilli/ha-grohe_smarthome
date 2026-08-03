import logging
from datetime import timedelta

from benedict import benedict
from homeassistant.components.valve import (
    ValveDeviceClass,
    ValveEntity,
    ValveEntityFeature,
)
from homeassistant.const import STATE_UNKNOWN
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import Throttle

from custom_components.grohe_smarthome.dto.config_dtos import ValveDto
from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice
from custom_components.grohe_smarthome.entities.interface.coordinator_valve_interface import (
    CoordinatorValveInterface,
)

_LOGGER = logging.getLogger(__name__)

VALVE_UPDATE_DELAY = timedelta(minutes=1)


class Valve(ValveEntity):
    def __init__(
        self,
        domain: str,
        coordinator: DataUpdateCoordinator,
        device: GroheDevice,
        valve: ValveDto,
    ):
        self._device = device
        self._domain = domain
        self._valve = valve
        self._is_closed = STATE_UNKNOWN
        self._coordinator = coordinator

        # Needed for ValveEntity
        self._attr_icon = "mdi:water"

        self._attr_name = f"{self._device.name} {self._valve.name}"
        self._attr_has_entity_name = False

        # Set the integration unavailable until first update was successful.
        self._attr_available = False

        self._attr_supported_features = (
            ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE
        )

        if self._valve.device_class is not None:
            self._attr_device_class = ValveDeviceClass(self._valve.device_class.lower())

    @property
    def unique_id(self):
        return (
            f"{self._device.appliance_id}_{self._valve.name.lower().replace(' ', '_')}"
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
    def reports_position(self) -> bool:
        return False

    @property
    def is_closed(self) -> bool:
        return self._is_closed

    def _get_value(self, full_data: dict[str, any]) -> bool | None:
        if self._valve.keypath is not None:
            # We do have some data here, so let's extract it
            data = benedict(full_data)
            value: bool | None = None
            try:
                value = data.get(self._valve.keypath)

            except KeyError:
                _LOGGER.error(
                    f"Device: {self._device.name} ({self._device.appliance_id}) with valve: {self._valve.name} has no value on keypath: {self._valve.keypath}"
                )

            return value

    @Throttle(VALVE_UPDATE_DELAY)
    async def async_update(self):
        if isinstance(self._coordinator, CoordinatorValveInterface):
            data = await self._coordinator.get_valve_value()
            valve_value = self._get_value(data)
            if valve_value is not None:
                self._attr_available = True
                self._is_closed = not valve_value
            else:
                self._attr_available = False

            _LOGGER.debug(
                f"Updating valve value for {self._device.name}: {valve_value} (isAvailable: {self._attr_available}, isClosed: {self._is_closed})"
            )
            _LOGGER.debug(
                f"Full command value for {self._device.name} and getting the valve value: {data})"
            )

    async def _set_state(self, state):
        if (
            isinstance(self._coordinator, CoordinatorValveInterface)
            and self._valve.keypath is not None
        ):
            data_to_set = benedict()
            data_to_set[self._valve.keypath] = state
            response_data = await self._coordinator.set_valve(data_to_set)

            value = not self._get_value(response_data)
            _LOGGER.debug(
                f'Device: {self._device.name} ({self._device.appliance_id}) with valve name: "{self._valve.name}" has the following value on keypath "{self._valve.keypath}": {value}'
            )

            self._is_closed = value

    async def async_open_valve(self) -> None:
        _LOGGER.info("Turning on water for %s", self._device.name)
        await self._set_state(True)

    async def async_close_valve(self, **kwargs):
        _LOGGER.info("Turning off water for %s", self._device.name)
        await self._set_state(False)
