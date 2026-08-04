"""Regression tests for has_entity_name behavior across entity types."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.grohe_smarthome.dto.config_dtos import (
    BinarySensorDto,
    ButtonDto,
    SensorDto,
    TodoDto,
    ValveDto,
)
from custom_components.grohe_smarthome.entities.entity.binary_sensor import (
    BinarySensor,
)
from custom_components.grohe_smarthome.entities.entity.button import Button
from custom_components.grohe_smarthome.entities.entity.sensor import Sensor
from custom_components.grohe_smarthome.entities.entity.todo import Todo
from custom_components.grohe_smarthome.entities.entity.valve import Valve


def _device() -> SimpleNamespace:
    return SimpleNamespace(
        name="Kitchen Sink Guard",
        appliance_id="app-1",
        device_name="Sense Guard",
        sw_version="1.2.3",
        room_name="Kitchen",
    )


def test_sensor_entity_uses_has_entity_name():
    entity = Sensor(
        "grohe_smarthome",
        MagicMock(),
        _device(),
        SensorDto(name="Pressure", keypath="details.pressure"),
        MagicMock(),
        {},
    )

    assert entity.has_entity_name is True
    assert entity.name == "Pressure"


def test_binary_sensor_entity_uses_has_entity_name():
    entity = BinarySensor(
        "grohe_smarthome",
        MagicMock(),
        _device(),
        BinarySensorDto(name="Leak Detected", keypath="details.leak"),
        {},
    )

    assert entity.has_entity_name is True
    assert entity.name == "Leak Detected"


def test_button_entity_uses_has_entity_name():
    entity = Button(
        "grohe_smarthome",
        MagicMock(),
        _device(),
        ButtonDto(name="Refresh", commands=[]),
    )

    assert entity.has_entity_name is True
    assert entity.name == "Refresh"


def test_valve_entity_uses_has_entity_name():
    entity = Valve(
        "grohe_smarthome",
        MagicMock(),
        _device(),
        ValveDto(name="Main Valve", keypath="details.valve"),
    )

    assert entity.has_entity_name is True
    assert entity.name == "Main Valve"


def test_todo_entity_uses_has_entity_name():
    entity = Todo(
        "grohe_smarthome",
        MagicMock(),
        _device(),
        TodoDto(name="Notifications", keypath="details.notifications"),
        MagicMock(),
    )

    assert entity.has_entity_name is True
    assert entity.name == "Notifications"
