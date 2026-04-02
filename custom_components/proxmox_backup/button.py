"""Button platform for Proxmox Backup Server."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PBSCoordinator
from .entity import PBSEntity, datastore_device_info, guest_device_info

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class PBSButtonDescription(ButtonEntityDescription):
    """Describes a PBS button entity."""


DATASTORE_BUTTON_DESCRIPTIONS: tuple[PBSButtonDescription, ...] = (
    PBSButtonDescription(
        key="verify",
        translation_key="verify",
        icon="mdi:check-decagram",
    ),
    PBSButtonDescription(
        key="garbage_collection",
        translation_key="garbage_collection",
        icon="mdi:delete-sweep",
    ),
    PBSButtonDescription(
        key="prune",
        translation_key="prune",
        icon="mdi:content-cut",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PBS button entities."""
    coordinator: PBSCoordinator = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    entities: list[ButtonEntity] = []

    # Datastore maintenance buttons
    for store in coordinator.data.datastores:
        device = datastore_device_info(entry.entry_id, store, host, port)
        for description in DATASTORE_BUTTON_DESCRIPTIONS:
            entities.append(
                PBSMaintenanceButton(coordinator, description, store, device)
            )

    # Guest buttons
    for guest_key, guest_data in coordinator.data.guests.items():
        device = guest_device_info(
            entry.entry_id,
            guest_data.backup_type,
            guest_data.backup_id,
            guest_data.datastore,
        )
        # Verify button (always available via PBS)
        entities.append(
            PBSVerifyGuestButton(coordinator, guest_key, device)
        )
        # Trigger backup button (only if PVE is configured)
        if coordinator.pve_client:
            entities.append(
                PBSTriggerBackupButton(coordinator, guest_key, device)
            )

    async_add_entities(entities)


class PBSMaintenanceButton(PBSEntity, ButtonEntity):
    """Button for datastore maintenance tasks."""

    entity_description: PBSButtonDescription

    TASK_MAP = {
        "verify": "async_start_verify",
        "garbage_collection": "async_start_gc",
        "prune": "async_start_prune",
    }

    def __init__(
        self,
        coordinator: PBSCoordinator,
        description: PBSButtonDescription,
        store: str,
        device_info: Any,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, device_info)
        self.entity_description = description
        self._store = store
        self._attr_unique_id = (
            f"{coordinator._entry.entry_id}_{store}_{description.key}"
        )

    @property
    def available(self) -> bool:
        """Return True if the datastore exists in coordinator data."""
        return super().available and self._store in self.coordinator.data.datastores

    async def async_press(self) -> None:
        """Execute the maintenance task."""
        method_name = self.TASK_MAP.get(self.entity_description.key)
        if method_name is not None:
            method = getattr(self.coordinator.client, method_name)
            await method(self._store)
            await self.coordinator.async_request_refresh()


class PBSVerifyGuestButton(PBSEntity, ButtonEntity):
    """Button to verify backups for a specific guest."""

    def __init__(
        self,
        coordinator: PBSCoordinator,
        guest_key: str,
        device_info: Any,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, device_info)
        self.entity_description = PBSButtonDescription(
            key="verify_guest",
            translation_key="verify_guest",
            icon="mdi:check-decagram",
        )
        self._guest_key = guest_key
        self._attr_unique_id = (
            f"{coordinator._entry.entry_id}_{guest_key.replace('/', '_')}_verify_guest"
        )

    @property
    def available(self) -> bool:
        """Return True if the guest exists in coordinator data."""
        return super().available and self._guest_key in self.coordinator.data.guests

    async def async_press(self) -> None:
        """Start verify for this guest."""
        guest = self.coordinator.data.guests.get(self._guest_key)
        if guest is None:
            return
        await self.coordinator.client.async_start_verify(
            store=guest.datastore,
            backup_type=guest.backup_type,
            backup_id=guest.backup_id,
        )
        await self.coordinator.async_request_refresh()


class PBSTriggerBackupButton(PBSEntity, ButtonEntity):
    """Button to trigger a backup via PVE."""

    def __init__(
        self,
        coordinator: PBSCoordinator,
        guest_key: str,
        device_info: Any,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, device_info)
        self.entity_description = PBSButtonDescription(
            key="trigger_backup",
            translation_key="trigger_backup",
            icon="mdi:play",
        )
        self._guest_key = guest_key
        self._attr_unique_id = (
            f"{coordinator._entry.entry_id}_{guest_key.replace('/', '_')}_trigger_backup"
        )

    @property
    def available(self) -> bool:
        """Return True if the guest exists and PVE is connected."""
        if not super().available:
            return False
        guest = self.coordinator.data.guests.get(self._guest_key)
        return (
            guest is not None
            and self.coordinator.pve_client is not None
            and guest.pve_node is not None
            and guest.pve_storage is not None
        )

    async def async_press(self) -> None:
        """Trigger a backup via PVE."""
        guest = self.coordinator.data.guests.get(self._guest_key)
        if guest is None or self.coordinator.pve_client is None:
            return
        await self.coordinator.pve_client.async_trigger_backup(
            node=guest.pve_node,
            vmid=guest.backup_id,
            storage=guest.pve_storage,
        )
        await self.coordinator.async_request_refresh()
