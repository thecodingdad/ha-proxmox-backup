"""Sensor platform for Proxmox Backup Server."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, UnitOfInformation, UnitOfTime, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import (
    PBSBackupGuestData,
    PBSCoordinator,
    PBSData,
    PBSDatastoreData,
    PBSMaintenanceTaskData,
)
from .entity import (
    PBSEntity,
    datastore_device_info,
    guest_device_info,
    server_device_info,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class PBSDatastoreSensorDescription(SensorEntityDescription):
    """Describes a PBS datastore sensor entity."""

    value_fn: Callable[[PBSDatastoreData], Any]


@dataclass(frozen=True, kw_only=True)
class PBSGuestSensorDescription(SensorEntityDescription):
    """Describes a PBS guest sensor entity."""

    value_fn: Callable[[PBSBackupGuestData, PBSData], Any]


@dataclass(frozen=True, kw_only=True)
class PBSGlobalSensorDescription(SensorEntityDescription):
    """Describes a PBS global sensor entity."""

    value_fn: Callable[[PBSData], Any]


@dataclass(frozen=True, kw_only=True)
class PBSMaintenanceSensorDescription(SensorEntityDescription):
    """Describes a PBS maintenance task sensor entity."""

    task_attr: str
    value_fn: Callable[[PBSMaintenanceTaskData], Any]


MAINTENANCE_SENSOR_DESCRIPTIONS: tuple[PBSMaintenanceSensorDescription, ...] = (
    # Verify
    PBSMaintenanceSensorDescription(
        key="verify_last_run",
        translation_key="verify_last_run",
        icon="mdi:check-decagram",
        device_class=SensorDeviceClass.TIMESTAMP,
        task_attr="verify",
        value_fn=lambda t: t.last_run_time,
    ),
    PBSMaintenanceSensorDescription(
        key="verify_last_status",
        translation_key="verify_last_status",
        icon="mdi:check-decagram",
        device_class=SensorDeviceClass.ENUM,
        options=["OK", "error", "unknown"],
        task_attr="verify",
        value_fn=lambda t: t.last_status,
    ),
    PBSMaintenanceSensorDescription(
        key="verify_last_duration",
        translation_key="verify_last_duration",
        icon="mdi:timer-outline",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        task_attr="verify",
        value_fn=lambda t: t.last_duration,
    ),
    # Garbage Collection
    PBSMaintenanceSensorDescription(
        key="gc_last_run",
        translation_key="gc_last_run",
        icon="mdi:delete-sweep",
        device_class=SensorDeviceClass.TIMESTAMP,
        task_attr="gc",
        value_fn=lambda t: t.last_run_time,
    ),
    PBSMaintenanceSensorDescription(
        key="gc_last_status",
        translation_key="gc_last_status",
        icon="mdi:delete-sweep",
        device_class=SensorDeviceClass.ENUM,
        options=["OK", "error", "unknown"],
        task_attr="gc",
        value_fn=lambda t: t.last_status,
    ),
    PBSMaintenanceSensorDescription(
        key="gc_last_duration",
        translation_key="gc_last_duration",
        icon="mdi:timer-outline",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        task_attr="gc",
        value_fn=lambda t: t.last_duration,
    ),
    # Prune
    PBSMaintenanceSensorDescription(
        key="prune_last_run",
        translation_key="prune_last_run",
        icon="mdi:content-cut",
        device_class=SensorDeviceClass.TIMESTAMP,
        task_attr="prune",
        value_fn=lambda t: t.last_run_time,
    ),
    PBSMaintenanceSensorDescription(
        key="prune_last_status",
        translation_key="prune_last_status",
        icon="mdi:content-cut",
        device_class=SensorDeviceClass.ENUM,
        options=["OK", "error", "unknown"],
        task_attr="prune",
        value_fn=lambda t: t.last_status,
    ),
    PBSMaintenanceSensorDescription(
        key="prune_last_duration",
        translation_key="prune_last_duration",
        icon="mdi:timer-outline",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        task_attr="prune",
        value_fn=lambda t: t.last_duration,
    ),
)

DATASTORE_SENSOR_DESCRIPTIONS: tuple[PBSDatastoreSensorDescription, ...] = (
    PBSDatastoreSensorDescription(
        key="total_size",
        translation_key="total_size",
        icon="mdi:database",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        suggested_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        value_fn=lambda d: d.total_bytes,
    ),
    PBSDatastoreSensorDescription(
        key="used_size",
        translation_key="used_size",
        icon="mdi:database",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        suggested_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        value_fn=lambda d: d.used_bytes,
    ),
    PBSDatastoreSensorDescription(
        key="available_size",
        translation_key="available_size",
        icon="mdi:database-outline",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        suggested_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        value_fn=lambda d: d.available_bytes,
    ),
    PBSDatastoreSensorDescription(
        key="usage_percent",
        translation_key="usage_percent",
        icon="mdi:gauge",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.usage_percent,
    ),
    PBSDatastoreSensorDescription(
        key="snapshot_count",
        translation_key="snapshot_count",
        icon="mdi:package-variant-closed",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.snapshot_count,
    ),
)

GUEST_SENSOR_DESCRIPTIONS: tuple[PBSGuestSensorDescription, ...] = (
    PBSGuestSensorDescription(
        key="last_backup_time",
        translation_key="last_backup_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d, _: d.last_backup_time,
    ),
    PBSGuestSensorDescription(
        key="last_backup_status",
        translation_key="last_backup_status",
        icon="mdi:backup-restore",
        device_class=SensorDeviceClass.ENUM,
        options=["OK", "error"],
        value_fn=lambda d, data: data.task_summary.guest_last_status.get(
            f"{d.backup_type}/{d.backup_id}", "OK"
        ),
    ),
    PBSGuestSensorDescription(
        key="last_backup_size",
        translation_key="last_backup_size",
        icon="mdi:database",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        suggested_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        value_fn=lambda d, _: d.last_backup_size,
    ),
    PBSGuestSensorDescription(
        key="last_backup_duration",
        translation_key="last_backup_duration",
        icon="mdi:timer-outline",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d, data: data.task_summary.guest_last_duration.get(
            f"{d.backup_type}/{d.backup_id}"
        ),
    ),
    PBSGuestSensorDescription(
        key="backup_count",
        translation_key="backup_count",
        icon="mdi:package-variant-closed",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d, _: d.snapshot_count,
    ),
    PBSGuestSensorDescription(
        key="last_verify_time",
        translation_key="last_verify_time",
        icon="mdi:check-decagram",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d, _: d.verify_time,
    ),
    PBSGuestSensorDescription(
        key="next_backup_time",
        translation_key="next_backup_time",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d, _: d.next_backup_time,
    ),
)

GLOBAL_SENSOR_DESCRIPTIONS: tuple[PBSGlobalSensorDescription, ...] = (
    PBSGlobalSensorDescription(
        key="total_tasks_24h",
        translation_key="total_tasks_24h",
        icon="mdi:clipboard-list-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.task_summary.total_tasks_24h,
    ),
    PBSGlobalSensorDescription(
        key="failed_tasks_24h",
        translation_key="failed_tasks_24h",
        icon="mdi:clipboard-alert-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.task_summary.failed_tasks_24h,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PBS sensor entities."""
    coordinator: PBSCoordinator = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    entities: list[SensorEntity] = []

    # Global sensors
    device = server_device_info(entry.entry_id, host, port)
    for description in GLOBAL_SENSOR_DESCRIPTIONS:
        entities.append(
            PBSGlobalSensor(coordinator, description, device)
        )

    # Datastore sensors
    for store, ds_data in coordinator.data.datastores.items():
        device = datastore_device_info(entry.entry_id, store, host, port)
        for description in DATASTORE_SENSOR_DESCRIPTIONS:
            entities.append(
                PBSDatastoreSensor(coordinator, description, store, device)
            )
        for description in MAINTENANCE_SENSOR_DESCRIPTIONS:
            entities.append(
                PBSMaintenanceSensor(coordinator, description, store, device)
            )

    # Guest sensors
    for guest_key, guest_data in coordinator.data.guests.items():
        device = guest_device_info(
            entry.entry_id,
            guest_data.backup_type,
            guest_data.backup_id,
            guest_data.datastore,
        )
        for description in GUEST_SENSOR_DESCRIPTIONS:
            entities.append(
                PBSGuestSensor(coordinator, description, guest_key, device)
            )

    async_add_entities(entities)


class PBSDatastoreSensor(PBSEntity, SensorEntity):
    """Sensor for a PBS datastore."""

    entity_description: PBSDatastoreSensorDescription

    def __init__(
        self,
        coordinator: PBSCoordinator,
        description: PBSDatastoreSensorDescription,
        store: str,
        device_info: Any,
    ) -> None:
        """Initialize the sensor."""
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

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        ds = self.coordinator.data.datastores.get(self._store)
        if ds is None:
            return None
        return self.entity_description.value_fn(ds)


class PBSGuestSensor(PBSEntity, SensorEntity):
    """Sensor for a PBS backup guest."""

    entity_description: PBSGuestSensorDescription

    def __init__(
        self,
        coordinator: PBSCoordinator,
        description: PBSGuestSensorDescription,
        guest_key: str,
        device_info: Any,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_info)
        self.entity_description = description
        self._guest_key = guest_key
        self._attr_unique_id = (
            f"{coordinator._entry.entry_id}_{guest_key.replace('/', '_')}_{description.key}"
        )

    @property
    def available(self) -> bool:
        """Return True if the guest exists in coordinator data."""
        return super().available and self._guest_key in self.coordinator.data.guests

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        guest = self.coordinator.data.guests.get(self._guest_key)
        if guest is None:
            return None
        return self.entity_description.value_fn(guest, self.coordinator.data)


class PBSMaintenanceSensor(PBSEntity, SensorEntity):
    """Sensor for a PBS maintenance task."""

    entity_description: PBSMaintenanceSensorDescription

    def __init__(
        self,
        coordinator: PBSCoordinator,
        description: PBSMaintenanceSensorDescription,
        store: str,
        device_info: Any,
    ) -> None:
        """Initialize the sensor."""
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

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        ds = self.coordinator.data.datastores.get(self._store)
        if ds is None:
            return None
        task_data: PBSMaintenanceTaskData = getattr(
            ds, self.entity_description.task_attr
        )
        return self.entity_description.value_fn(task_data)


class PBSGlobalSensor(PBSEntity, SensorEntity):
    """Sensor for global PBS statistics."""

    entity_description: PBSGlobalSensorDescription

    def __init__(
        self,
        coordinator: PBSCoordinator,
        description: PBSGlobalSensorDescription,
        device_info: Any,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_info)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator._entry.entry_id}_global_{description.key}"
        )

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

