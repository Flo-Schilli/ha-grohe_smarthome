"""A streak of denied polls logs one warning at the start and one info at the end."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from grohe import GroheForbiddenError

from custom_components.grohe_smarthome.entities.coordinator.blue_prof_coordinator import (
    BlueProfCoordinator,
)
from custom_components.grohe_smarthome.entities.coordinator.deny_streak import (
    DenyStreakLog,
)
from custom_components.grohe_smarthome.entities.coordinator.guard_coordinator import (
    GuardCoordinator,
)
from custom_components.grohe_smarthome.entities.coordinator.profile_coordinator import (
    ProfileCoordinator,
)
from custom_components.grohe_smarthome.entities.coordinator.sense_coordinator import (
    SenseCoordinator,
)

DOMAIN = "grohe_smarthome"
DENY = "User is not authorized to access this resource with an explicit deny"

DETAILS = {
    "installation_date": "2025-01-19T00:00:00+01:00",
    "status": [{"type": "connection", "value": 1}],
    # Blue Professional polls until this timestamp moves; without it every test
    # would sit out the full 10 s measurement timeout.
    "details": {"data_latest_measurement": {"timestamp": "2026-10-25T02:46:00+01:00"}},
}


def _make_device() -> SimpleNamespace:
    return SimpleNamespace(
        appliance_id="appliance-1",
        name="Test Device",
        type="grohe_sense",
        location_id="loc-1",
        room_id="room-1",
        stripped_sw_version=(1, 0),
    )


def _levels(caplog, logger_name: str) -> list[tuple[int, str]]:
    return [
        (record.levelno, record.getMessage())
        for record in caplog.records
        if record.name == logger_name and record.filename == "deny_streak.py"
    ]


def test_streak_logs_warning_then_debug_then_info(caplog):
    logger = logging.getLogger("test.deny_streak")
    streak = DenyStreakLog(logger, "Test Device (appliance-1)")
    caplog.set_level(logging.DEBUG, logger="test.deny_streak")

    streak.accepted()
    streak.denied(GroheForbiddenError(DENY))
    streak.denied(GroheForbiddenError(DENY))
    streak.denied(GroheForbiddenError(DENY))
    streak.accepted()
    streak.accepted()

    assert [level for level, _ in _levels(caplog, "test.deny_streak")] == [
        logging.WARNING,
        logging.DEBUG,
        logging.DEBUG,
        logging.INFO,
    ]


def test_next_streak_warns_again(caplog):
    logger = logging.getLogger("test.deny_streak")
    streak = DenyStreakLog(logger, "Test Device (appliance-1)")
    caplog.set_level(logging.DEBUG, logger="test.deny_streak")

    streak.denied(GroheForbiddenError(DENY))
    streak.accepted()
    streak.denied(GroheForbiddenError(DENY))

    assert [level for level, _ in _levels(caplog, "test.deny_streak")] == [
        logging.WARNING,
        logging.INFO,
        logging.WARNING,
    ]


def _denying_api(deny: dict[str, bool]) -> MagicMock:
    """An API that answers with an explicit deny while deny["now"] is set."""

    async def details(*_args):
        if deny["now"]:
            raise GroheForbiddenError(DENY)
        return DETAILS

    async def notifications(_limit):
        if deny["now"]:
            raise GroheForbiddenError(DENY)
        return []

    api = MagicMock()
    api.access_token = "token"
    api.get_appliance_details = AsyncMock(side_effect=details)
    api.get_appliance_pressure_measurement = AsyncMock(return_value=None)
    api.get_appliance_data = AsyncMock(return_value={"data": {"withdrawals": []}})
    api.set_appliance_command = AsyncMock(return_value=None)
    api.get_profile_notifications = AsyncMock(side_effect=notifications)
    return api


@pytest.mark.parametrize(
    "make_coordinator",
    [
        lambda hass, api: SenseCoordinator(hass, DOMAIN, _make_device(), api),
        lambda hass, api: GuardCoordinator(hass, DOMAIN, _make_device(), api),
        lambda hass, api: BlueProfCoordinator(hass, DOMAIN, _make_device(), api),
        lambda hass, api: ProfileCoordinator(hass, DOMAIN, api),
    ],
    ids=["sense", "guard", "blue_prof", "profile"],
)
async def test_coordinator_logs_deny_streak_once(hass, caplog, make_coordinator):
    deny = {"now": False}
    coordinator = make_coordinator(hass, _denying_api(deny))
    logger_name = type(coordinator).__module__
    caplog.set_level(logging.DEBUG, logger=logger_name)

    coordinator.data = await coordinator._async_update_data()
    deny["now"] = True
    for _ in range(4):
        assert await coordinator._async_update_data() is coordinator.data
    deny["now"] = False
    await coordinator._async_update_data()

    assert [level for level, _ in _levels(caplog, logger_name)] == [
        logging.WARNING,
        logging.DEBUG,
        logging.DEBUG,
        logging.DEBUG,
        logging.INFO,
    ]
