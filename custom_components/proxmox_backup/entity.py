"""Base entity for Proxmox Backup Server integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import PBSCoordinator


class PBSEntity(CoordinatorEntity["PBSCoordinator"]):
    """Base entity for Proxmox Backup Server."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PBSCoordinator,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize base entity."""
        super().__init__(coordinator)
        self._attr_device_info = device_info


def server_device_info(
    entry_id: str,
    host: str,
    port: int,
) -> DeviceInfo:
    """Return device info for the PBS server."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_server")},
        name=f"PBS ({host}:{port})",
        manufacturer="Proxmox",
        model="Backup Server",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=f"https://{host}:{port}",
    )


def datastore_device_info(
    entry_id: str,
    store: str,
    host: str,
    port: int,
) -> DeviceInfo:
    """Return device info for a datastore."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_datastore_{store}")},
        name=f"Datastore: {store}",
        manufacturer="Proxmox",
        model="PBS Datastore",
        entry_type=DeviceEntryType.SERVICE,
        via_device=(DOMAIN, f"{entry_id}_server"),
        configuration_url=f"https://{host}:{port}",
    )


def guest_device_info(
    entry_id: str,
    backup_type: str,
    backup_id: str,
    datastore: str,
) -> DeviceInfo:
    """Return device info for a VM/CT backup group."""
    label = "VM" if backup_type == "vm" else "CT"
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_guest_{backup_type}_{backup_id}")},
        name=f"{label} {backup_id} Backups",
        manufacturer="Proxmox",
        model=f"{label} Backup",
        entry_type=DeviceEntryType.SERVICE,
        via_device=(DOMAIN, f"{entry_id}_datastore_{datastore}"),
    )
