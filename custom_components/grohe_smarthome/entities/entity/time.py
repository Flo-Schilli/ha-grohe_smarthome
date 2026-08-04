import logging
from datetime import time as dt_time

from benedict import benedict
from homeassistant.components.time import TimeEntity
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from custom_components.grohe_smarthome.dto.config_dtos import TimeDto
from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice

_LOGGER = logging.getLogger(__name__)


def _minutes_to_time(minutes: int | None) -> dt_time | None:
    if minutes is None:
        return None
    return dt_time(hour=(int(minutes) // 60) % 24, minute=int(minutes) % 60)


def _time_to_minutes(value: dt_time) -> int:
    return value.hour * 60 + value.minute


class Time(CoordinatorEntity, TimeEntity):
    def __init__(
        self,
        domain: str,
        coordinator: DataUpdateCoordinator,
        device: GroheDevice,
        time_config: TimeDto,
        initial_value: dict[str, any] = None,
    ):
        super().__init__(coordinator)
        self._device = device
        self._domain = domain
        self._time = time_config
        self._coordinator = coordinator
        self._attr_native_value = self._get_value((initial_value or {}).get("details"))

        self._attr_name = self._time.name
        self._attr_has_entity_name = True
        self._attr_entity_registry_enabled_default = self._time.enabled

    @property
    def unique_id(self):
        return (
            f"{self._device.appliance_id}_{self._time.name.lower().replace(' ', '_')}"
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

    def _get_value(self, full_data: dict[str, any] | None) -> dt_time | None:
        if full_data is not None and self._time.keypath is not None:
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

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data is not None:
            self._attr_native_value = self._get_value(
                self.coordinator.data.get("details")
            )
            self.async_write_ha_state()

    async def async_set_value(self, value: dt_time) -> None:
        if self._time.keypath is not None:
            data_to_set = benedict()
            data_to_set[self._time.keypath] = _time_to_minutes(value)
            await self._coordinator.set_config(data_to_set)
