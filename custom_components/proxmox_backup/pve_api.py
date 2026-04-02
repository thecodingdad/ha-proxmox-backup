"""API client for Proxmox VE."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import (
    API_PVE_BACKUP_JOBS,
    API_PVE_NODES,
    API_PVE_VERSION,
    API_PVE_VZDUMP,
)

_LOGGER = logging.getLogger(__name__)


class PVEConnectionError(Exception):
    """Error connecting to Proxmox VE."""


class PVEAuthError(Exception):
    """Authentication error with Proxmox VE."""


class PVEApiClient:
    """API client for Proxmox VE."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        token_id: str,
        token_secret: str,
        verify_ssl: bool,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._base_url = f"https://{host}:{port}"
        self._headers = {
            "Authorization": f"PVEAPIToken={token_id}={token_secret}",
        }
        self._verify_ssl: bool | None = None if verify_ssl else False

    async def _request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> Any:
        """Make an HTTP request to the PVE API."""
        url = f"{self._base_url}{endpoint}"

        try:
            resp = await self._session.request(
                method,
                url,
                headers=self._headers,
                params=params,
                data=data,
                ssl=self._verify_ssl,
            )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise PVEConnectionError(
                f"Cannot connect to PVE at {self._base_url}: {err}"
            ) from err

        if resp.status in (401, 403):
            raise PVEAuthError(
                f"Authentication failed (status {resp.status})"
            )

        if resp.status != 200:
            text = await resp.text()
            raise PVEConnectionError(
                f"Unexpected response from PVE (status {resp.status}): {text}"
            )

        result = await resp.json()
        if result.get("message") and result.get("data") is None:
            raise PVEConnectionError(
                f"PVE API error: {result['message'].strip()}"
            )
        return result.get("data", result)

    async def async_get_version(self) -> dict[str, Any]:
        """Fetch PVE version information."""
        return await self._request(API_PVE_VERSION)

    async def async_get_nodes(self) -> list[dict[str, Any]]:
        """Fetch list of nodes."""
        return await self._request(API_PVE_NODES)

    async def async_get_backup_jobs(self) -> list[dict[str, Any]]:
        """Fetch configured backup jobs."""
        result = await self._request(API_PVE_BACKUP_JOBS)
        return result if isinstance(result, list) else []

    async def async_trigger_backup(
        self, node: str, vmid: str, storage: str
    ) -> str:
        """Trigger a backup for a VM/CT. Returns UPID."""
        endpoint = API_PVE_VZDUMP.format(node=node)
        return await self._request(
            endpoint,
            method="POST",
            data={"vmid": vmid, "storage": storage, "mode": "snapshot"},
        )

    async def async_test_connection(self) -> bool:
        """Test the connection to PVE."""
        await self.async_get_version()
        return True
