"""Binary sensor platform for Proxmox Backup Server."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BACKUP_FRESHNESS_HOURS, DOMAIN
from .coordinator import PBSCoordinator
from .entity import PBSEntity, guest_device_info, server_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PBS binary sensor entities."""
    coordinator: PBSCoordinator = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    entities: list[BinarySensorEntity] = []

    # Global: any backup failed
    device = server_device_info(entry.entry_id, host, port)
    entities.append(PBSBackupFailedSensor(coordinator, device))

    # Per-guest: backup recent + verified
    for guest_key, guest_data in coordinator.data.guests.items():
        device = guest_device_info(
            entry.entry_id,
            guest_data.backup_type,
            guest_data.backup_id,
            guest_data.datastore,
        )
        entities.append(
            PBSBackupRecentSensor(coordinator, guest_key, device)
        )
        entities.append(
            PBSBackupVerifiedSensor(coordinator, guest_key, device)
        )

    async_add_entities(entities)


class PBSBackupFailedSensor(PBSEntity, BinarySensorEntity):
    """Binary sensor for any backup failure in the last 24h."""

    def __init__(
        self,
        coordinator: PBSCoordinator,
        device_info: Any,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, device_info)
        self.entity_description = BinarySensorEntityDescription(
            key="backup_failed",
            translation_key="backup_failed",
            device_class=BinarySensorDeviceClass.PROBLEM,
        )
        self._attr_unique_id = (
            f"{coordinator._entry.entry_id}_global_backup_failed"
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if any backup task failed in the last 24h."""
        return self.coordinator.data.task_summary.failed_tasks_24h > 0


class PBSBackupRecentSensor(PBSEntity, BinarySensorEntity):
    """Binary sensor for backup freshness per guest."""

    def __init__(
        self,
        coordinator: PBSCoordinator,
        guest_key: str,
        device_info: Any,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, device_info)
        self.entity_description = BinarySensorEntityDescription(
            key="backup_recent",
            translation_key="backup_recent",
            icon="mdi:backup-restore",
        )
        self._guest_key = guest_key
        self._attr_unique_id = (
            f"{coordinator._entry.entry_id}_{guest_key.replace('/', '_')}_backup_recent"
        )

    @property
    def available(self) -> bool:
        """Return True if the guest exists in coordinator data."""
        return super().available and self._guest_key in self.coordinator.data.guests

    @property
    def is_on(self) -> bool | None:
        """Return True if backup is recent (within freshness threshold)."""
        guest = self.coordinator.data.guests.get(self._guest_key)
        if guest is None or guest.last_backup_time is None:
            return False
        threshold = datetime.now(tz=timezone.utc) - timedelta(
            hours=BACKUP_FRESHNESS_HOURS
        )
        return guest.last_backup_time > threshold


class PBSBackupVerifiedSensor(PBSEntity, BinarySensorEntity):
    """Binary sensor for backup verification status per guest."""

    def __init__(
        self,
        coordinator: PBSCoordinator,
        guest_key: str,
        device_info: Any,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, device_info)
        self.entity_description = BinarySensorEntityDescription(
            key="backup_verified",
            translation_key="backup_verified",
            icon="mdi:check-decagram",
        )
        self._guest_key = guest_key
        self._attr_unique_id = (
            f"{coordinator._entry.entry_id}_{guest_key.replace('/', '_')}_backup_verified"
        )

    @property
    def available(self) -> bool:
        """Return True if the guest exists in coordinator data."""
        return super().available and self._guest_key in self.coordinator.data.guests

    @property
    def is_on(self) -> bool | None:
        """Return True if last backup is verified."""
        guest = self.coordinator.data.guests.get(self._guest_key)
        if guest is None or guest.verified is None:
            return None
        return guest.verified
