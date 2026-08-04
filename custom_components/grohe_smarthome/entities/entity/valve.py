import logging

from benedict import benedict
from homeassistant.components.valve import (
    ValveDeviceClass,
    ValveEntity,
    ValveEntityFeature,
)
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from custom_components.grohe_smarthome.dto.config_dtos import ValveDto
from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice

_LOGGER = logging.getLogger(__name__)


class Valve(CoordinatorEntity, ValveEntity):
    def __init__(
        self,
        domain: str,
        coordinator: DataUpdateCoordinator,
        device: GroheDevice,
        valve: ValveDto,
        initial_value: dict[str, any] = None,
    ):
        super().__init__(coordinator)
        self._device = device
        self._domain = domain
        self._valve = valve
        self._coordinator = coordinator
        self._is_closed = self._get_is_closed((initial_value or {}).get("details"))

        # Needed for ValveEntity
        self._attr_icon = "mdi:water"

        self._attr_name = self._valve.name
        self._attr_has_entity_name = True

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
    def is_closed(self):
        return self._is_closed

    def _get_value(self, full_data: dict[str, any] | None) -> bool | None:
        if full_data is not None and self._valve.keypath is not None:
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

    def _get_is_closed(self, full_data: dict[str, any] | None) -> bool | str | None:
        value = self._get_value(full_data)
        return not value if value is not None else STATE_UNKNOWN

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data is not None:
            self._is_closed = self._get_is_closed(self.coordinator.data.get("details"))
            self.async_write_ha_state()

    async def _set_state(self, state):
        if self._valve.keypath is not None:
            data_to_set = benedict()
            data_to_set[self._valve.keypath] = state
            await self._coordinator.set_valve(data_to_set)

    async def async_open_valve(self) -> None:
        _LOGGER.info("Turning on water for %s", self._device.name)
        await self._set_state(True)

    async def async_close_valve(self, **kwargs):
        _LOGGER.info("Turning off water for %s", self._device.name)
        await self._set_state(False)
