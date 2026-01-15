import asyncio
from datetime import timedelta
import logging
from typing import Any, cast

from benedict import benedict
from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice
from custom_components.grohe_smarthome.dto.notification_dto import Notification
from custom_components.grohe_smarthome.entities.interface.coordinator_button_interface import (
    CoordinatorButtonInterface,
)
from custom_components.grohe_smarthome.entities.interface.coordinator_interface import (
    CoordinatorInterface,
)
from grohe import GroheClient
import httpx

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class BlueHomeCoordinator(
    DataUpdateCoordinator,
    CoordinatorInterface,
    CoordinatorButtonInterface,
):
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
        self._last_update = dt_util.now()
        self._notifications: list[Notification] = []
        self._log_response_data = log_response_data

        self._key_path_for_timestamp = "details.data_latest.measurement.timestamp"
        self._last_measurement_timestamp = None
        self._refresh_task_running: bool = False

        # Timeout and poll interval for background refresh
        # Integration polling has in options min 40s
        self._update_timeout = 30
        self._poll_interval = 10

    async def _async_update_data(self) -> dict[str, Any]:
        """Non-blocking data fetch."""
        _LOGGER.debug(
            "Updating device data for %s (%s)",
            self._device.name,
            self._device.appliance_id,
        )

        if self.data is not None:
            current_data = self.data
            log_msg = "using cached data"
        else:
            current_data = await self._fetch_device_data()
            log_msg = "fetched initial data"

        if self._log_response_data:
            _LOGGER.debug(
                "Response data for %s (%s) [%s]: %s",
                self._device.name,
                self._device.appliance_id,
                log_msg,
                current_data,
            )

        self._last_update = dt_util.now()

        if not self._refresh_task_running:
            self.hass.async_create_task(self._async_refresh_and_verify())

        return current_data

    async def _fetch_device_data(self) -> dict[str, Any]:
        """Retrieve data from the device."""
        api_data = await self._api.get_appliance_details(
            cast(str, self._device.location_id),
            cast(str, self._device.room_id),
            self._device.appliance_id,
        )

        try:
            status = {val["type"]: val["value"] for val in api_data.get("status", [])}
        except Exception as err:
            _LOGGER.debug("Status mapping failed: %s", err)
            status = None

        return {"details": api_data, "status": status}

    async def _async_refresh_and_verify(self) -> None:
        """Background refresh workflow.

        1. Send refresh command to device
        2. Periodically check for new data
        3. Update coordinator when new data arrives
        """
        self._refresh_task_running = True

        try:
            old_ts = self._last_measurement_timestamp

            await self._send_refresh_command()

            max_attempts = self._update_timeout // self._poll_interval
            attempts = 0

            while attempts < max_attempts:
                await asyncio.sleep(self._poll_interval)
                attempts += 1
                new_data = await self._fetch_device_data()
                ts = self._extract_timestamp(new_data)

                if ts and (old_ts is None or ts > old_ts):
                    self._last_measurement_timestamp = ts

                    self.async_set_updated_data(new_data)

                    _LOGGER.debug(
                        "New measurement received for %s (%s) after %d/%d attempts",
                        self._device.name,
                        self._device.appliance_id,
                        attempts,
                        max_attempts,
                    )
                    return

            _LOGGER.warning(
                "No new measurement received for %s (%s) after %d attempts (%s seconds)",
                self._device.name,
                self._device.appliance_id,
                attempts,
                self._update_timeout,
            )

        except Exception as err:
            _LOGGER.error(
                "Error in refresh workflow for %s (%s): %s",
                self._device.name,
                self._device.appliance_id,
                err,
            )

        finally:
            self._refresh_task_running = False

    async def _send_refresh_command(self) -> None:
        """Send refresh command to device with retry."""
        max_attempts = 3

        for attempt in range(max_attempts):
            try:
                _LOGGER.debug(
                    "Sending refresh command to %s (%s) - attempt %d/%d",
                    self._device.name,
                    self._device.appliance_id,
                    attempt + 1,
                    max_attempts,
                )

                await self._api.set_appliance_command(
                    cast(str, self._device.location_id),
                    cast(str, self._device.room_id),
                    self._device.appliance_id,
                    self._device.type,
                    {"command": {"get_current_measurement": True}},
                )

            except httpx.ReadTimeout as err:
                if attempt + 1 >= max_attempts:
                    _LOGGER.error(
                        "Refresh command failed after %d attempts for %s (%s): %s",
                        max_attempts,
                        self._device.name,
                        self._device.appliance_id,
                        err,
                    )
                    raise

                _LOGGER.debug(
                    "Refresh command timeout for %s (%s) - retry %d/%d: %s",
                    self._device.name,
                    self._device.appliance_id,
                    attempt + 1,
                    max_attempts,
                    err,
                )

            else:
                _LOGGER.debug(
                    "Refresh command sent successfully to %s (%s)",
                    self._device.name,
                    self._device.appliance_id,
                )
                return

    def _extract_timestamp(self, data: dict[str, Any]):
        """Extracts the timestamp from the device data."""
        if not data:
            return None

        wrapped = benedict({"details": data.get("details")})
        ts_raw = wrapped.get(self._key_path_for_timestamp)

        if not isinstance(ts_raw, str):
            return None

        return dt_util.parse_datetime(ts_raw)

    async def get_initial_value(self) -> dict[str, Any]:
        """Get the initial value of the device."""
        return await self._fetch_device_data()

    def set_polling_interval(self, polling: int) -> None:
        """Set the polling interval."""
        self.update_interval = timedelta(seconds=polling)
        self.async_update_listeners()

    def set_log_response_data(self, log_response_data: bool) -> None:
        """Enable/disable response data logging."""
        self._log_response_data = log_response_data

    async def send_command(self, data_to_send: dict[str, Any]) -> dict[str, Any]:
        """Send a command to the device."""
        return await self._api.set_appliance_command(
            cast(str, self._device.location_id),
            cast(str, self._device.room_id),
            self._device.appliance_id,
            self._device.type,
            data_to_send,
        )
