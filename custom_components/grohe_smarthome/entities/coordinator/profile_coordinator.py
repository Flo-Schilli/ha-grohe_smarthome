import asyncio
import logging
from datetime import datetime, timedelta

from grohe import GroheClient, GroheForbiddenError, GroheUnauthorizedError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from custom_components.grohe_smarthome.entities.coordinator.deny_streak import (
    DenyStreakLog,
)
from custom_components.grohe_smarthome.entities.coordinator.relogin import (
    fetch_with_relogin,
)
from custom_components.grohe_smarthome.entities.interface.coordinator_interface import (
    CoordinatorInterface,
)

_LOGGER = logging.getLogger(__name__)


class ProfileCoordinator(DataUpdateCoordinator, CoordinatorInterface):
    def __init__(
        self,
        hass: HomeAssistant,
        domain: str,
        api: GroheClient,
        polling: int = 900,
        log_response_data: bool = False,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Grohe",
            update_interval=timedelta(seconds=polling),
            always_update=True,
        )
        self._api = api
        self._domain = domain

        self._timezone = datetime.now().astimezone().tzinfo
        self._last_update = datetime.now().astimezone().replace(tzinfo=self._timezone)
        self._data: dict[str, any] = {}
        self._log_response_data = log_response_data
        self._initial_value_lock = asyncio.Lock()
        self._deny_streak = DenyStreakLog(_LOGGER, f"domain {domain}")

    async def _get_data(self) -> dict[str, any]:
        api_data = await self._api.get_profile_notifications(50)

        data = {"notifications": api_data}
        self._data = data
        return data

    def get_data(self) -> dict[str, any]:
        return self._data

    async def _async_update_data(self) -> dict:
        try:
            _LOGGER.debug(f"Updating generic profile data for domain {self._domain}")
            data = await fetch_with_relogin(self._api, self._get_data)

            if self._log_response_data:
                _LOGGER.debug(f"Response data for Profile: {data}")

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
            _LOGGER.error("Error updating Profile data: %s", str(e))
            raise UpdateFailed(f"Error updating Profile data: {e}") from e

    async def _async_setup(self) -> None:
        await self._async_update_data()

    async def update_notification(self, notification_id: str, state: bool) -> None:
        await self._api.update_profile_notification_state(notification_id, state)

    async def get_initial_value(self) -> dict[str, any]:
        async with self._initial_value_lock:
            if self.data is None:
                try:
                    self.data = await fetch_with_relogin(self._api, self._get_data)
                except GroheUnauthorizedError as e:
                    raise ConfigEntryAuthFailed(str(e)) from e
                except GroheForbiddenError as e:
                    _LOGGER.warning(
                        "Grohe denied the initial request for domain %s, will retry: %s",
                        self._domain,
                        e,
                    )
                    raise ConfigEntryNotReady(str(e)) from e
                except Exception as e:
                    _LOGGER.error("Error fetching initial Profile data: %s", str(e))
                    raise ConfigEntryNotReady(
                        f"Error fetching initial Profile data: {e}"
                    ) from e
            return self.data

    def set_polling_interval(self, polling: int) -> None:
        self.update_interval = timedelta(seconds=polling)
        self.async_update_listeners()

    def set_log_response_data(self, log_response_data: bool) -> None:
        self._log_response_data = log_response_data
