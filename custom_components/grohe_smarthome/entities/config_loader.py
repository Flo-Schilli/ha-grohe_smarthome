import os

import yaml

from custom_components.grohe_smarthome.dto.config_dtos import (
    ConfigDto,
    NotificationsDto,
)


class ConfigLoader:
    notification_name = "notifications.yaml"
    config_name = "config.yaml"

    def __init__(self, path: str):
        self.path = path

    def load_notifications(self) -> NotificationsDto:
        with open(os.path.join(self.path, self.notification_name)) as file:
            yaml_data = yaml.safe_load(file)
            return NotificationsDto.from_dict(yaml_data)

    def load_config(self) -> ConfigDto:
        with open(os.path.join(self.path, self.config_name)) as file:
            yaml_data = yaml.safe_load(file)
            return ConfigDto.from_dict(yaml_data)
