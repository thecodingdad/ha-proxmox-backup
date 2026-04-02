"""Data update coordinator for Proxmox Backup Server."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PBSApiClient, PBSAuthError, PBSConnectionError
from .const import (
    CONF_NODE,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    TASK_TYPE_GC,
    TASK_TYPE_PRUNE,
    TASK_TYPE_PRUNE_JOB,
    TASK_TYPE_VERIFY_GROUP,
    TASK_TYPE_VERIFY_JOB,
    TASK_TYPE_VERIFY_SNAPSHOT,
)
from .pve_api import PVEApiClient

_LOGGER = logging.getLogger(__name__)


@dataclass
class PBSMaintenanceTaskData:
    """Data for a maintenance task (verify, gc, prune)."""

    last_run_time: datetime | None = None
    last_status: str | None = None
    last_duration: float | None = None


@dataclass
class PBSDatastoreData:
    """Data for a single datastore."""

    store: str
    total_bytes: int = 0
    used_bytes: int = 0
    available_bytes: int = 0
    usage_percent: float = 0.0
    snapshot_count: int = 0
    verify: PBSMaintenanceTaskData = field(default_factory=PBSMaintenanceTaskData)
    gc: PBSMaintenanceTaskData = field(default_factory=PBSMaintenanceTaskData)
    prune: PBSMaintenanceTaskData = field(default_factory=PBSMaintenanceTaskData)


@dataclass
class PBSBackupGuestData:
    """Data for a single VM/CT backup group."""

    backup_type: str
    backup_id: str
    datastore: str
    last_backup_time: datetime | None = None
    last_backup_duration: float | None = None
    last_backup_size: int = 0
    snapshot_count: int = 0
    verified: bool | None = None
    verify_time: datetime | None = None
    next_backup_time: datetime | None = None
    pve_node: str | None = None
    pve_storage: str | None = None


@dataclass
class PBSTaskSummary:
    """Aggregated task data."""

    total_tasks_24h: int = 0
    failed_tasks_24h: int = 0
    guest_last_status: dict[str, str] = field(default_factory=dict)
    guest_last_duration: dict[str, float] = field(default_factory=dict)


@dataclass
class PBSData:
    """Aggregated data from Proxmox Backup Server."""

    datastores: dict[str, PBSDatastoreData] = field(default_factory=dict)
    guests: dict[str, PBSBackupGuestData] = field(default_factory=dict)
    task_summary: PBSTaskSummary = field(default_factory=PBSTaskSummary)
    pve_connected: bool = False


class PBSCoordinator(DataUpdateCoordinator[PBSData]):
    """Coordinator for polling Proxmox Backup Server."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: PBSApiClient,
        entry: ConfigEntry,
        pve_client: PVEApiClient | None = None,
    ) -> None:
        """Initialize the coordinator."""
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.pve_client = pve_client
        self._entry = entry
        self._node = entry.data.get(CONF_NODE, "localhost")

    async def _async_update_data(self) -> PBSData:
        """Fetch data from Proxmox Backup Server."""
        since = int((datetime.now(tz=timezone.utc) - timedelta(hours=24)).timestamp())

        try:
            usage_list, task_list = await asyncio.gather(
                self.client.async_get_datastore_usage(),
                self.client.async_get_tasks(self._node, since=since),
            )
        except PBSAuthError as err:
            raise ConfigEntryAuthFailed from err
        except PBSConnectionError as err:
            raise UpdateFailed(f"Cannot connect to PBS: {err}") from err

        data = PBSData()

        # Parse datastore usage
        for ds in usage_list:
            store = ds.get("store", "")
            total = ds.get("total", 0)
            used = ds.get("used", 0)
            avail = ds.get("avail", 0)
            data.datastores[store] = PBSDatastoreData(
                store=store,
                total_bytes=total,
                used_bytes=used,
                available_bytes=avail,
                usage_percent=round((used / total) * 100, 1) if total > 0 else 0.0,
            )

        # Parse task summary
        self._parse_tasks(task_list, data)

        # Fetch snapshots per datastore (must run before maintenance parsing
        # because per-guest verify status needs guests to exist)
        await self._fetch_snapshots(data)

        # Parse maintenance task history
        self._parse_maintenance_tasks(task_list, data)

        # Fetch PVE backup schedules if configured
        if self.pve_client:
            data.pve_connected = True
            await self._fetch_pve_backup_jobs(data)

        return data

    def _parse_tasks(
        self, task_list: list[dict[str, Any]], data: PBSData
    ) -> None:
        """Parse tasks to extract summary and per-guest backup status."""
        backup_tasks = [t for t in task_list if t.get("worker_type") == "backup"]
        data.task_summary.total_tasks_24h = len(backup_tasks)
        data.task_summary.failed_tasks_24h = sum(
            1 for t in backup_tasks if t.get("status") != "OK"
        )

        # Extract per-guest last backup status from tasks
        # worker_id format: "datastore:backup_type/backup_id:timestamp"
        seen_guests: set[str] = set()
        # Sort by starttime descending to find latest per guest
        backup_tasks.sort(key=lambda t: t.get("starttime", 0), reverse=True)

        for task in backup_tasks:
            worker_id = task.get("worker_id", "")
            parts = worker_id.split(":")
            if len(parts) < 2:
                continue

            guest_key = parts[1]  # e.g. "vm/100"
            if guest_key in seen_guests:
                continue
            seen_guests.add(guest_key)

            status = task.get("status", "")
            data.task_summary.guest_last_status[guest_key] = (
                "OK" if status == "OK" else "error"
            )

            starttime = task.get("starttime", 0)
            endtime = task.get("endtime", 0)
            if starttime and endtime:
                data.task_summary.guest_last_duration[guest_key] = (
                    float(endtime - starttime)
                )

    def _parse_maintenance_tasks(
        self, task_list: list[dict[str, Any]], data: PBSData
    ) -> None:
        """Parse maintenance tasks (verify, gc, prune) per datastore."""
        # Datastore-level maintenance tasks (worker_id = datastore name)
        datastore_type_map = {
            TASK_TYPE_VERIFY_JOB: "verify",
            TASK_TYPE_GC: "gc",
            TASK_TYPE_PRUNE_JOB: "prune",
        }

        # Per-guest verify tasks:
        #   verify_group: worker_id = "datastore:/vm/100"
        #   verify:       worker_id = "datastore::vm/100"
        guest_verify_types = {
            TASK_TYPE_VERIFY_GROUP,
            TASK_TYPE_VERIFY_SNAPSHOT,
        }

        all_types = set(datastore_type_map.keys()) | guest_verify_types
        maintenance_tasks = [
            t for t in task_list if t.get("worker_type") in all_types
        ]
        maintenance_tasks.sort(
            key=lambda t: t.get("starttime", 0), reverse=True
        )

        seen_datastore: set[tuple[str, str]] = set()
        seen_guest_verify: set[str] = set()

        for task in maintenance_tasks:
            worker_type = task.get("worker_type", "")
            worker_id = task.get("worker_id", "")
            starttime = task.get("starttime", 0)
            endtime = task.get("endtime", 0)
            status = task.get("status", "")

            # Datastore-level tasks: worker_id is just the datastore name
            if worker_type in datastore_type_map:
                attr_name = datastore_type_map[worker_type]
                store = worker_id

                key = (store, attr_name)
                if key in seen_datastore or store not in data.datastores:
                    continue
                seen_datastore.add(key)

                task_data = PBSMaintenanceTaskData(
                    last_run_time=(
                        datetime.fromtimestamp(endtime or starttime, tz=timezone.utc)
                        if starttime
                        else None
                    ),
                    last_status="OK" if status == "OK" else (status or "unknown"),
                    last_duration=(
                        float(endtime - starttime) if starttime and endtime else None
                    ),
                )
                setattr(data.datastores[store], attr_name, task_data)

            # Per-guest verify tasks
            if worker_type in guest_verify_types:
                guest_key = _extract_guest_key(worker_id)
                if not guest_key or guest_key in seen_guest_verify:
                    continue
                seen_guest_verify.add(guest_key)

                if guest_key in data.guests:
                    data.guests[guest_key].verified = status == "OK"
                    data.guests[guest_key].verify_time = (
                        datetime.fromtimestamp(endtime or starttime, tz=timezone.utc)
                        if starttime
                        else None
                    )

    async def _fetch_snapshots(self, data: PBSData) -> None:
        """Fetch snapshots for all datastores and build guest data."""
        if not data.datastores:
            return

        try:
            tasks = {
                store: self.client.async_get_snapshots(store)
                for store in data.datastores
            }
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)

            for store, result in zip(tasks.keys(), results):
                if isinstance(result, Exception):
                    _LOGGER.debug(
                        "Failed to get snapshots for datastore %s: %s", store, result
                    )
                    continue

                snapshot_count = 0
                guests: dict[str, list[dict[str, Any]]] = {}

                for snap in result:
                    snapshot_count += 1
                    backup_type = snap.get("backup-type", "")
                    backup_id = snap.get("backup-id", "")
                    guest_key = f"{backup_type}/{backup_id}"

                    if guest_key not in guests:
                        guests[guest_key] = []
                    guests[guest_key].append(snap)

                data.datastores[store].snapshot_count = snapshot_count

                for guest_key, snaps in guests.items():
                    # Sort by backup-time descending
                    snaps.sort(key=lambda s: s.get("backup-time", 0), reverse=True)
                    latest = snaps[0]

                    backup_type, backup_id = guest_key.split("/", 1)
                    backup_time = latest.get("backup-time", 0)

                    data.guests[guest_key] = PBSBackupGuestData(
                        backup_type=backup_type,
                        backup_id=backup_id,
                        datastore=store,
                        last_backup_time=(
                            datetime.fromtimestamp(backup_time, tz=timezone.utc)
                            if backup_time
                            else None
                        ),
                        last_backup_size=latest.get("size", 0),
                        snapshot_count=len(snaps),
                    )

        except Exception:
            _LOGGER.debug("Failed to fetch snapshots", exc_info=True)

    async def _fetch_pve_backup_jobs(self, data: PBSData) -> None:
        """Fetch PVE backup job schedules and map to guests."""
        try:
            jobs = await self.pve_client.async_get_backup_jobs()
            nodes = await self.pve_client.async_get_nodes()
        except Exception as err:
            _LOGGER.warning("Failed to fetch PVE backup jobs: %s", err)
            return

        _LOGGER.debug(
            "PVE data: %d nodes, %d jobs, %d guests",
            len(nodes), len(jobs), len(data.guests),
        )

        # Find first online node name for vzdump
        pve_node: str | None = None
        for node in nodes:
            if node.get("status") == "online":
                pve_node = node.get("node")
                break

        # Collect all known guest backup_ids for "all" jobs
        all_guest_ids = [g.backup_id for g in data.guests.values()]

        for job in jobs:
            if not job.get("enabled", True):
                continue

            storage = job.get("storage", "")
            schedule = job.get("schedule", "")
            next_run = _parse_schedule_next_run(schedule) if schedule else None

            # Determine which VMIDs this job covers
            # PVE jobs can have "all": 1 (backup all), or "vmid": "100,101"
            vmid_str = job.get("vmid", "")
            is_all = bool(job.get("all", 0))

            if is_all:
                target_ids = all_guest_ids
            elif vmid_str:
                target_ids = [v.strip() for v in str(vmid_str).split(",")]
            else:
                # No vmid and not "all" — skip
                continue

            for vmid in target_ids:
                for guest_key, guest_data in data.guests.items():
                    if guest_data.backup_id == vmid:
                        guest_data.next_backup_time = next_run
                        guest_data.pve_node = pve_node
                        guest_data.pve_storage = storage
                        break


def _extract_guest_key(worker_id: str) -> str | None:
    """Extract guest key (e.g. 'vm/100') from a PBS task worker_id.

    Known formats:
      verify_group: "backup:/vm/100"  (colon-slash)
      verify:       "backup::vm/100"  (double-colon)
      prune:        "backup::vm/100"  (double-colon)
    """
    # Try "datastore:/type/id" format (verify_group)
    if ":/" in worker_id:
        _, guest_path = worker_id.split(":/", 1)
        # guest_path = "vm/100" — strip leading slash if present
        return guest_path.lstrip("/")

    # Try "datastore::type/id" format (verify, prune)
    if "::" in worker_id:
        _, guest_part = worker_id.split("::", 1)
        return guest_part

    return None


def _parse_schedule_next_run(schedule: str, tz_info: Any = None) -> datetime | None:
    """Parse a PVE systemd calendar schedule and return the next run time.

    PVE schedules are in the server's local time.
    We use HA's configured timezone to interpret them.
    """
    import homeassistant.util.dt as dt_util

    now_local = dt_util.now()

    # Handle simple presets
    if schedule == "daily" or schedule == "*-*-* 00:00:00":
        tomorrow = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow += timedelta(days=1)
        return tomorrow

    if schedule == "hourly":
        next_hour = now_local.replace(minute=0, second=0, microsecond=0)
        next_hour += timedelta(hours=1)
        return next_hour

    # Parse "*-*-* HH:MM:SS" or "*-*-* HH:MM" format
    try:
        parts = schedule.split(" ")
        time_part = parts[-1] if len(parts) >= 2 else parts[0]
        time_components = time_part.split(":")
        hour = int(time_components[0])
        minute = int(time_components[1]) if len(time_components) > 1 else 0

        next_run = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now_local:
            next_run += timedelta(days=1)
        return next_run
    except (ValueError, IndexError):
        _LOGGER.debug("Cannot parse PVE schedule: %s", schedule)
        return None
