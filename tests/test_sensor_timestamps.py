"""Relative timestamps belong to a device measurement, not its next poll."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.grohe_smarthome.dto.config_dtos import (
    ConfigSpecialType,
    SensorDto,
)
from custom_components.grohe_smarthome.entities.entity.sensor import Sensor


def _sample(timestamp, minutes=30):
    return {
        "details": {
            "data_latest": {
                "measurement": {
                    "timestamp": timestamp,
                    "time_since_last_withdrawal": minutes,
                }
            }
        }
    }


def _sensor(data):
    return Sensor(
        "grohe_smarthome",
        MagicMock(),
        SimpleNamespace(name="Test Blue", appliance_id="test-device"),
        SensorDto(
            name="Time since last withdrawal",
            keypath="details.data_latest.measurement.time_since_last_withdrawal",
            device_class="Timestamp",
            special_type=ConfigSpecialType.DURATION_AS_TIMESTAMP,
        ),
        MagicMock(),
        data,
    )


def test_cached_measurement_keeps_withdrawal_time(freezer):
    """Repeated polls must not move a withdrawal from an old cached sample."""
    sample = _sample("2026-01-01T14:00:00+02:00")
    freezer.move_to("2026-02-01T09:00:00+00:00")
    sensor = _sensor(sample)
    first = sensor.native_value
    freezer.tick(900)
    second = sensor._get_value(sample)

    assert first == datetime.fromisoformat("2026-01-01T11:30:00+00:00")
    assert second == first


def test_new_measurement_updates_relative_timestamp():
    sensor = _sensor(_sample("2026-01-02T12:00:00+00:00", 30))
    # Fifteen minutes later, no new withdrawal: the relative duration grew too.
    assert sensor._get_value(_sample("2026-01-02T12:15:00+00:00", 45)) == (
        datetime.fromisoformat("2026-01-02T11:30:00+00:00")
    )
    # A genuinely new withdrawal has a new sample time and a short duration.
    assert sensor._get_value(_sample("2026-01-02T12:30:00+00:00", 2)) == (
        datetime.fromisoformat("2026-01-02T12:28:00+00:00")
    )


@pytest.mark.parametrize("timestamp", [None, "invalid", "2026-01-02T12:00:00", 123])
def test_missing_or_invalid_sample_time_is_unknown(timestamp):
    """Without a zoned sample time, do not invent a recent withdrawal."""
    assert _sensor(_sample(timestamp)).native_value is None


def test_absolute_timestamp_keeps_existing_behavior():
    sensor = Sensor(
        "grohe_smarthome",
        MagicMock(),
        SimpleNamespace(name="Test Blue", appliance_id="test-device"),
        SensorDto(
            name="Last measurement update",
            keypath="details.data_latest.measurement.timestamp",
            device_class="Timestamp",
        ),
        MagicMock(),
        _sample("2026-01-02T12:00:27+00:00"),
    )
    assert sensor.native_value == datetime.fromisoformat("2026-01-02T12:00:00+00:00")
