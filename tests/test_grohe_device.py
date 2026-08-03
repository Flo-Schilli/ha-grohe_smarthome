"""Tests for GroheDevice.get_devices() dashboard parsing."""

from unittest.mock import AsyncMock, MagicMock

from grohe import GroheTypes

from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice


def _dashboard(appliances: list[dict]) -> dict:
    return {
        "locations": [
            {
                "id": "loc-1",
                "rooms": [
                    {
                        "id": "room-1",
                        "name": "Kitchen",
                        "appliances": appliances,
                    }
                ],
            }
        ]
    }


async def test_get_devices_parses_registered_appliance():
    api = MagicMock()
    api.get_dashboard = AsyncMock(
        return_value=_dashboard(
            [
                {
                    "appliance_id": "app-1",
                    "type": GroheTypes.GROHE_SENSE.value,
                    "name": "Sense 1",
                    "version": "1.2.3",
                    "registration_complete": True,
                }
            ]
        )
    )

    devices = await GroheDevice.get_devices(api)

    assert len(devices) == 1
    assert devices[0].appliance_id == "app-1"
    assert devices[0].type == GroheTypes.GROHE_SENSE
    assert devices[0].stripped_sw_version == (1, 2)


async def test_get_devices_skips_unregistered_appliance():
    api = MagicMock()
    api.get_dashboard = AsyncMock(
        return_value=_dashboard(
            [
                {
                    "appliance_id": "app-1",
                    "type": GroheTypes.GROHE_SENSE.value,
                    "name": "Sense 1",
                    "registration_complete": False,
                }
            ]
        )
    )

    devices = await GroheDevice.get_devices(api)

    assert devices == []


async def test_get_devices_skips_unknown_device_type():
    api = MagicMock()
    api.get_dashboard = AsyncMock(
        return_value=_dashboard(
            [
                {
                    "appliance_id": "app-1",
                    "type": 999,
                    "name": "Mystery device",
                    "registration_complete": True,
                }
            ]
        )
    )

    devices = await GroheDevice.get_devices(api)

    assert devices == []


async def test_get_devices_skips_broken_appliance_but_keeps_others(monkeypatch):
    """Regression: a single appliance that fails to parse must not abort discovery
    of the remaining ones (the except block used to only catch ValueError, which
    nothing in this path could actually raise)."""
    api = MagicMock()
    api.get_dashboard = AsyncMock(
        return_value=_dashboard(
            [
                {
                    "appliance_id": "broken",
                    "type": GroheTypes.GROHE_SENSE.value,
                    "name": "Broken Sense",
                    "registration_complete": True,
                },
                {
                    "appliance_id": "healthy",
                    "type": GroheTypes.GROHE_SENSE.value,
                    "name": "Healthy Sense",
                    "registration_complete": True,
                },
            ]
        )
    )

    original_is_valid = GroheDevice.is_valid_device_type

    def is_valid_device_type(self):
        if self.appliance_id == "broken":
            raise RuntimeError("boom")
        return original_is_valid(self)

    monkeypatch.setattr(GroheDevice, "is_valid_device_type", is_valid_device_type)

    devices = await GroheDevice.get_devices(api)

    assert [device.appliance_id for device in devices] == ["healthy"]
