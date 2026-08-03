import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from grohe import GroheClient
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers import httpx_client

from .const import CONF_PASSWORD, CONF_USERNAME, DOMAIN
from .options_flow import OptionsFlowHandler

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)


class GroheSenseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def _async_validate_login(self, username: str, password: str) -> str | None:
        """Try to log in to the Grohe backend. Returns an error code, or None on success."""
        client = httpx_client.get_async_client(self.hass)
        client.cookies.clear()
        api = GroheClient(username, password, client)
        try:
            await api.login()
        except Exception as e:
            _LOGGER.debug("Grohe login failed: %s", e)
            return "invalid_auth"
        return None

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            error = await self._async_validate_login(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if error is None:
                await self.async_set_unique_id("GroheSmarthome")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title="Grohe Smarthome", data=user_input)

            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Allow updating the username/password of an existing entry."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            error = await self._async_validate_login(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    reconfigure_entry, data=user_input
                )

            errors["base"] = error

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                DATA_SCHEMA, reconfigure_entry.data
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlowHandler:
        """Create the options flow."""
        return OptionsFlowHandler()
