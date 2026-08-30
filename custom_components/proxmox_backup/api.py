"""API client for Proxmox Backup Server."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import (
    API_DATASTORE_GC,
    API_DATASTORE_LIST,
    API_DATASTORE_PRUNE,
    API_DATASTORE_SNAPSHOTS,
    API_DATASTORE_USAGE,
    API_DATASTORE_VERIFY,
    API_NODE_TASKS,
    API_VERSION,
    PRIV_DATASTORE_AUDIT,
    PRIV_DATASTORE_MODIFY,
    PRIV_DATASTORE_PRUNE,
    PRIV_DATASTORE_VERIFY,
    PRIV_SYS_AUDIT,
)

_LOGGER = logging.getLogger(__name__)


class PBSConnectionError(Exception):
    """Error connecting to Proxmox Backup Server."""


class PBSAuthError(Exception):
    """Invalid API token (HTTP 401)."""


class PBSPermissionError(Exception):
    """Token is valid but lacks the required privileges (HTTP 403)."""

    def __init__(self, endpoint: str, permission: str) -> None:
        """Initialize with the denied endpoint and the missing permission."""
        super().__init__(
            f"Token lacks permission for {endpoint} "
            f"(status 403, requires {permission})"
        )
        self.endpoint = endpoint
        self.permission = permission


class PBSApiClient:
    """API client for Proxmox Backup Server."""

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
            "Authorization": f"PBSAPIToken={token_id}:{token_secret}",
        }
        self._verify_ssl: bool | None = None if verify_ssl else False

    async def _request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        permission: str = "the required privilege",
    ) -> Any:
        """Make an HTTP request to the PBS API."""
        url = f"{self._base_url}{endpoint}"

        try:
            resp = await self._session.request(
                method,
                url,
                headers=self._headers,
                params=params,
                json=json_data,
                ssl=self._verify_ssl,
            )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise PBSConnectionError(
                f"Cannot connect to PBS at {self._base_url}: {err}"
            ) from err

        if resp.status == 401:
            raise PBSAuthError(
                f"Invalid API token (status 401) while calling {endpoint}"
            )

        if resp.status == 403:
            raise PBSPermissionError(endpoint, permission)

        if resp.status != 200:
            text = await resp.text()
            raise PBSConnectionError(
                f"Unexpected response from PBS (status {resp.status}): {text}"
            )

        result = await resp.json()
        return result.get("data", result)

    async def async_get_version(self) -> dict[str, Any]:
        """Fetch PBS version information."""
        return await self._request(API_VERSION)

    async def async_get_datastores(self) -> list[dict[str, Any]]:
        """Fetch list of datastores."""
        return await self._request(
            API_DATASTORE_LIST, permission=PRIV_DATASTORE_AUDIT
        )

    async def async_get_datastore_usage(self) -> list[dict[str, Any]]:
        """Fetch datastore usage statistics."""
        return await self._request(
            API_DATASTORE_USAGE, permission=PRIV_DATASTORE_AUDIT
        )

    async def async_get_snapshots(self, store: str) -> list[dict[str, Any]]:
        """Fetch snapshots for a datastore."""
        endpoint = API_DATASTORE_SNAPSHOTS.format(store=store)
        return await self._request(endpoint, permission=PRIV_DATASTORE_AUDIT)

    async def async_get_tasks(
        self, node: str, since: int, type_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch tasks for a node since a given epoch timestamp."""
        endpoint = API_NODE_TASKS.format(node=node)
        params: dict[str, Any] = {"since": since, "limit": 500}
        if type_filter:
            params["typefilter"] = type_filter
        return await self._request(
            endpoint, params=params, permission=PRIV_SYS_AUDIT
        )

    async def async_start_verify(
        self,
        store: str,
        backup_type: str | None = None,
        backup_id: str | None = None,
    ) -> str:
        """Start a verify job on a datastore. Returns UPID.

        Optionally filter by backup-type and backup-id to verify a single guest.
        """
        endpoint = API_DATASTORE_VERIFY.format(store=store)
        json_data: dict[str, Any] = {}
        if backup_type:
            json_data["backup-type"] = backup_type
        if backup_id:
            json_data["backup-id"] = backup_id
        return await self._request(
            endpoint,
            method="POST",
            json_data=json_data,
            permission=PRIV_DATASTORE_VERIFY.format(store=store),
        )

    async def async_start_gc(self, store: str) -> str:
        """Start garbage collection on a datastore. Returns UPID."""
        endpoint = API_DATASTORE_GC.format(store=store)
        return await self._request(
            endpoint,
            method="POST",
            permission=PRIV_DATASTORE_MODIFY.format(store=store),
        )

    async def async_start_prune(self, store: str) -> str:
        """Start a prune job on a datastore. Returns UPID."""
        endpoint = API_DATASTORE_PRUNE.format(store=store)
        return await self._request(
            endpoint,
            method="POST",
            json_data={},
            permission=PRIV_DATASTORE_PRUNE.format(store=store),
        )

    async def async_test_connection(self) -> bool:
        """Test the connection to PBS.

        Only checks that host, port and token are usable — /version needs no
        privileges, so a token without any ACL passes this check.
        """
        await self.async_get_version()
        return True

    async def async_check_permissions(self, node: str) -> None:
        """Verify the token holds the privileges the coordinator needs.

        Raises PBSPermissionError for the first endpoint that is denied, so
        a misconfigured ACL fails during setup instead of on the first refresh.
        """
        await self.async_get_datastore_usage()
        await self._request(
            API_NODE_TASKS.format(node=node),
            params={"limit": 1},
            permission=PRIV_SYS_AUDIT,
        )
