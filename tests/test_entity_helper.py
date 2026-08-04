"""Tests for EntityHelper static logic."""

from types import SimpleNamespace

import pytest
from grohe import GroheTypes

from custom_components.grohe_smarthome.entities.entity_helper import EntityHelper


def _device(device_type, sw_version="2.5.0"):
    return SimpleNamespace(
        type=device_type,
        stripped_sw_version=tuple(map(int, sw_version.split(".")[:2])),
    )


@pytest.mark.parametrize(
    ("device_type", "expected_name"),
    [
        (GroheTypes.GROHE_SENSE, "GroheSense"),
        (GroheTypes.GROHE_SENSE_GUARD, "GroheSenseGuard"),
        (GroheTypes.GROHE_BLUE_HOME, "GroheBlueHome"),
        (GroheTypes.GROHE_BLUE_PROFESSIONAL, "GroheBlueProf"),
    ],
)
def test_get_config_name_by_device_type(device_type, expected_name):
    assert EntityHelper.get_config_name_by_device_type(_device(device_type)) == (
        expected_name
    )


def test_get_config_name_by_device_type_unknown_returns_empty_string():
    device = _device(GroheTypes.GROHE_SENSE_PLUS)
    assert EntityHelper.get_config_name_by_device_type(device) == ""


def test_is_valid_version_true_when_entity_has_no_min_version():
    entity = SimpleNamespace(min_version=None)
    device = _device(GroheTypes.GROHE_SENSE, "2.5.0")
    assert EntityHelper.is_valid_version(device, entity) is True


def test_is_valid_version_true_when_device_meets_minimum():
    entity = SimpleNamespace(min_version="2.0")
    device = _device(GroheTypes.GROHE_SENSE, "2.5.0")
    assert EntityHelper.is_valid_version(device, entity) is True


def test_is_valid_version_false_when_device_below_minimum():
    entity = SimpleNamespace(min_version="3.0")
    device = _device(GroheTypes.GROHE_SENSE, "2.5.0")
    assert EntityHelper.is_valid_version(device, entity) is False
