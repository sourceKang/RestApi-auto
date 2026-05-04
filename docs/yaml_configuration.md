# YAML Configuration

The REST API automation framework is YAML-only. Normal runs read configuration
only from the YAML files in `configs/`.

## Files

| YAML file | Owns |
| --- | --- |
| `configs/ems.yaml` | EMS REST URL, EMS version, TLS verify default, API timeout |
| `configs/auth_accounts.yaml` | default local accounts, RAD external accounts, auth profiles |
| `configs/hardware_matrix.yaml` | chassis rules, supported controller cards, line cards, GE service cards |
| `configs/test_targets.yaml` | NODE identity, card inventory, report cards, ONT target, GE service target |

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
3. Include `device_name`, `device_ip`, `chassis`, `report_cards`,
   `controller_card`, `pon_card`, `ge_service_card`.
4. Add the node's `cards:` inventory with `fw_version`, `slot_id`, `type`,
   `port_id`, `port_type`, and `port_speed`.
5. Add `ont:` and `ge_service:` targets used by the API tests.

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
