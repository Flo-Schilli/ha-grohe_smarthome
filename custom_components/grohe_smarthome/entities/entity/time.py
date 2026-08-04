import logging
from datetime import time as dt_time
from datetime import timedelta

from benedict import benedict
from homeassistant.components.time import TimeEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import Throttle

from custom_components.grohe_smarthome.dto.config_dtos import TimeDto
from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice
from custom_components.grohe_smarthome.entities.interface.coordinator_config_interface import (
    CoordinatorConfigInterface,
)

_LOGGER = logging.getLogger(__name__)

TIME_UPDATE_DELAY = timedelta(minutes=1)


def _minutes_to_time(minutes: int | None) -> dt_time | None:
    if minutes is None:
        return None
    return dt_time(hour=(int(minutes) // 60) % 24, minute=int(minutes) % 60)


def _time_to_minutes(value: dt_time) -> int:
    return value.hour * 60 + value.minute


class Time(TimeEntity):
    def __init__(
        self,
        domain: str,
        coordinator: DataUpdateCoordinator,
        device: GroheDevice,
        time_config: TimeDto,
    ):
        self._device = device
        self._domain = domain
        self._time = time_config
        self._coordinator = coordinator

        self._attr_name = self._time.name
        self._attr_has_entity_name = True

        # Set the integration unavailable until first update was successful.
        self._attr_available = False
        self._attr_native_value = None

        self._attr_entity_registry_enabled_default = self._time.enabled

    @property
    def unique_id(self):
        return f"{self._device.appliance_id}_{self._time.name.lower().replace(' ', '_')}"

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

    def _get_value(self, full_data: dict[str, any]) -> dt_time | None:
        if self._time.keypath is not None:
            # We do have some data here, so let's extract it
            data = benedict(full_data)
            minutes: int | None = None
            try:
                minutes = data.get(self._time.keypath)

            except KeyError:
                _LOGGER.error(
                    f"Device: {self._device.name} ({self._device.appliance_id}) with time: {self._time.name} has no value on keypath: {self._time.keypath}"
                )

            return _minutes_to_time(minutes)

    @Throttle(TIME_UPDATE_DELAY)
    async def async_update(self):
        if isinstance(self._coordinator, CoordinatorConfigInterface):
            data = await self._coordinator.get_config_value()
            value = self._get_value(data)
            self._attr_available = value is not None
            self._attr_native_value = value

            _LOGGER.debug(
                f"Updating time value for {self._device.name}: {value} (isAvailable: {self._attr_available})"
            )

    async def async_set_value(self, value: dt_time) -> None:
        if (
            isinstance(self._coordinator, CoordinatorConfigInterface)
            and self._time.keypath is not None
        ):
            data_to_set = benedict()
            data_to_set[self._time.keypath] = _time_to_minutes(value)
            response_data = await self._coordinator.set_config(data_to_set)

            new_value = self._get_value(response_data)
            _LOGGER.debug(
                f'Device: {self._device.name} ({self._device.appliance_id}) with time name: "{self._time.name}" has the following value on keypath "{self._time.keypath}": {new_value}'
            )

            self._attr_native_value = new_value
