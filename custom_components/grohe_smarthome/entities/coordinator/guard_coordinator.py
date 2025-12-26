import logging
from datetime import timedelta
from typing import List, Dict
from datetime import datetime

from benedict import benedict
from grohe import GroheClient
from grohe.enum.grohe_enum import GroheGroupBy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.grohe_smarthome.dto.config_dtos import DeviceConfigDto
from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice
from custom_components.grohe_smarthome.dto.notification_dto import Notification
from custom_components.grohe_smarthome.entities.interface.coordinator_button_interface import CoordinatorButtonInterface
from custom_components.grohe_smarthome.entities.interface.coordinator_interface import CoordinatorInterface
from custom_components.grohe_smarthome.entities.interface.coordinator_valve_interface import CoordinatorValveInterface

_LOGGER = logging.getLogger(__name__)


class GuardCoordinator(DataUpdateCoordinator, CoordinatorInterface, CoordinatorValveInterface, CoordinatorButtonInterface):
    def __init__(self, hass: HomeAssistant, domain: str, device: GroheDevice, api: GroheClient, device_config: DeviceConfigDto | None = None, polling: int = 300, log_response_data: bool = False) -> None:
        super().__init__(hass, _LOGGER, name='Grohe Sense', update_interval=timedelta(seconds=polling), always_update=True)
        self._api = api
        self._domain = domain
        self._device = device
        self._total_value = 0
        self._total_value_update_day: datetime | None = None
        self._timezone = datetime.now().astimezone().tzinfo
        self._last_update = datetime.now().astimezone().replace(tzinfo=self._timezone)
        self._notifications: List[Notification] = []
        self._log_response_data = log_response_data
        self._has_pressure_measurement = False

        if device_config is not None and device_config.min_pressure_measurement_version is not None:
            pressure_version = tuple(map(int, device_config.min_pressure_measurement_version.split('.')[:2]))
            if device.stripped_sw_version >= pressure_version:
                self._has_pressure_measurement = True

    async def _get_total_value(self, date_from: datetime, date_to: datetime, group_by: GroheGroupBy) -> float:
        try:
            _LOGGER.debug(f'Getting total values for Grohe Sense Guard with appliance id {self._device.appliance_id}')
            data_in = await self._api.get_appliance_data(
                            self._device.location_id,
                            self._device.room_id,
                            self._device.appliance_id,
                            date_from,
                            date_to,
                            group_by,
                            True)

            data = benedict(data_in)
            _LOGGER.debug(f'Got total values for Grohe Sense Guard for appliance with name {self._device.name}: {data}')

            withdrawals = data.get('data.withdrawals')
            if withdrawals is not None and isinstance(withdrawals, list):
                # Handle None values in waterconsumption
                return sum([val.get('waterconsumption', 0) for val in withdrawals])

            else:
                return 0.0

        except Exception as e:
            _LOGGER.error(f"Failed to get total values: {e}")
            return 0.0

    async def _get_data(self) -> Dict[str, any]:
        api_data = await self._api.get_appliance_details(
            self._device.location_id,
            self._device.room_id,
            self._device.appliance_id)

        pressure: None | Dict[str, any]  = None

        if self._has_pressure_measurement:
            pressure = await self._api.get_appliance_pressure_measurement(
                self._device.location_id,
                self._device.room_id,
                self._device.appliance_id
            )

        today_water_consumption = await self._get_total_value(datetime.now().astimezone(), datetime.now().astimezone(),
                                                              GroheGroupBy.DAY)
        if (self._total_value_update_day is not None and datetime.now().astimezone().day - self._total_value_update_day.day >= 1) or (self._total_value_update_day is None):
            install_date = datetime.fromisoformat(api_data['installation_date'])
            date_from = install_date
            date_to = datetime.now().astimezone()
            group_by = GroheGroupBy.YEAR

            _LOGGER.debug(f'Old total water consumption: {self._total_value}')
            self._total_value = max(round(await self._get_total_value(date_from, date_to, group_by), 2) - today_water_consumption, 0)
            _LOGGER.debug(f'New total water consumption: {self._total_value}')
            self._total_value_update_day = datetime.now().astimezone().replace(tzinfo=self._timezone)

        latest_data = api_data.get('data_latest') or {}
        _LOGGER.debug(f'Todays water consumption from appliance data: {today_water_consumption}. Absolute difference to daily_consumption is: {round(abs(today_water_consumption - latest_data.get('daily_consumption', 0)), 2)}')
        _LOGGER.info(f'Water consumption for {self._device.appliance_id}: TOTAL TILL YESTERDAY - {round(self._total_value, 2)}l, TOTAL NOW - {round(self._total_value + today_water_consumption, 2)}l, TODAY - {today_water_consumption}l')

        try:
            status = { val['type']: val['value'] for val in api_data['status'] }
        except AttributeError as e:
            _LOGGER.debug(f'Status could not be mapped: {e}')
            status = None


        data = {'details': api_data, 'status': status, 'pressure': pressure, 'total_water_consumption': self._total_value + today_water_consumption}

        return data

    async def get_valve_value(self) -> Dict[str, any]:
        api_data = await self._api.get_appliance_command(
            self._device.location_id,
            self._device.room_id,
            self._device.appliance_id)

        return api_data

    async def set_valve(self, data_to_set: Dict[str, any]) -> Dict[str, any]:
        api_data = await self._api.set_appliance_command(
            self._device.location_id,
            self._device.room_id,
            self._device.appliance_id,
            self._device.type, data_to_set)

        return api_data

    async def send_command(self, data_to_send: Dict[str, any]) -> Dict[str, any]:
        api_data = await self._api.set_appliance_command(
            self._device.location_id,
            self._device.room_id,
            self._device.appliance_id,
            self._device.type, data_to_send)

        return api_data

    async def _async_update_data(self) -> dict:
        try:
            _LOGGER.debug(f'Updating device data for device {self._device.type} with name {self._device.name} (appliance = {self._device.appliance_id})')
            data = await self._get_data()

            if self._log_response_data:
                _LOGGER.debug(f'Response data for {self._device.name} (appliance = {self._device.appliance_id}): {data}')

            self._last_update = datetime.now().astimezone().replace(tzinfo=self._timezone)
            return data

        except Exception as e:
            _LOGGER.error("Error updating Grohe Sense Guard data: %s", str(e))

    async def get_initial_value(self) -> Dict[str, any]:
        return await self._get_data()

    def set_polling_interval(self, polling: int) -> None:
        self.update_interval = timedelta(seconds=polling)
        self.async_update_listeners()

    def set_log_response_data(self, log_response_data: bool) -> None:
        self._log_response_data = log_response_data
