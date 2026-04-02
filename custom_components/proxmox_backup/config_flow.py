"""Config flow for Proxmox Backup Server integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PBSApiClient, PBSAuthError, PBSConnectionError
from .const import (
    CONF_NODE,
    CONF_PVE_HOST,
    CONF_PVE_PORT,
    CONF_PVE_TOKEN_ID,
    CONF_PVE_TOKEN_SECRET,
    CONF_PVE_VERIFY_SSL,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN_ID,
    CONF_TOKEN_SECRET,
    CONF_VERIFY_SSL,
    DEFAULT_PORT,
    DEFAULT_PVE_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .pve_api import PVEApiClient, PVEAuthError, PVEConnectionError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_TOKEN_ID): str,
        vol.Required(CONF_TOKEN_SECRET): str,
        vol.Required(CONF_VERIFY_SSL, default=False): bool,
        vol.Required(CONF_NODE, default="localhost"): str,
    }
)

STEP_PVE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PVE_HOST): str,
        vol.Optional(CONF_PVE_PORT, default=DEFAULT_PVE_PORT): int,
        vol.Required(CONF_PVE_TOKEN_ID): str,
        vol.Required(CONF_PVE_TOKEN_SECRET): str,
        vol.Optional(CONF_PVE_VERIFY_SSL, default=False): bool,
    }
)


class PBSConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Proxmox Backup Server."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._pbs_data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PBSOptionsFlow:
        """Return the options flow handler."""
        return PBSOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the PBS setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            verify_ssl = user_input[CONF_VERIFY_SSL]

            session = async_get_clientsession(self.hass, verify_ssl=verify_ssl)
            client = PBSApiClient(
                session=session,
                host=host,
                port=port,
                token_id=user_input[CONF_TOKEN_ID],
                token_secret=user_input[CONF_TOKEN_SECRET],
                verify_ssl=verify_ssl,
            )

            try:
                await client.async_test_connection()
            except PBSConnectionError as err:
                _LOGGER.error("Cannot connect to PBS: %s", err)
                errors["base"] = "cannot_connect"
            except PBSAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during PBS setup")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(f"{host}:{port}")
                self._abort_if_unique_id_configured()

                self._pbs_data = user_input
                return await self.async_step_pve()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of PBS connection."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            verify_ssl = user_input[CONF_VERIFY_SSL]

            session = async_get_clientsession(self.hass, verify_ssl=verify_ssl)
            client = PBSApiClient(
                session=session,
                host=host,
                port=port,
                token_id=user_input[CONF_TOKEN_ID],
                token_secret=user_input[CONF_TOKEN_SECRET],
                verify_ssl=verify_ssl,
            )

            try:
                await client.async_test_connection()
            except PBSConnectionError as err:
                _LOGGER.error("Cannot connect to PBS: %s", err)
                errors["base"] = "cannot_connect"
            except PBSAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during PBS reconfigure")
                errors["base"] = "unknown"
            else:
                self._pbs_data = user_input
                return await self.async_step_reconfigure_pve()

        current = entry.data
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=current.get(CONF_HOST, "")): str,
                    vol.Required(CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)): int,
                    vol.Required(CONF_TOKEN_ID, default=current.get(CONF_TOKEN_ID, "")): str,
                    vol.Required(CONF_TOKEN_SECRET, default=current.get(CONF_TOKEN_SECRET, "")): str,
                    vol.Required(CONF_VERIFY_SSL, default=current.get(CONF_VERIFY_SSL, False)): bool,
                    vol.Required(CONF_NODE, default=current.get(CONF_NODE, "localhost")): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure_pve(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of PVE connection."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            if not user_input.get(CONF_PVE_HOST):
                # Remove PVE config
                new_data = {
                    k: v for k, v in self._pbs_data.items()
                    if not k.startswith("pve_")
                }
                return self.async_update_reload_and_abort(
                    entry, data=new_data,
                )

            verify_ssl = user_input.get(CONF_PVE_VERIFY_SSL, False)
            session = async_get_clientsession(self.hass, verify_ssl=verify_ssl)
            client = PVEApiClient(
                session=session,
                host=user_input[CONF_PVE_HOST],
                port=user_input.get(CONF_PVE_PORT, DEFAULT_PVE_PORT),
                token_id=user_input[CONF_PVE_TOKEN_ID],
                token_secret=user_input[CONF_PVE_TOKEN_SECRET],
                verify_ssl=verify_ssl,
            )

            try:
                await client.async_test_connection()
            except PVEConnectionError as err:
                _LOGGER.error("Cannot connect to PVE: %s", err)
                errors["base"] = "pve_cannot_connect"
            except PVEAuthError:
                errors["base"] = "pve_invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during PVE reconfigure")
                errors["base"] = "unknown"
            else:
                merged = {**self._pbs_data, **user_input}
                return self.async_update_reload_and_abort(
                    entry, data=merged,
                )

        current = entry.data
        return self.async_show_form(
            step_id="reconfigure_pve",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PVE_HOST, default=current.get(CONF_PVE_HOST, "")): str,
                    vol.Optional(CONF_PVE_PORT, default=current.get(CONF_PVE_PORT, DEFAULT_PVE_PORT)): int,
                    vol.Optional(CONF_PVE_TOKEN_ID, default=current.get(CONF_PVE_TOKEN_ID, "")): str,
                    vol.Optional(CONF_PVE_TOKEN_SECRET, default=current.get(CONF_PVE_TOKEN_SECRET, "")): str,
                    vol.Optional(CONF_PVE_VERIFY_SSL, default=current.get(CONF_PVE_VERIFY_SSL, False)): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_pve(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the optional PVE setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_PVE_HOST):
                # User skipped PVE config
                return self.async_create_entry(
                    title=f"PBS ({self._pbs_data[CONF_HOST]}:{self._pbs_data[CONF_PORT]})",
                    data=self._pbs_data,
                )

            verify_ssl = user_input.get(CONF_PVE_VERIFY_SSL, False)
            session = async_get_clientsession(self.hass, verify_ssl=verify_ssl)
            client = PVEApiClient(
                session=session,
                host=user_input[CONF_PVE_HOST],
                port=user_input.get(CONF_PVE_PORT, DEFAULT_PVE_PORT),
                token_id=user_input[CONF_PVE_TOKEN_ID],
                token_secret=user_input[CONF_PVE_TOKEN_SECRET],
                verify_ssl=verify_ssl,
            )

            try:
                await client.async_test_connection()
            except PVEConnectionError as err:
                _LOGGER.error("Cannot connect to PVE: %s", err)
                errors["base"] = "pve_cannot_connect"
            except PVEAuthError:
                errors["base"] = "pve_invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during PVE setup")
                errors["base"] = "unknown"
            else:
                merged = {**self._pbs_data, **user_input}
                return self.async_create_entry(
                    title=f"PBS ({self._pbs_data[CONF_HOST]}:{self._pbs_data[CONF_PORT]})",
                    data=merged,
                )

        return self.async_show_form(
            step_id="pve",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PVE_HOST): str,
                    vol.Optional(CONF_PVE_PORT, default=DEFAULT_PVE_PORT): int,
                    vol.Optional(CONF_PVE_TOKEN_ID): str,
                    vol.Optional(CONF_PVE_TOKEN_SECRET): str,
                    vol.Optional(CONF_PVE_VERIFY_SSL, default=False): bool,
                }
            ),
            errors=errors,
        )


class PBSOptionsFlow(OptionsFlow):
    """Handle PBS options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=current,
                    ): vol.All(
                        int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                    ),
                }
            ),
        )
