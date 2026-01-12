import asyncio
import logging
from datetime import timedelta, time
from typing import List, Dict
from datetime import datetime

import httpx
from benedict import benedict
from grohe import GroheClient
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice
from custom_components.grohe_smarthome.dto.notification_dto import Notification
from custom_components.grohe_smarthome.entities.interface.coordinator_button_interface import CoordinatorButtonInterface
from custom_components.grohe_smarthome.entities.interface.coordinator_interface import CoordinatorInterface

_LOGGER = logging.getLogger(__name__)


class BlueHomeCoordinator(DataUpdateCoordinator, CoordinatorInterface, CoordinatorButtonInterface):
    def __init__(self, hass: HomeAssistant, domain: str, device: GroheDevice, api: GroheClient, polling: int = 300, log_response_data: bool = False) -> None:
        super().__init__(hass, _LOGGER, name='Grohe Sense', update_interval=timedelta(seconds=polling), always_update=True)
        self._api = api
        self._domain = domain
        self._device = device
        self._timezone = datetime.now().astimezone().tzinfo
        self._last_update = datetime.now().astimezone().replace(tzinfo=self._timezone)
        self._notifications: List[Notification] = []
        self._log_response_data = log_response_data

        self._key_path_for_timestamp = 'details.data_latest.measurement.timestamp'
        self._last_measurement_timestamp: datetime | None = None
        self._last_measurement_updated: bool = False
        self._update_timeout = 15
        self._local_update_interval = 5

    # This is being called by the binary_sensor and sensor functions
    async def _get_data(self) -> Dict[str, any]:
        self._last_measurement_updated = False

        _LOGGER.debug(
            f'Sending command to device {self._device.type} with name {self._device.name} (appliance = {self._device.appliance_id})')
        # Before each call, get the new current measurement
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                await self._api.set_appliance_command(
                    self._device.location_id,
                    self._device.room_id,
                    self._device.appliance_id,
                    self._device.type,
                    {'command': {'get_current_measurement': True}})
                break
            except httpx.ReadTimeout as e:
                _LOGGER.info(f'Command to device {self._device.type} with name {self._device.name} (appliance = {self._device.appliance_id}) timed out: {e} (retry {attempt + 1}/3)')
                if attempt + 1 >= max_attempts:
                    raise e

        command_send_at: datetime = datetime.now().astimezone()

        _LOGGER.debug(
            f'Command send successfully to device {self._device.type} with name {self._device.name} (appliance = {self._device.appliance_id}) at {command_send_at}')

        while datetime.now().astimezone() - command_send_at < timedelta(seconds=self._update_timeout):
            _LOGGER.debug(
                f'Waiting for new data to receive on device {self._device.type} with name {self._device.name} (appliance = {self._device.appliance_id})')

            await asyncio.sleep(self._local_update_interval)

            api_data = await self._api.get_appliance_details(
                self._device.location_id,
                self._device.room_id,
                self._device.appliance_id)

            _LOGGER.debug(
                f'Data received on device {self._device.type} with name {self._device.name} (appliance = {self._device.appliance_id})')

            data = benedict({ 'details': api_data })
            if data.get(self._key_path_for_timestamp) is not None:
                data_set_timestamp: datetime = datetime.fromisoformat(data.get(self._key_path_for_timestamp)).astimezone()

                if self._last_measurement_timestamp is None or data_set_timestamp > self._last_measurement_timestamp:
                    _LOGGER.debug(
                        f'Last measurement timestamp updated on device {self._device.type} with name {self._device.name} (appliance = {self._device.appliance_id})')

                    self._last_measurement_timestamp = data_set_timestamp
                    self._last_measurement_updated = True
                    break
                else:
                    _LOGGER.debug(
                        f'No new measurement found for device {self._device.type} with name {self._device.name}. Last measurement timestamp: {self._last_measurement_timestamp} returned timestamp: {data_set_timestamp}. Should be timestamp after {command_send_at}')


        if not self._last_measurement_updated:
            _LOGGER.warning(f'No new measurement found for device {self._device.type} with name {self._device.name} (appliance = {self._device.appliance_id}) after {self._update_timeout} seconds.')


        try:
            status = { val['type']: val['value'] for val in api_data['status'] }
        except AttributeError as e:
            _LOGGER.debug(f'Status could not be mapped: {e}')
            status = None

        data = {'details': api_data, 'status': status}
        return data

    async def _async_update_data(self) -> dict:
        try:
            _LOGGER.debug(f'Updating device data for device {self._device.type} with name {self._device.name} (appliance = {self._device.appliance_id})')
            data = await self._get_data()

            if self._log_response_data:
                _LOGGER.debug(f'Response data for {self._device.name} (appliance = {self._device.appliance_id}): {data}')

            self._last_update = datetime.now().astimezone().replace(tzinfo=self._timezone)
            return data

        except Exception as e:
            _LOGGER.error("Error updating Grohe Blue Home data: %s", str(e))

    async def get_initial_value(self) -> Dict[str, any]:
        return await self._get_data()

    def set_polling_interval(self, polling: int) -> None:
        self.update_interval = timedelta(seconds=polling)
        self.async_update_listeners()

    def set_log_response_data(self, log_response_data: bool) -> None:
        self._log_response_data = log_response_data

    async def send_command(self, data_to_send: Dict[str, any]) -> Dict[str, any]:
        api_data = await self._api.set_appliance_command(
            self._device.location_id,
            self._device.room_id,
            self._device.appliance_id,
            self._device.type, data_to_send)

        return api_data