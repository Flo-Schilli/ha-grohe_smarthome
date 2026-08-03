import logging
from enum import Enum

from homeassistant.components.valve import ValveEntityFeature
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)

from custom_components.grohe_smarthome.enums.grohe_enums import GroheBlueFilterType

_LOGGER = logging.getLogger(__name__)

_UNIT_MAP = {
    "Celsius": UnitOfTemperature.CELSIUS,
    "Percentage": PERCENTAGE,
    "Liters": UnitOfVolume.LITERS,
    "Cubic meters": UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    "Bar": UnitOfPressure.BAR,
    "Minutes": UnitOfTime.MINUTES,
}


class Helper:
    @staticmethod
    def get_ha_units(unit: str) -> str:
        return _UNIT_MAP.get(unit, unit)

    @staticmethod
    def get_valve_features(features: list[str]) -> int:
        parsed_features: list[type[ValveEntityFeature]] = []
        for feature in features:
            try:
                parsed = ValveEntityFeature[feature.upper()]
                parsed_features.append(parsed)
            except ValueError:
                _LOGGER.error(
                    f"Provided feature {feature} is not a valid ValveEntityFeature from HA"
                )

        bit_features = 0
        for parsed_feature in parsed_features:
            bit_features |= parsed_feature.value

        return bit_features

    @staticmethod
    def get_config_enum(enum_name: str) -> type[Enum]:
        if enum_name == "GroheBlueFilterType":
            return GroheBlueFilterType
