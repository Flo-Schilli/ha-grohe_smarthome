import logging

from grohe import GroheClient
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice

_LOGGER = logging.getLogger(__name__)


class GroheSenseGuardButton(ButtonEntity):
    def __init__(self, domain: str, auth_session: GroheClient, device: GroheDevice):
        self._auth_session = auth_session
        self._device = device
        self._domain = domain

        # Needed for ButtonEntity
        self._attr_icon = "mdi:water"
        self._attr_name = f"{self._device.name} pressure_measurement"

    @property
    def unique_id(self):
        return f"{self._device.appliance_id}_pressure_measurement"

    @property
    def device_info(self) -> DeviceInfo | None:
        return DeviceInfo(
            identifiers={(self._domain, self._device.appliance_id)},
            name=self._device.name,
            manufacturer="Grohe",
            model="Sense Guard",
            sw_version=self._device.sw_version,
        )

    async def async_press(self) -> None:
        _LOGGER.info("Starting pressure measurement for %s", self._device.name)
        await self._auth_session.start_pressure_measurement(
            self._device.location_id, self._device.room_id, self._device.appliance_id
        )
