import asyncio
import logging
from datetime import datetime, timedelta

from grohe import GroheClient, GroheForbiddenError, GroheUnauthorizedError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice
from custom_components.grohe_smarthome.dto.notification_dto import Notification
from custom_components.grohe_smarthome.entities.interface.coordinator_interface import (
    CoordinatorInterface,
)

_LOGGER = logging.getLogger(__name__)


class SenseCoordinator(DataUpdateCoordinator, CoordinatorInterface):
    def __init__(
        self,
        hass: HomeAssistant,
        domain: str,
        device: GroheDevice,
        api: GroheClient,
        polling: int = 300,
        log_response_data: bool = False,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Grohe Sense",
            update_interval=timedelta(seconds=polling),
            always_update=True,
        )
        self._api = api
        self._domain = domain
        self._device = device
        self._timezone = datetime.now().astimezone().tzinfo
        self._last_update = datetime.now().astimezone().replace(tzinfo=self._timezone)
        self._notifications: list[Notification] = []
        self._log_response_data = log_response_data
        self._initial_value_lock = asyncio.Lock()

    async def _get_data(self) -> dict[str, any]:
        api_data = await self._api.get_appliance_details(
            self._device.location_id, self._device.room_id, self._device.appliance_id
        )

        try:
            status = {val["type"]: val["value"] for val in api_data["status"]}
        except (AttributeError, KeyError, TypeError) as e:
            _LOGGER.debug(f"Status could not be mapped: {e}")
            status = None

        data = {"details": api_data, "status": status}
        return data

    async def _async_update_data(self) -> dict:
        try:
            _LOGGER.debug(
                f"Updating device data for device {self._device.type} with name {self._device.name} (appliance = {self._device.appliance_id})"
            )
            data = await self._get_data()

            if self._log_response_data:
                _LOGGER.debug(
                    f"Response data for {self._device.name} (appliance = {self._device.appliance_id}): {data}"
                )

            self._last_update = (
                datetime.now().astimezone().replace(tzinfo=self._timezone)
            )
            return data

        except GroheUnauthorizedError as e:
            raise ConfigEntryAuthFailed(str(e)) from e

        except GroheForbiddenError as e:
            _LOGGER.warning(
                "Grohe denied the request for %s (%s), keeping last known data: %s",
                self._device.name,
                self._device.appliance_id,
                e,
            )
            if self.data is not None:
                return self.data
            raise UpdateFailed(str(e)) from e

        except Exception as e:
            _LOGGER.error("Error updating Grohe Sense data: %s", str(e))
            raise UpdateFailed(f"Error updating Grohe Sense data: {e}") from e

    async def get_initial_value(self) -> dict[str, any]:
        # HA sets up all platforms concurrently, and each one calls this during its own
        # setup - the lock makes sure only one real fetch happens; the rest just wait for
        # it and reuse the result, instead of each racing in with "self.data is None".
        async with self._initial_value_lock:
            if self.data is None:
                self.data = await self._get_data()
            return self.data

    def set_polling_interval(self, polling: int) -> None:
        self.update_interval = timedelta(seconds=polling)
        self.async_update_listeners()

    def set_log_response_data(self, log_response_data: bool) -> None:
        self._log_response_data = log_response_data
