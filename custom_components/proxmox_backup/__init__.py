"""Proxmox Backup Server integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    PBSApiClient,
    PBSAuthError,
    PBSConnectionError,
    PBSPermissionError,
)
from .const import (
    CONF_PVE_HOST,
    CONF_PVE_PORT,
    CONF_PVE_TOKEN_ID,
    CONF_PVE_TOKEN_SECRET,
    CONF_PVE_VERIFY_SSL,
    CONF_TOKEN_ID,
    CONF_TOKEN_SECRET,
    CONF_VERIFY_SSL,
    DEFAULT_PVE_PORT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import PBSCoordinator
from .pve_api import PVEApiClient, PVEPermissionError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Proxmox Backup Server from a config entry."""
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, False)
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    client = PBSApiClient(
        session=session,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        token_id=entry.data[CONF_TOKEN_ID],
        token_secret=entry.data[CONF_TOKEN_SECRET],
        verify_ssl=verify_ssl,
    )

    try:
        await client.async_test_connection()
    except PBSAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except PBSPermissionError as err:
        raise ConfigEntryNotReady(str(err)) from err
    except PBSConnectionError as err:
        raise ConfigEntryNotReady(
            f"Cannot connect to PBS: {err}"
        ) from err

    # Optional PVE client
    pve_client: PVEApiClient | None = None
    _LOGGER.debug("Config entry data keys: %s", list(entry.data.keys()))
    if entry.data.get(CONF_PVE_HOST):
        pve_verify_ssl = entry.data.get(CONF_PVE_VERIFY_SSL, False)
        pve_session = async_get_clientsession(hass, verify_ssl=pve_verify_ssl)
        pve_client = PVEApiClient(
            session=pve_session,
            host=entry.data[CONF_PVE_HOST],
            port=entry.data.get(CONF_PVE_PORT, DEFAULT_PVE_PORT),
            token_id=entry.data[CONF_PVE_TOKEN_ID],
            token_secret=entry.data[CONF_PVE_TOKEN_SECRET],
            verify_ssl=pve_verify_ssl,
        )
        try:
            await pve_client.async_test_connection()
            await pve_client.async_check_permissions()
            _LOGGER.debug("PVE connection successful")
        except PVEPermissionError as err:
            _LOGGER.warning(
                "PVE features disabled, token lacks permissions: %s", err
            )
            pve_client = None
        except Exception:
            _LOGGER.warning("PVE connection failed, continuing without PVE features", exc_info=True)
            pve_client = None

    coordinator = PBSCoordinator(hass, client, entry, pve_client=pve_client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a PBS config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
