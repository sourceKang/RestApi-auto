# YAML Configuration

The REST API automation framework is YAML-only. Normal runs read configuration
only from the YAML files in `configs/`.

## Files

| YAML file | Owns |
| --- | --- |
| `configs/ems.yaml` | EMS REST URL, EMS version, TLS verify default, API timeout |
| `configs/auth_accounts.yaml` | default local accounts, RAD external accounts, auth profiles |
| `configs/hardware_matrix.yaml` | chassis rules, supported controller cards, line cards, GE service cards |
| `configs/test_targets.yaml` | topology-oriented node, slots, cards, ports, ONTs and service selectors |
| `configs/profiles/manifest.yaml` | ordered profile data files referenced by case catalog metadata |

Profile definitions are grouped by domain under `configs/profiles/`. Add a new data file to `manifest.yaml` before referencing its config keys from the case catalog. Duplicate config keys and duplicate `profiletype + profilename` identities are rejected during loading.

## Normal Run

```powershell
pytest --ems-node NODE1
pytest --ems-node NODE3 --auth-matrix
```

## EMS Overrides

Use `EMS_YAML_FILE` only when you want to point the framework at another EMS
YAML file:

```powershell
$env:EMS_YAML_FILE="D:\path\to\ems.yaml"
pytest --ems-node NODE1
```

## Adding A New Node

1. Add or update chassis capability rules in `configs/hardware_matrix.yaml`.
2. Add the node under `nodes:` in `configs/test_targets.yaml`.
3. Include `device_name`, `device_ip`, `chassis`, and EMS location metadata.
4. Add the physical `slots:` inventory with card model, firmware, role and ports.
5. Add ONTs only under GPON/xPON ports, and add GE service data only under the selected GE port.
6. Add `test_targets:` selectors for report slots, ONT target and GE service target.

## Topology v2

`configs/test_targets.yaml` uses the topology-oriented v2 schema. It models the
physical layout first:

```text
node -> slots -> card -> ports -> onts
```

The test target section then only selects the physical target:

```yaml
test_targets:
  report_slots: ["3", "1", "2"]
  ont:
    slot: "2"
    port: "16"
    ont: "1"
  ge_service:
    slot: "1"
    port: "39"
```

This removes repeated `card`, `port_id`, and `ont_id` values from the old
`ont:` and `ge_service:` sections. The loader still accepts v1 files for
compatibility when a custom target file is passed in tests, but the default
configuration now uses v2.

## Account Profiles

`configs/auth_accounts.yaml` has reusable account pools. The default profile is
used unless `--auth-profile` is provided:

```powershell
pytest --ems-node NODE1 --auth-profile default
pytest --ems-node NODE1 --auth-profile rad_external
pytest --ems-node NODE1 --auth-matrix
```

`--auth-matrix` keeps the main run on the selected/default profile and adds
RAD external summary checks in the same report.

## Local Private Values

The tracked `auth_accounts.yaml` and `test_targets.yaml` files are sanitized,
shareable defaults. Put complete real lab values in the ignored
`auth_accounts.local.yaml` and `test_targets.local.yaml` files in the same
`configs` directory. When present, the local file is selected automatically.

`EMS_AUTH_ACCOUNTS_FILE` and `EMS_TEST_TARGETS_FILE` remain explicit run-time
overrides and take precedence over the corresponding local file. Process
environment variables may still override placeholder values when needed.

DUT SSH credentials belong to each node target and are independent from EMS REST
accounts. Configure real `ssh_username` and `ssh_password` values only in
`test_targets.local.yaml`. The tracked file keeps sanitized environment-variable
placeholders. Generic `DUT_SSH_USERNAME` and `DUT_SSH_PASSWORD` process variables
remain explicit run-wide overrides.
