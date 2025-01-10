import logging
from datetime import timedelta
from typing import List, Dict
from datetime import datetime

from benedict import benedict
from grohe import GroheClient
from grohe.enum.grohe_enum import GroheGroupBy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice
from custom_components.grohe_smarthome.dto.notification_dto import Notification
from custom_components.grohe_smarthome.entities.interface.coordinator_interface import CoordinatorInterface
from custom_components.grohe_smarthome.entities.interface.coordinator_valve_interface import CoordinatorValveInterface

_LOGGER = logging.getLogger(__name__)


class GuardCoordinator(DataUpdateCoordinator, CoordinatorInterface, CoordinatorValveInterface):
    def __init__(self, hass: HomeAssistant, domain: str, device: GroheDevice, api: GroheClient, polling: int = 300) -> None:
        super().__init__(hass, _LOGGER, name='Grohe Sense', update_interval=timedelta(seconds=polling), always_update=True)
        self._api = api
        self._domain = domain
        self._device = device
        self._total_value = 0
        self._total_value_update_day: datetime | None = None
        self._timezone = datetime.now().astimezone().tzinfo
        self._last_update = datetime.now().astimezone().replace(tzinfo=self._timezone)
        self._notifications: List[Notification] = []

    async def _get_total_value(self, date_from: datetime, date_to: datetime, group_by: GroheGroupBy) -> float:
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
        withdrawals = data.get('data.withdrawals')
        if withdrawals is not None and isinstance(withdrawals, list):
            return sum([val.get('waterconsumption') for val in withdrawals])
        else:
            return 0.0

    async def _get_data(self) -> Dict[str, any]:
        api_data = await self._api.get_appliance_details(
            self._device.location_id,
            self._device.room_id,
            self._device.appliance_id)

        pressure = await self._api.get_appliance_pressure_measurement(
            self._device.location_id,
            self._device.room_id,
            self._device.appliance_id
        )

        if (self._total_value_update_day is not None and datetime.now().astimezone().day - self._total_value_update_day.day >= 1) or (self._total_value_update_day is None):
            if self._total_value_update_day is None:
                date_from = datetime.now().astimezone() - timedelta(days=2000)
                date_to = datetime.now().astimezone() - timedelta(days=1)
                group_by = GroheGroupBy.YEAR
            else:
                date_from = self._total_value_update_day
                date_to = self._total_value_update_day
                group_by = GroheGroupBy.DAY

            _LOGGER.debug(f'Old total water consumption: {self._total_value}')
            self._total_value = self._total_value + await self._get_total_value(date_from, date_to, group_by)
            _LOGGER.debug(f'New total water consumption: {self._total_value}')
            self._total_value_update_day = datetime.now().astimezone().replace(tzinfo=self._timezone)


        try:
            status = { val['type']: val['value'] for val in api_data['status'] }
        except AttributeError as e:
            _LOGGER.debug(f'Status could not be mapped: {e}')
            status = None


        data = {'details': api_data, 'status': status, 'pressure': pressure, 'total_water_consumption': self._total_value}

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

    async def _async_update_data(self) -> dict:
        try:
            _LOGGER.debug(f'Updating device data for device {self._device.type} with name {self._device.name} (appliance = {self._device.appliance_id})')
            data = await self._get_data()

            self._last_update = datetime.now().astimezone().replace(tzinfo=self._timezone)
            return data

        except Exception as e:
            _LOGGER.error("Error updating Grohe Sense Guard data: %s", str(e))

    async def get_initial_value(self) -> Dict[str, any]:
        return await self._get_data()

    def set_polling_interval(self, polling: int) -> None:
        self.update_interval = timedelta(seconds=polling)
        self.async_update_listeners()
