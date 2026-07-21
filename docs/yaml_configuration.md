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

The tracked `auth_accounts.yaml` and `test_targets.yaml` files are the single
canonical configuration sources. Their sensitive fields use
`${VARIABLE:-public_fallback}` references. Put real lab values in the ignored
project-root `.env` file; process environment variables take precedence over
`.env`, and the public fallback is used only when neither is set.

`EMS_ENV_FILE` may select a different local environment file. The existing
`EMS_AUTH_ACCOUNTS_FILE` and `EMS_TEST_TARGETS_FILE` variables may still select
an entirely different canonical YAML file when required. Never commit `.env`.
