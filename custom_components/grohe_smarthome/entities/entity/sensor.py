import logging
from datetime import datetime, timedelta
from typing import Dict

from benedict import benedict
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from ..helper import Helper
from ...dto.grohe_device import GroheDevice
from ...dto.config_dtos import SensorDto, NotificationsDto, ConfigSpecialType

_LOGGER = logging.getLogger(__name__)
DATETIME_DIFF_SECONDS = 60

class Sensor(CoordinatorEntity, SensorEntity):
    def __init__(self, domain: str, coordinator: DataUpdateCoordinator, device: GroheDevice, sensor: SensorDto,
                 notification_config: NotificationsDto, initial_value: Dict[str, any] = None):
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._device = device
        self._notification_config = notification_config
        self._sensor = sensor
        self._domain = domain
        self._value: float | str | int | dict[str, any] | datetime | None = self._get_value(initial_value)
        self._old_datetime_value: datetime | None = None

        # If value is a datetime, set the old_datetime_value to the same as value
        if isinstance(self._value, datetime):
            self._old_datetime_value = self._value

        # Needed for Sensor Entity
        self._attr_name = f'{self._device.name} {self._sensor.name}'
        self._attr_has_entity_name = False

        self._attr_entity_registry_enabled_default = self._sensor.enabled

        if self._sensor.device_class is not None:
            self._attr_device_class = SensorDeviceClass(self._sensor.device_class.lower())

            if self._attr_device_class == SensorDeviceClass.ENUM and self._sensor.enum is not None:
                self._attr_options = [e.name for e in Helper.get_config_enum(self._sensor.enum)]

        if self._sensor.unit is not None:
            self._attr_native_unit_of_measurement = Helper.get_ha_units(self._sensor.unit)

        if self._sensor.category is not None:
            self._attr_entity_category = EntityCategory(self._sensor.category.lower())

        if self._sensor.state_class is not None:
            self._attr_state_class = SensorStateClass(self._sensor.state_class.lower().replace(" ", "_"))

    @property
    def device_info(self) -> DeviceInfo | None:
        return DeviceInfo(identifiers={(self._domain, self._device.appliance_id)},
                          name=self._device.name,
                          manufacturer='Grohe',
                          model=self._device.device_name,
                          sw_version=self._device.sw_version,
                          suggested_area=self._device.room_name)

    @property
    def unique_id(self):
        return f'{self._device.appliance_id}_{self._sensor.name.lower().replace(" ", "_")}'

    @property
    def native_value(self):
        return self._value

    def _get_value(self, full_data: Dict[str, any]) -> float | int | str | dict[str, any] | datetime | None:
        if self._sensor.keypath is not None:
            # We do have some data here, so let's extract it
            data = benedict(full_data)
            value: float | int | str | dict[str, any] | datetime | None = None
            try:
                value = data.get(self._sensor.keypath)

            except KeyError:
                _LOGGER.error(f'Device: {self._device.name} ({self._device.appliance_id}) with sensor: {self._sensor.name} has no value on keypath: {self._sensor.keypath}')

            if self._sensor.device_class is not None and self._sensor.device_class == 'Timestamp' and value is not None:
                if self._sensor.special_type is not None and self._sensor.special_type == ConfigSpecialType.DURATION_AS_TIMESTAMP:
                    value = datetime.now().astimezone() - timedelta(minutes=value)
                else:
                    value = datetime.fromisoformat(value)

                _LOGGER.debug(f'New timestamp value for {self._sensor.name} is: {value}. Old one was {self._old_datetime_value} and the difference is: {(value - self._old_datetime_value).total_seconds()} seconds.')

                if self._old_datetime_value is not None and abs((value - self._old_datetime_value).total_seconds()) <= DATETIME_DIFF_SECONDS:
                    _LOGGER.debug(f'Timestamp value {self._sensor.name} is the same as the old one, so we will not update it: {value}')
                    value = self._old_datetime_value
                else:
                    self._old_datetime_value = value

                # Only show minutes and not seconds
                value = value.replace(second=0, microsecond=0)

            if self._sensor.device_class is not None and self._sensor.device_class == 'Enum' and value is not None:
                if self._sensor.enum is not None:
                    value = Helper.get_config_enum(self._sensor.enum)(value).name

            if self._sensor.special_type is not None:
                if self._sensor.special_type == ConfigSpecialType.NOTIFICATION and value is not None and isinstance(value, dict):
                    value = self._notification_config.get_notification(value.get('category'), value.get('type'))
                elif self._sensor.special_type == ConfigSpecialType.NOTIFICATION and value is None:
                    value = 'No actual notification'
                elif self._sensor.special_type == ConfigSpecialType.ACCUMULATED_WATER and value is not None:
                    value = value + data.get('total_water_consumption')

            return value

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._coordinator is not None and self._coordinator.data is not None and self._sensor.keypath is not None:
            # We do have some data here, so let's extract it
            value = self._get_value(self._coordinator.data)
            _LOGGER.debug(
                f'Device: {self._device.name} ({self._device.appliance_id}) with sensor name: "{self._sensor.name}" has the following value on keypath "{self._sensor.keypath}": {value}')

            self._value = value
            self.async_write_ha_state()
