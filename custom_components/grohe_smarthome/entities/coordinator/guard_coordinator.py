import asyncio
import logging
from datetime import date, datetime, time, timedelta

from benedict import benedict
from grohe import GroheClient, GroheForbiddenError, GroheUnauthorizedError
from grohe.enum.grohe_enum import GroheGroupBy
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from custom_components.grohe_smarthome.dto.config_dtos import DeviceConfigDto
from custom_components.grohe_smarthome.dto.grohe_device import GroheDevice
from custom_components.grohe_smarthome.dto.notification_dto import Notification
from custom_components.grohe_smarthome.entities.coordinator.deny_streak import (
    DenyStreakLog,
)
from custom_components.grohe_smarthome.entities.coordinator.relogin import (
    fetch_with_relogin,
)
from custom_components.grohe_smarthome.entities.coordinator.water_consumption_tracker import (
    WaterConsumptionTracker,
)
from custom_components.grohe_smarthome.entities.interface.coordinator_button_interface import (
    CoordinatorButtonInterface,
)
from custom_components.grohe_smarthome.entities.interface.coordinator_config_interface import (
    CoordinatorConfigInterface,
)
from custom_components.grohe_smarthome.entities.interface.coordinator_interface import (
    CoordinatorInterface,
)
from custom_components.grohe_smarthome.entities.interface.coordinator_valve_interface import (
    CoordinatorValveInterface,
)

_LOGGER = logging.getLogger(__name__)

# Aggregated-data queries over long ranges (a year of history, for the initial fetch of
# the lifetime total) have been observed to exceed the default request timeout. They run
# rarely, so a longer timeout here is cheap.
HISTORICAL_TOTAL_VALUE_TIMEOUT = 30.0


class GuardCoordinator(
    DataUpdateCoordinator,
    CoordinatorInterface,
    CoordinatorValveInterface,
    CoordinatorButtonInterface,
    CoordinatorConfigInterface,
):
    def __init__(
        self,
        hass: HomeAssistant,
        domain: str,
        device: GroheDevice,
        api: GroheClient,
        device_config: DeviceConfigDto | None = None,
        polling: int = 300,
        log_response_data: bool = False,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Grohe Sense",
            update_interval=timedelta(seconds=polling),
            always_update=True,
        )
        self._api = api
        self._domain = domain
        self._device = device
        self._consumption = WaterConsumptionTracker(
            hass, domain, device.appliance_id, self._get_historical_total_value
        )
        self._timezone = datetime.now().astimezone().tzinfo
        self._last_update = datetime.now().astimezone().replace(tzinfo=self._timezone)
        self._notifications: list[Notification] = []
        self._log_response_data = log_response_data
        self._has_pressure_measurement = False
        self._initial_value_lock = asyncio.Lock()
        self._deny_streak = DenyStreakLog(
            _LOGGER, f"{device.name} ({device.appliance_id})"
        )

        if (
            device_config is not None
            and device_config.min_pressure_measurement_version is not None
        ):
            pressure_version = tuple(
                map(int, device_config.min_pressure_measurement_version.split(".")[:2])
            )
            if device.stripped_sw_version >= pressure_version:
                self._has_pressure_measurement = True

    async def _get_total_value(
        self,
        date_from: date,
        date_to: date,
        group_by: GroheGroupBy,
        request_timeout: float | None = None,
    ) -> float:
        """Summed water consumption of the full days from date_from to date_to."""
        _LOGGER.debug(
            f"Getting total values for Grohe Sense Guard with appliance id {self._device.appliance_id}"
        )
        data_in = await self._api.get_appliance_data(
            self._device.location_id,
            self._device.room_id,
            self._device.appliance_id,
            datetime.combine(date_from, time()),
            datetime.combine(date_to, time()),
            group_by,
            True,
            timeout=request_timeout,
        )
        if data_in is None:
            # The grohe library returns None instead of raising for unexpected status
            # codes (e.g. a 504 gateway timeout). That is not "no consumption".
            raise UpdateFailed(
                f"Grohe returned no aggregated data for {self._device.appliance_id}"
            )

        data = benedict(data_in)
        _LOGGER.debug(
            f"Got total values for Grohe Sense Guard for appliance with name {self._device.name}: {data}"
        )

        withdrawals = data.get("data.withdrawals")
        if withdrawals is not None and isinstance(withdrawals, list):
            # Handle None values in waterconsumption
            return sum(val.get("waterconsumption") or 0 for val in withdrawals)

        return 0.0

    async def _get_historical_total_value(
        self, date_from: date, date_to: date, group_by: GroheGroupBy
    ) -> float:
        return await self._get_total_value(
            date_from,
            date_to,
            group_by,
            request_timeout=HISTORICAL_TOTAL_VALUE_TIMEOUT,
        )

    async def _get_total_water_consumption(
        self, api_data: dict[str, any]
    ) -> float | None:
        """Lifetime consumption including today, or the last known value on failure.

        A failure here must only affect the consumption sensors, not the valve and the
        other entities of the Guard, so it is not raised. Auth and rate-limit errors are
        the exception: _async_update_data relogs in, starts reauth or keeps the last
        known data for those.
        """
        today = dt_util.now().date()
        try:
            install_date = datetime.fromisoformat(api_data["installation_date"]).date()
            await self._consumption.async_sync(install_date)
            today_water_consumption = await self._get_total_value(
                today, today, GroheGroupBy.DAY
            )
        except (GroheUnauthorizedError, GroheForbiddenError):
            raise
        except Exception as e:
            last_known = (self.data or {}).get("total_water_consumption")
            # str(e) is empty for some exceptions (e.g. TimeoutError).
            _LOGGER.warning(
                "Could not update the water consumption of %s, keeping %s: %s: %s",
                self._device.appliance_id,
                last_known,
                type(e).__name__,
                e,
            )
            return last_known

        total_till_yesterday = self._consumption.total_until(today - timedelta(days=1))
        total = round(total_till_yesterday + today_water_consumption, 2)

        latest_data = api_data.get("data_latest") or {}
        _LOGGER.debug(
            f"Todays water consumption from appliance data: {today_water_consumption}. Absolute difference to daily_consumption is: {round(abs(today_water_consumption - latest_data.get('daily_consumption', 0)), 2)}"
        )
        _LOGGER.info(
            f"Water consumption for {self._device.appliance_id}: TOTAL TILL YESTERDAY - {total_till_yesterday}l, TOTAL NOW - {total}l, TODAY - {today_water_consumption}l"
        )
        return total

    async def _get_data(self) -> dict[str, any]:
        api_data = await self._api.get_appliance_details(
            self._device.location_id, self._device.room_id, self._device.appliance_id
        )

        pressure: None | dict[str, any] = None

        if self._has_pressure_measurement:
            pressure = await self._api.get_appliance_pressure_measurement(
                self._device.location_id,
                self._device.room_id,
                self._device.appliance_id,
            )

        total_water_consumption = await self._get_total_water_consumption(api_data)

        try:
            status = {val["type"]: val["value"] for val in api_data["status"]}
        except AttributeError as e:
            _LOGGER.debug(f"Status could not be mapped: {e}")
            status = None

        data = {
            "details": api_data,
            "status": status,
            "pressure": pressure,
            "total_water_consumption": total_water_consumption,
        }

        return data

    def _merge_details(self, api_data: dict[str, any] | None, key: str) -> None:
        """
        Merge a single sub-key (e.g. "config" or "command") from a write response into the
        coordinator's cached "details" and push it to every listening entity.

        Valve/Switch/Time/Number read their state straight from `coordinator.data["details"]`
        instead of polling their own endpoint (see `_get_data`, which already pulls the full
        appliance object - including `config` and `command` - out of the dashboard response
        that's fetched for the sensors anyway). After a write, the API's response for that
        write already contains the fresh sub-object, so we patch just that key into the
        cached details and notify listeners - no extra GET needed to see our own change.
        """
        if api_data is None or self.data is None:
            return

        value = api_data.get(key)
        if value is None:
            return

        old_value = (self.data.get("details") or {}).get(key) or {}
        if isinstance(value, dict) and isinstance(old_value, dict):
            changes = {
                field: (old_value.get(field), new)
                for field, new in value.items()
                if old_value.get(field) != new
            }
            if changes:
                changes_str = ", ".join(
                    f"{field}: {old} -> {new}" for field, (old, new) in changes.items()
                )
                _LOGGER.info(
                    "Grohe %s updated via PUT for %s (%s): %s",
                    key,
                    self._device.name,
                    self._device.appliance_id,
                    changes_str,
                )

        details = {**(self.data.get("details") or {}), key: value}
        self.async_set_updated_data({**self.data, "details": details})

    async def set_valve(self, data_to_set: dict[str, any]) -> dict[str, any]:
        api_data = await self._api.set_appliance_command(
            self._device.location_id,
            self._device.room_id,
            self._device.appliance_id,
            self._device.type,
            data_to_set,
        )

        self._merge_details(api_data, "command")

        return api_data

    async def set_config(self, data_to_set: dict[str, any]) -> dict[str, any] | None:
        config = data_to_set.get("config", {})
        api_data = await self._api.set_appliance_config(
            self._device.location_id,
            self._device.room_id,
            self._device.appliance_id,
            config,
        )

        self._merge_details(api_data, "config")

        return api_data

    async def send_command(self, data_to_send: dict[str, any]) -> dict[str, any]:
        api_data = await self._api.set_appliance_command(
            self._device.location_id,
            self._device.room_id,
            self._device.appliance_id,
            self._device.type,
            data_to_send,
        )

        return api_data

    async def _async_update_data(self) -> dict:
        try:
            _LOGGER.debug(
                f"Updating device data for device {self._device.type} with name {self._device.name} (appliance = {self._device.appliance_id})"
            )
            data = await fetch_with_relogin(self._api, self._get_data)

            if self._log_response_data:
                _LOGGER.debug(
                    f"Response data for {self._device.name} (appliance = {self._device.appliance_id}): {data}"
                )

            self._last_update = (
                datetime.now().astimezone().replace(tzinfo=self._timezone)
            )
            self._deny_streak.accepted()
            return data

        except GroheUnauthorizedError as e:
            raise ConfigEntryAuthFailed(str(e)) from e

        except GroheForbiddenError as e:
            self._deny_streak.denied(e)
            if self.data is not None:
                return self.data
            raise UpdateFailed(str(e)) from e

        except Exception as e:
            _LOGGER.error("Error updating Grohe Sense Guard data: %s", str(e))
            raise UpdateFailed(f"Error updating Grohe Sense Guard data: {e}") from e

    async def get_initial_value(self) -> dict[str, any]:
        # HA sets up all platforms (sensor, switch, valve, ...) concurrently, and each one
        # calls this during its own setup - a bare "if self.data is None" check isn't enough
        # to dedupe that, since several callers can all see None before the first one
        # finishes. The lock makes sure only one real fetch happens; the rest just wait for
        # it and reuse the result.
        async with self._initial_value_lock:
            if self.data is None:
                try:
                    self.data = await fetch_with_relogin(self._api, self._get_data)
                except GroheUnauthorizedError as e:
                    raise ConfigEntryAuthFailed(str(e)) from e
                except GroheForbiddenError as e:
                    _LOGGER.warning(
                        "Grohe denied the initial request for %s (%s), will retry: %s",
                        self._device.name,
                        self._device.appliance_id,
                        e,
                    )
                    raise ConfigEntryNotReady(str(e)) from e
                except Exception as e:
                    _LOGGER.error(
                        "Error fetching initial Grohe Sense Guard data: %s", str(e)
                    )
                    raise ConfigEntryNotReady(
                        f"Error fetching initial Grohe Sense Guard data: {e}"
                    ) from e
            return self.data

    async def async_remove_stored_data(self) -> None:
        await self._consumption.async_remove()

    def set_polling_interval(self, polling: int) -> None:
        self.update_interval = timedelta(seconds=polling)
        self.async_update_listeners()

    def set_log_response_data(self, log_response_data: bool) -> None:
        self._log_response_data = log_response_data
