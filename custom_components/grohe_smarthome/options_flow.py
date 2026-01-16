from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult, section
import voluptuous as vol
from homeassistant.helpers import config_validation


class OptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return FlowResult(self.async_create_entry(data=user_input))

        show_form = self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(
                            "polling", "Set a custom polling interval in seconds.", 300
                        ): vol.All(
                            config_validation.positive_int,
                            vol.Range(
                                min=40, msg="Polling must be at least 40 seconds."
                            ),
                        ),
                        vol.Required("logging_options"): section(
                            vol.Schema(
                                {
                                    vol.Required(
                                        "log_response_data",
                                        "Define if response data shall be logged as well",
                                        False,
                                    ): bool,
                                }
                            ),
                        ),
                        vol.Required("network_options"): section(
                            vol.Schema(
                                {
                                    vol.Required(
                                        "request_timeout",
                                        "Set a custom request timeout in seconds (for httpx).",
                                        10,
                                    ): config_validation.positive_int,
                                    vol.Required(
                                        "connect_timeout",
                                        "Set a custom connect timeout in seconds (for httpx).",
                                        5,
                                    ): config_validation.positive_int,
                                }
                            ),
                        ),
                    }
                ),
                self.config_entry.options,
            ),
        )

        return FlowResult(show_form)
