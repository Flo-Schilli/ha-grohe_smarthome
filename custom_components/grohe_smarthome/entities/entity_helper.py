import logging

from grohe import GroheTypes
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.grohe_smarthome.dto.config_dtos import (
    ButtonDto,
    ConfigDto,
    NotificationsDto,
    SensorDto,
)
from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice
from custom_components.grohe_smarthome.entities.entity.binary_sensor import BinarySensor
from custom_components.grohe_smarthome.entities.entity.button import Button
from custom_components.grohe_smarthome.entities.entity.sensor import Sensor
from custom_components.grohe_smarthome.entities.entity.todo import Todo
from custom_components.grohe_smarthome.entities.entity.valve import Valve
from custom_components.grohe_smarthome.entities.interface.coordinator_interface import (
    CoordinatorInterface,
)

_LOGGER = logging.getLogger(__name__)


class EntityHelper:
    def __init__(self, config: ConfigDto, domain: str):
        self._config = config
        self._domain = domain

    @staticmethod
    def is_valid_version(device: GroheDevice, entity: SensorDto | ButtonDto):
        if entity.min_version is not None:
            entity_version = tuple(map(int, entity.min_version.split(".")[:2]))
            return device.stripped_sw_version >= entity_version
        else:
            return True

    @staticmethod
    def get_config_name_by_device_type(device: GroheDevice) -> str:
        config_name: str = ""
        if device.type == GroheTypes.GROHE_SENSE:
            config_name = "GroheSense"
        elif device.type == GroheTypes.GROHE_SENSE_GUARD:
            config_name = "GroheSenseGuard"
        elif device.type == GroheTypes.GROHE_BLUE_HOME:
            config_name = "GroheBlueHome"
        elif device.type == GroheTypes.GROHE_BLUE_PROFESSIONAL:
            config_name = "GroheBlueProf"

        return config_name

    async def add_sensor_entities(
        self,
        coordinator: CoordinatorInterface,
        device: GroheDevice,
        notification_config: NotificationsDto,
    ) -> list[Sensor]:

        config_name = EntityHelper.get_config_name_by_device_type(device)

        entities: list = []
        if config_name:
            initial_value = await coordinator.get_initial_value()
            if self._config.get_device_config(config_name) is not None:
                for sensor in self._config.get_device_config(config_name).sensors:
                    if EntityHelper.is_valid_version(device, sensor):
                        _LOGGER.debug(
                            f"Adding sensor {sensor.name} for device {device.name}"
                        )
                        if isinstance(coordinator, DataUpdateCoordinator):
                            entities.append(
                                Sensor(
                                    self._domain,
                                    coordinator,
                                    device,
                                    sensor,
                                    notification_config,
                                    initial_value,
                                )
                            )
        return entities

    async def add_todo_entities(
        self,
        coordinator: CoordinatorInterface,
        device: GroheDevice,
        notification_config: NotificationsDto,
    ) -> list[Todo]:

        config_name = EntityHelper.get_config_name_by_device_type(device)

        entities: list = []
        if (
            self._config.get_device_config(config_name) is not None
            and self._config.get_device_config(config_name).todos is not None
        ):
            for todo in self._config.get_device_config(config_name).todos:
                _LOGGER.debug(f"Adding todo {todo.name} for device {device.name}")
                if isinstance(coordinator, DataUpdateCoordinator):
                    entities.append(
                        Todo(
                            self._domain, coordinator, device, todo, notification_config
                        )
                    )

        return entities

    async def add_valve_entities(
        self, coordinator: CoordinatorInterface, device: GroheDevice
    ) -> list[Valve]:

        config_name = EntityHelper.get_config_name_by_device_type(device)

        entities: list[Valve] = []
        if (
            config_name
            and self._config.get_device_config(config_name) is not None
            and self._config.get_device_config(config_name).valves is not None
        ):
            for valve in self._config.get_device_config(config_name).valves:
                _LOGGER.debug(f"Adding valve {valve.name} for device {device.name}")
                if isinstance(coordinator, DataUpdateCoordinator):
                    entities.append(Valve(self._domain, coordinator, device, valve))

        return entities

    async def add_button_entities(
        self, coordinator: CoordinatorInterface, device: GroheDevice
    ) -> list[Button]:

        config_name = EntityHelper.get_config_name_by_device_type(device)

        entities: list[Button] = []
        if (
            config_name
            and self._config.get_device_config(config_name) is not None
            and self._config.get_device_config(config_name).buttons is not None
        ):
            for button in self._config.get_device_config(config_name).buttons:
                if EntityHelper.is_valid_version(device, button):
                    _LOGGER.debug(
                        f"Adding button {button.name} for device {device.name}"
                    )
                    if isinstance(coordinator, DataUpdateCoordinator):
                        entities.append(
                            Button(self._domain, coordinator, device, button)
                        )

        return entities

    async def add_binary_sensor_entities(
        self, coordinator: CoordinatorInterface, device: GroheDevice
    ) -> list[BinarySensor]:

        config_name = EntityHelper.get_config_name_by_device_type(device)

        entities: list[BinarySensor] = []
        if (
            config_name
            and self._config.get_device_config(config_name) is not None
            and self._config.get_device_config(config_name).binary_sensors is not None
        ):
            initial_value = await coordinator.get_initial_value()
            for binary_sensor in self._config.get_device_config(
                config_name
            ).binary_sensors:
                if EntityHelper.is_valid_version(device, binary_sensor):
                    _LOGGER.debug(
                        f"Adding binary sensor {binary_sensor.name} for device {device.name}"
                    )
                    if isinstance(coordinator, DataUpdateCoordinator):
                        entities.append(
                            BinarySensor(
                                self._domain,
                                coordinator,
                                device,
                                binary_sensor,
                                initial_value,
                            )
                        )

        return entities
