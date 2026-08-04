from dataclasses import dataclass
from enum import Enum

from dataclasses_json import dataclass_json


#### NOTIFICATION.YAML #################################################################################################
@dataclass_json
@dataclass
class SubCategoryDto:
    id: int
    text: str


@dataclass_json
@dataclass
class NotificationDto:
    category: int
    type: str
    sub_category: list[SubCategoryDto]


@dataclass_json
@dataclass
class NotificationsDto:
    notifications: list[NotificationDto]

    def get_notification(self, category: int, subcategory: int) -> str:
        notify_category = [
            cat for cat in self.notifications if cat.category == category
        ]
        if len(notify_category) == 1:
            notify_cat = notify_category[0]
            notify_sub_cat = [
                cat for cat in notify_cat.sub_category if cat.id == subcategory
            ]
            if len(notify_sub_cat) == 1:
                sub_cat_info = notify_sub_cat[0]
                return sub_cat_info.text
        return f"Unknown Notification {category}/{subcategory}"


#### CONFIG.YAML #######################################################################################################
class ConfigSpecialType(Enum):
    ACCUMULATED_WATER = "Accumulated Water"
    NOTIFICATION = "Notification"
    DURATION_AS_TIMESTAMP = "Duration as Timestamp"
    FILTER_REMAINING_ADJUSTED = "Filter Remaining Adjusted"


@dataclass_json
@dataclass
class SensorDto:
    name: str
    keypath: str
    device_class: str | None = None
    category: str | None = None
    state_class: str | None = None
    unit: str | None = None
    enabled: bool | None = True
    special_type: ConfigSpecialType | None = None
    min_version: str | None = None
    enum: str | None = None
    icon: str | None = None


@dataclass_json
@dataclass
class BinarySensorDto:
    name: str
    keypath: str
    device_class: str | None = None
    category: str | None = None
    enabled: bool | None = True
    min_version: str | None = None


@dataclass_json
@dataclass
class TodoDto:
    name: str
    keypath: str


@dataclass_json
@dataclass
class ValveDto:
    name: str
    keypath: str
    device_class: str | None = None
    features: list[str] | None = None


@dataclass_json
@dataclass
class SwitchDto:
    name: str
    keypath: str
    device_class: str | None = None
    category: str | None = None
    enabled: bool | None = True
    min_version: str | None = None


@dataclass_json
@dataclass
class TimeDto:
    name: str
    keypath: str
    category: str | None = None
    enabled: bool | None = True
    min_version: str | None = None


@dataclass_json
@dataclass
class ButtonCommands:
    keypath: str
    value: bool | str | int


@dataclass_json
@dataclass
class ButtonDto:
    name: str
    commands: list[ButtonCommands]
    min_version: str | None = None


@dataclass_json
@dataclass
class DeviceConfigDto:
    has_pressure_measurements: bool = False
    min_pressure_measurement_version: str | None = None


@dataclass_json
@dataclass
class DeviceDto:
    type: str
    sensors: list[SensorDto]
    device_config: DeviceConfigDto | None = None
    todos: list[TodoDto] | None = None
    valves: list[ValveDto] | None = None
    buttons: list[ButtonDto] | None = None
    binary_sensors: list[BinarySensorDto] | None = None
    switches: list[SwitchDto] | None = None
    times: list[TimeDto] | None = None


@dataclass_json
@dataclass
class DevicesDto:
    device: list[DeviceDto]


@dataclass_json
@dataclass
class ConfigDto:
    devices: DevicesDto

    def get_device_config(self, device_type: str) -> DeviceDto | None:
        """
        Get the configuration for a specific device type.

        :param device_type: The type of device to search for.
        :return: `DeviceDto` if found, otherwise `None`.
        """
        for device in self.devices.device:
            if device.type == device_type:
                return device
        return None
