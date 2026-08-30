# Proxmox Backup Server

Full monitoring and control for Proxmox Backup Server (PBS). Includes optional Proxmox VE (PVE) integration for VM backup management.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/thecodingdad/ha-proxmox-backup)](https://github.com/thecodingdad/ha-proxmox-backup/releases)

## Features

- Monitor datastore usage, total size, and used space
- Track snapshot counts per datastore
- View status of last verify, garbage collection, and prune tasks
- Binary sensor for backup freshness (stale after 26 hours)
- Trigger verify jobs, garbage collection, and prune operations from Home Assistant
- Optional Proxmox VE integration for backup triggers
- API token-based authentication

## Prerequisites

- Home Assistant 2026.3.0 or newer
- Proxmox Backup Server (PBS) instance with API token access
- Optionally a Proxmox VE (PVE) instance with API token access

## Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=thecodingdad&repository=ha-proxmox-backup&category=integration)

Or add manually:
1. Open HACS in your Home Assistant instance
2. Click the three dots in the top right corner and select **Custom repositories**
3. Enter `https://github.com/thecodingdad/ha-proxmox-backup` and select **Integration** as the category
4. Click **Add**, then search for "Proxmox Backup Server" and download it
5. Restart Home Assistant

### Manual Installation

1. Download the latest release from [GitHub Releases](https://github.com/thecodingdad/ha-proxmox-backup/releases)
2. Copy the `custom_components/proxmox_backup` folder to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

### Setup

1. Go to **Settings** -> **Devices & Services**
2. Click **Add Integration**
3. Search for "Proxmox Backup Server"
4. Follow the setup wizard

### PBS Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `host` | string | required | PBS server address |
| `port` | integer | 8007 | PBS API port |
| `token_id` | string | required | API token ID (e.g. user@pbs!token) |
| `token_secret` | string | required | API token secret |
| `verify_ssl` | boolean | false | Enable SSL certificate verification |
| `node` | string | localhost | Backup node name |
| `scan_interval` | integer | 300 | Polling interval in seconds (60-3600) |

### Optional PVE Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `pve_host` | string | optional | PVE server address |
| `pve_port` | integer | 8006 | PVE API port |
| `pve_token_id` | string | optional | PVE API token ID |
| `pve_token_secret` | string | optional | PVE API token secret |
| `pve_verify_ssl` | boolean | false | Enable SSL certificate verification |

## API Token Permissions

The setup wizard verifies the token during configuration and rejects it if privileges are missing. Note that a token only ever gets the intersection of its own ACL and the parent user's ACL, unless **Privilege Separation** is disabled for the token.

### PBS Permissions

| Feature | Privilege | Path |
|---------|-----------|------|
| Datastore sensors (usage, size, snapshots) | `Datastore.Audit` | `/datastore` (or `/datastore/<store>`) |
| Task history, backup status, freshness | `Sys.Audit` | `/system` |
| Verify button | `Datastore.Verify` | `/datastore/<store>` |
| Garbage collection button | `Datastore.Modify` | `/datastore/<store>` |
| Prune button | `Datastore.Prune` | `/datastore/<store>` |

Minimum for read-only monitoring — assign both roles:

```bash
proxmox-backup-manager user create monitor@pbs
proxmox-backup-manager user generate-token monitor@pbs ha-token
proxmox-backup-manager acl update /datastore DatastoreAudit --auth-id 'monitor@pbs!ha-token'
proxmox-backup-manager acl update /system Audit --auth-id 'monitor@pbs!ha-token'
```

To also use the verify, garbage collection, and prune buttons, grant `DatastoreAdmin` on the datastore instead of `DatastoreAudit`:

```bash
proxmox-backup-manager acl update /datastore DatastoreAdmin --auth-id 'monitor@pbs!ha-token'
```

### PVE Permissions (optional)

| Feature | Privilege | Path |
|---------|-----------|------|
| Node list, backup schedules (next backup sensor) | `Sys.Audit` | `/` |
| Trigger backup button | `VM.Backup` | `/vms/<vmid>` or `/vms` |
| Trigger backup button | `Datastore.AllocateSpace` | `/storage/<storage>` |

```bash
pveum user add ha@pve
pveum user token add ha@pve ha-token --privsep 0
pveum acl modify / --roles PVEAuditor --tokens 'ha@pve!ha-token'
# only needed for the trigger backup button
pveum acl modify /vms --roles PVEVMAdmin --tokens 'ha@pve!ha-token'
pveum acl modify /storage --roles PVEDatastoreUser --tokens 'ha@pve!ha-token'
```

Without PVE permissions the integration still works — PVE features are disabled and a warning is written to the log.

## Entities

The integration creates the following entities for each datastore on your Proxmox Backup Server.

### Sensors

| Sensor | Description |
|--------|-------------|
| Datastore Usage | Datastore usage as a percentage |
| Total Size | Total capacity of the datastore |
| Used Size | Amount of space currently used |
| Snapshot Count | Number of snapshots stored in the datastore |
| Last Verify Task | Status of the last verify task |
| Last GC Task | Status of the last garbage collection task |
| Last Prune Task | Status of the last prune task |

### Binary Sensors

| Binary Sensor | Description |
|---------------|-------------|
| Backup Freshness | Indicates whether the backup is stale (no backup in the last 26 hours) |

### Buttons

| Button | Description |
|--------|-------------|
| Trigger Verify | Start a verify job on the datastore |
| Garbage Collection | Run garbage collection on the datastore |
| Prune | Execute a prune operation on the datastore |

## Troubleshooting

| Message | Cause |
|---------|-------|
| `Invalid API token` | HTTP 401 — token ID or secret is wrong, the token was deleted, or the realm in the token ID does not match (e.g. `@pbs` vs `@pam`) |
| `The API token is valid but lacks permissions` | HTTP 403 — the token authenticates, but the ACL is missing a privilege. The log names the denied endpoint and the required privilege |
| `Failed to connect` | Host, port, firewall, or SSL certificate problem |

If the token is rejected while the integration is running, Home Assistant starts a re-authentication flow where a new token can be entered. Permission problems do not trigger re-authentication — fix the ACL and reload the integration.

## Multilanguage Support

This integration supports English and German.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
