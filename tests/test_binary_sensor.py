"""Blue Home maintenance flags and published binary sensor state changes."""

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from grohe import GroheTypes
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grohe_smarthome.entities.config_loader import ConfigLoader
from custom_components.grohe_smarthome.entities.coordinator.blue_home_coordinator import (
    BlueHomeCoordinator,
)

DOMAIN = "grohe_smarthome"
MAINTENANCE_FLAGS = [
    ("co2_20l_reached", "CO2 low", "problem"),
    ("co2_empty", "CO2 empty", "problem"),
    ("filter_20l_reached", "Filter low", "problem"),
    ("filter_empty", "Filter exhausted", "problem"),
    ("cleaning_needed", "Cleaning required", "problem"),
    ("cleaning_mode_active", "Cleaning active", "running"),
    ("flush_confirmation_required", "Flush confirmation required", "problem"),
]


@pytest.fixture
async def blue_home_sensors(hass):
    """Load the shipped YAML through the real helper and register HA entities."""
    device = SimpleNamespace(
        appliance_id="blue-home-test",
        name="Test Blue Home",
        device_name="Grohe Blue Home",
        type=GroheTypes.GROHE_BLUE_HOME,
        sw_version="02.12.Z10.0300.0104",
        stripped_sw_version=(2, 12),
        location_id="test-location",
        room_id="test-room",
        room_name="Kitchen",
    )
    api = MagicMock()
    api.get_appliance_details = AsyncMock(
        return_value={
            "state": {field: False for field, _, _ in MAINTENANCE_FLAGS},
            "status": [
                {"type": "connection", "value": 1},
                {"type": "update_available", "value": 0},
            ],
        }
    )
    coordinator = BlueHomeCoordinator(hass, DOMAIN, device, api)
    # Tests push coordinator data explicitly instead of scheduling real refreshes.
    coordinator.update_interval = None
    config_dir = Path(__file__).parents[1] / "custom_components" / DOMAIN / "config"
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(
        config=ConfigLoader(str(config_dir)).load_config(),
        devices=[device],
        coordinator={device.appliance_id: coordinator},
    )
    component = EntityComponent(logging.getLogger(__name__), "binary_sensor", hass)
    assert await component.async_setup_entry(entry)
    await hass.async_block_till_done()

    entities = list(component.entities)
    assert len(entities) == 9
    api.get_appliance_details.assert_awaited_once()
    api.set_appliance_command.assert_not_called()
    yield coordinator, {entity.name: entity for entity in entities}
    await component.async_unload_entry(entry)


@pytest.mark.parametrize(("field", "name", "device_class"), MAINTENANCE_FLAGS)
async def test_blue_home_maintenance_state_changes(
    hass, blue_home_sensors, field, name, device_class
):
    """Each raw flag updates the actual HA state and preserves unknown values."""
    coordinator, entities = blue_home_sensors
    entity = entities[name]
    assert entity.device_class == device_class
    assert entity.entity_registry_enabled_default is True
    assert hass.states.get(entity.entity_id).state == "off"

    for value, expected in ((True, "on"), (False, "off"), (None, "unknown")):
        coordinator.async_set_updated_data({"details": {"state": {field: value}}})
        assert hass.states.get(entity.entity_id).state == expected

    coordinator.async_set_updated_data({"details": {"state": {field: True}}})
    assert hass.states.get(entity.entity_id).state == "on"
    coordinator.async_set_updated_data({"details": {"state": {}}})
    assert hass.states.get(entity.entity_id).state == "unknown"
    coordinator.async_set_updated_data({"details": {}})
    assert hass.states.get(entity.entity_id).state == "unknown"


@pytest.mark.parametrize(
    ("name", "field"),
    [("Online", "connection"), ("Update available", "update_available")],
)
async def test_existing_binary_sensor_publishes_numeric_status(
    hass, blue_home_sensors, name, field
):
    """Existing integer-valued flags also publish changes and missing values."""
    coordinator, entities = blue_home_sensors
    entity = entities[name]
    for value, expected in ((0, "off"), (1, "on"), (0, "off"), (None, "unknown")):
        coordinator.async_set_updated_data({"status": {field: value}})
        assert hass.states.get(entity.entity_id).state == expected


async def test_binary_sensor_publishes_unavailability_and_recovery(
    hass, blue_home_sensors
):
    """A failed coordinator update must reach HA, even without new measurements."""
    coordinator, entities = blue_home_sensors
    entity = entities["Cleaning required"]
    coordinator.async_set_update_error(UpdateFailed("Test API unavailable"))
    assert hass.states.get(entity.entity_id).state == "unavailable"
    coordinator.async_set_updated_data(
        {"details": {"state": {"cleaning_needed": True}}}
    )
    assert hass.states.get(entity.entity_id).state == "on"
