"""Tests for the Grohe SmartHome config flow."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grohe_smarthome.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)

GROHE_CLIENT_PATH = "custom_components.grohe_smarthome.config_flow.GroheClient"


def _mock_grohe_client(login_side_effect=None):
    client = AsyncMock()
    if login_side_effect is not None:
        client.login.side_effect = login_side_effect
    return client


async def test_user_step_success_creates_entry(hass):
    with patch(GROHE_CLIENT_PATH, return_value=_mock_grohe_client()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Grohe Smarthome"
    assert result["data"] == {
        CONF_USERNAME: "user@example.com",
        CONF_PASSWORD: "secret",
    }


async def test_user_step_invalid_credentials_shows_error(hass):
    with patch(
        GROHE_CLIENT_PATH,
        return_value=_mock_grohe_client(login_side_effect=RuntimeError("nope")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "wrong"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_step_aborts_on_duplicate_entry(hass):
    with patch(GROHE_CLIENT_PATH, return_value=_mock_grohe_client()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY

        result2 = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_USERNAME: "user2@example.com", CONF_PASSWORD: "secret2"},
        )

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_reauth_step_updates_existing_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="GroheSmarthome",
        data={CONF_USERNAME: "old@example.com", CONF_PASSWORD: "old-pass"},
    )
    entry.add_to_hass(hass)

    with patch(GROHE_CLIENT_PATH, return_value=_mock_grohe_client()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "new@example.com", CONF_PASSWORD: "new-pass"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {
        CONF_USERNAME: "new@example.com",
        CONF_PASSWORD: "new-pass",
    }


async def test_reauth_step_invalid_credentials_keeps_old_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="GroheSmarthome",
        data={CONF_USERNAME: "old@example.com", CONF_PASSWORD: "old-pass"},
    )
    entry.add_to_hass(hass)

    with patch(
        GROHE_CLIENT_PATH,
        return_value=_mock_grohe_client(login_side_effect=RuntimeError("nope")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "new@example.com", CONF_PASSWORD: "wrong"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data == {CONF_USERNAME: "old@example.com", CONF_PASSWORD: "old-pass"}


async def test_reconfigure_step_updates_existing_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="GroheSmarthome",
        data={CONF_USERNAME: "old@example.com", CONF_PASSWORD: "old-pass"},
    )
    entry.add_to_hass(hass)

    with patch(GROHE_CLIENT_PATH, return_value=_mock_grohe_client()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reconfigure"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "new@example.com", CONF_PASSWORD: "new-pass"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {
        CONF_USERNAME: "new@example.com",
        CONF_PASSWORD: "new-pass",
    }


async def test_reconfigure_step_invalid_credentials_keeps_old_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="GroheSmarthome",
        data={CONF_USERNAME: "old@example.com", CONF_PASSWORD: "old-pass"},
    )
    entry.add_to_hass(hass)

    with patch(
        GROHE_CLIENT_PATH,
        return_value=_mock_grohe_client(login_side_effect=RuntimeError("nope")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "new@example.com", CONF_PASSWORD: "wrong"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data == {CONF_USERNAME: "old@example.com", CONF_PASSWORD: "old-pass"}
