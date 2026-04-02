"""Constants for the Proxmox Backup Server integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "proxmox_backup"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]

DEFAULT_PORT = 8007
DEFAULT_SCAN_INTERVAL = 300  # seconds
MIN_SCAN_INTERVAL = 60
MAX_SCAN_INTERVAL = 3600

CONF_SCAN_INTERVAL = "scan_interval"
CONF_TOKEN_ID = "token_id"
CONF_TOKEN_SECRET = "token_secret"
CONF_VERIFY_SSL = "verify_ssl"
CONF_NODE = "node"

BACKUP_FRESHNESS_HOURS = 26

# PVE configuration keys (optional)
CONF_PVE_HOST = "pve_host"
CONF_PVE_PORT = "pve_port"
CONF_PVE_TOKEN_ID = "pve_token_id"
CONF_PVE_TOKEN_SECRET = "pve_token_secret"
CONF_PVE_VERIFY_SSL = "pve_verify_ssl"
DEFAULT_PVE_PORT = 8006

# PVE API endpoints
API_PVE_VERSION = "/api2/json/version"
API_PVE_NODES = "/api2/json/nodes"
API_PVE_BACKUP_JOBS = "/api2/json/cluster/backup"
API_PVE_VZDUMP = "/api2/json/nodes/{node}/vzdump"

# PBS API endpoints
API_VERSION = "/api2/json/version"
API_DATASTORE_LIST = "/api2/json/admin/datastore"
API_DATASTORE_USAGE = "/api2/json/status/datastore-usage"
API_DATASTORE_SNAPSHOTS = "/api2/json/admin/datastore/{store}/snapshots"
API_NODE_TASKS = "/api2/json/nodes/{node}/tasks"

# PBS maintenance API endpoints
API_DATASTORE_VERIFY = "/api2/json/admin/datastore/{store}/verify"
API_DATASTORE_GC = "/api2/json/admin/datastore/{store}/garbage-collection"
API_DATASTORE_PRUNE = "/api2/json/admin/datastore/{store}/prune"

# PBS task types for filtering
TASK_TYPE_VERIFY_JOB = "verificationjob"
TASK_TYPE_VERIFY_GROUP = "verify_group"
TASK_TYPE_VERIFY_SNAPSHOT = "verify"
TASK_TYPE_GC = "garbage_collection"
TASK_TYPE_PRUNE_JOB = "prunejob"
TASK_TYPE_PRUNE = "prune"
