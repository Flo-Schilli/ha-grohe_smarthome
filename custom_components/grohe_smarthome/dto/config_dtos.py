from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
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
    sub_category: List[SubCategoryDto]


@dataclass_json
@dataclass
class NotificationsDto:
    notifications: List[NotificationDto]

    def get_notification(self, category: int, subcategory: int) -> str:
        notify_category = [cat for cat in self.notifications if cat.category == category]
        if len(notify_category) == 1:
            notify_cat = notify_category[0]
            notify_sub_cat = [cat for cat in notify_cat.sub_category if cat.id == subcategory]
            if len(notify_sub_cat) == 1:
                sub_cat_info = notify_sub_cat[0]
                return sub_cat_info.text
        return f'Unknown Notification {category}/{subcategory}'


#### CONFIG.YAML #######################################################################################################
class ConfigSpecialType(Enum):
    ACCUMULATED_WATER = 'Accumulated Water'
    NOTIFICATION = 'Notification'
    DURATION_AS_TIMESTAMP = 'Duration as Timestamp'

@dataclass_json
@dataclass
class SensorDto:
    name: str
    keypath: str
    device_class: Optional[str] = None
    category: Optional[str] = None
    state_class: Optional[str] = None
    unit: Optional[str] = None
    enabled: Optional[bool] = True
    special_type: Optional[ConfigSpecialType] = None
    min_version: Optional[str] = None
    enum: Optional[str] = None

@dataclass_json
@dataclass
class BinarySensorDto:
    name: str
    keypath: str
    device_class: Optional[str] = None
    category: Optional[str] = None
    enabled: Optional[bool] = True
    min_version: Optional[str] = None

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
    device_class: Optional[str] = None
    features: Optional[List[str]] = None

@dataclass_json
@dataclass
class ButtonCommands:
    keypath: str
    value: bool | str | int

@dataclass_json
@dataclass
class ButtonDto:
    name: str
    commands: List[ButtonCommands]
    min_version: Optional[str] = None

@dataclass_json
@dataclass
class DeviceConfigDto:
    has_pressure_measurements: bool = False
    min_pressure_measurement_version: Optional[str] = None
    
@dataclass_json
@dataclass
class DeviceDto:
    type: str
    sensors: List[SensorDto]
    device_config: Optional[DeviceConfigDto] = None
    todos: Optional[List[TodoDto]] = None
    valves: Optional[List[ValveDto]] = None
    buttons: Optional[List[ButtonDto]] = None
    binary_sensors: Optional[List[BinarySensorDto]] = None

@dataclass_json
@dataclass
class DevicesDto:
    device: List[DeviceDto]

@dataclass_json
@dataclass
class ConfigDto:
    devices: DevicesDto
    
    def get_device_config(self, device_type: str) -> Optional[DeviceDto]:
        """
        Get the configuration for a specific device type.

        :param device_type: The type of device to search for.
        :return: `DeviceDto` if found, otherwise `None`.
        """
        for device in self.devices.device:
            if device.type == device_type:
                return device
        return None