"""Tests for the Helper utility class."""

import pytest
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)

from custom_components.grohe_smarthome.entities.helper import Helper


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        ("Celsius", UnitOfTemperature.CELSIUS),
        ("Percentage", PERCENTAGE),
        ("Liters", UnitOfVolume.LITERS),
        ("Cubic meters", UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR),
        ("Bar", UnitOfPressure.BAR),
        ("Minutes", UnitOfTime.MINUTES),
    ],
)
def test_get_ha_units_known_unit(unit, expected):
    assert Helper.get_ha_units(unit) == expected


def test_get_ha_units_unknown_unit_passthrough():
    assert Helper.get_ha_units("Foobar") == "Foobar"
