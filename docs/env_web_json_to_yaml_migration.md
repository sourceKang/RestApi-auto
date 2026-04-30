# ENV_WEB.JSON to YAML Migration Map

This document defines how the new REST API automation should gradually stop
depending on `D:\AScript\PyTest\EMS\web_ems\ENV_WEB.JSON` without modifying the
legacy file.

## Goal

Move the new framework toward YAML-owned configuration while keeping
`ENV_WEB.JSON` read-only during the transition.

The migration should optimize for:

- stable test behavior
- simple node switching
- clean account management
- easier maintenance for new chassis/cards/nodes
- clear ownership of "live lab inventory" vs "test target"

## Current State

The new framework still reads these core areas from `ENV_WEB.JSON`:

- EMS connection and version
- default readwrite/readonly/noaccess credentials
- selected DUT basic identity
- live `CARDINFO`
- live `ONTINFO`

YAML is already used for:

- chassis/card capability rules: `configs/hardware_matrix.yaml`
- per-node test targets: `configs/test_targets.yaml`

## Recommended YAML Split

Do not copy the whole legacy JSON structure into one YAML file.

Instead, split it by responsibility:

1. `configs/ems.yaml`
   - EMS URL
   - EMS version
   - API timeout / TLS options
   - default admin login for REST API tests

2. `configs/auth_accounts.yaml`
   - role-based login pools
   - local EMS accounts
   - external RAD accounts

3. `configs/hardware_matrix.yaml`
   - chassis capability rules
   - allowed controller cards
   - allowed line cards
   - GE service capable cards

4. `configs/test_targets.yaml`
   - node identity used by this project
   - cards selected for testing/reporting
   - ONT test target
   - GE service test target

5. Optional future file: `configs/seed_inventory.yaml`
   - backup ONT samples
   - backup cards/ports
   - optional test data pools

## Field Mapping

### Keep in JSON only for now

These fields are legacy or outside the scope of this REST API framework:

| ENV_WEB.JSON path | Reason |
| --- | --- |
| `LOOP.*` | legacy UI/system test control |
| `ELEMENT.*` | legacy wait tuning |
| `AUTO_SITE.*` | UI upload/report path data |
| `EMS.url` | UI URL, not required for REST tests |
| `EMS.server_username` | outside REST test scope |
| `EMS.server_password` | outside REST test scope |
| `EMS.sudo_password` | outside REST test scope |
| `EMS.db_username` | outside REST test scope |
| `EMS.db_password` | outside REST test scope |
| `EMS.USER.USER1..USER3` metadata | not used by current REST framework |
| extra DUT UI fields (`submap_name`, `map_name`, etc.) | not needed for current API tests |

These should not be migrated unless the new framework actually starts using
them.

### Move to `configs/ems.yaml`

| ENV_WEB.JSON path | New YAML path | Notes |
| --- | --- | --- |
| `EMS.rest_api_url` | `ems.rest_api_url` | primary API base URL |
| `EMS.version` | `ems.version` | report output |
| `EMS.login_username` | `ems.default_readwrite.username` | can later move fully under account pools |
| `EMS.login_password` | `ems.default_readwrite.password` | can later move fully under account pools |

Suggested future structure:

```yaml
version: 1

ems:
  rest_api_url: "https://..."
  version: "03.00.10 (AAVV.221) b6"
  verify_tls: false
  timeout: 60
```

### Move to `configs/auth_accounts.yaml`

| ENV_WEB.JSON path | New YAML path | Notes |
| --- | --- | --- |
| `EMS.login_username/login_password` | `accounts.readwrite.default.*` | current admin/local account |
| `EMS.USER.USER5.name/password` | `accounts.readonly.default.*` | current readonly account |
| `EMS.USER.USER4.name/password` | `accounts.noaccess.default.*` | current noaccess account |
| new RAD accounts | `accounts.<role>.rad_external.<name>.*` | future multi-account execution |

Suggested future structure:

```yaml
version: 1

accounts:
  readwrite:
    default:
      username: "admin"
      password: "..."
      source: "ems_local"
    rad_external:
      readwrite1:
        username: "readwrite1"
        password: "readwrite1PW"
        source: "rad_external"

  readonly:
    default:
      username: "RestApiRO"
      password: "..."
      source: "ems_local"
    rad_external:
      readonly1:
        username: "readonly1"
        password: "readonly1PW"
        source: "rad_external"

  noaccess:
    default:
      username: "RestApiNA"
      password: "..."
      source: "ems_local"
    rad_external:
      noaccess1:
        username: "noaccess1"
        password: "noaccess1PW"
        source: "rad_external"
```

### Move to `configs/test_targets.yaml`

These values describe what this project intentionally tests on each node. They
should be owned by YAML, not discovered ad hoc from legacy JSON.

| ENV_WEB.JSON path | New YAML path | Status |
| --- | --- | --- |
| `ZYXEL_DUT.NODEX.name` | `nodes.NODEX.device_name` | not migrated yet |
| `ZYXEL_DUT.NODEX.ip` | `nodes.NODEX.device_ip` | not migrated yet |
| `ZYXEL_DUT.NODEX.chassis` | `nodes.NODEX.chassis` | not migrated yet |
| selected report cards | `nodes.NODEX.report_cards` | already migrated |
| selected controller card | `nodes.NODEX.controller_card` | already migrated |
| selected PON card | `nodes.NODEX.pon_card` | already migrated |
| selected GE service card | `nodes.NODEX.ge_service_card` | already migrated |
| ONT slot/port/ont/sn/password/template/description | `nodes.NODEX.ont.*` | mostly migrated |
| GE slot/port/template/port_name/telephone | `nodes.NODEX.ge_service.*` | mostly migrated |

Recommended final target shape:

```yaml
version: 1

nodes:
  NODE1:
    device_name: "California_IES4204_169.57"
    device_ip: "192.168.169.57"
    chassis: "IES4204"
    report_cards: ["MSC1240QB", "GLC1440X", "OLC3816"]
    controller_card: "MSC1240QB"
    pon_card: "OLC3816"
    ge_service_card: "GLC1440X"
    ont:
      slot_id: "2"
      port_id: "16"
      ont_id: "1"
      sn: "5A5958458CADDDC3"
      password: "F44D5C39E710"
      description: "tony_test"
      template: "#RestApi_provision_temp_SFU"
    ge_service:
      slot_id: "1"
      port_id: "39"
      template: "#RestApi_getemp_ge1"
      port_name: "10g_Hsinchu"
      telephone: "011+886+7+2737"
```

### Keep `CARDINFO` in JSON for now, but use YAML to select from it

`CARDINFO` still has value as live lab inventory because it carries:

- actual firmware versions
- actual slot assignment
- actual type strings
- actual port capabilities

Current recommendation:

- keep the raw card inventory in `ENV_WEB.JSON` for now
- let YAML select which cards this project cares about
- continue using YAML tokens such as `MSC1240QB`, `GLC1440X`, `OLC3816`

Move `CARDINFO` fully to YAML only when the team is ready to maintain lab
inventory outside the legacy system.

### Keep `ONTINFO` as fallback only, then phase out

`ONTINFO` is currently used as fallback sample data when YAML does not provide a
fully explicit ONT target.

Recommended direction:

1. keep `ONTINFO` as fallback during transition
2. make `nodes.NODEX.ont.*` complete enough that tests no longer need fallback
3. after that, stop reading `ONTINFO` for primary test selection

## Migration Phases

### Phase A: finish YAML ownership of explicit test targets

Implement next:

- `nodes.NODEX.device_name`
- `nodes.NODEX.device_ip`
- `nodes.NODEX.chassis`
- full ONT target
- full GE service target

Expected result:

- node switching no longer depends on legacy DUT discovery order
- report identity comes from YAML-owned target data

### Phase B: add account pools

Implement next:

- `configs/auth_accounts.yaml`
- role -> profile -> named account model
- fixtures choose credentials by profile
- reports show auth profile and selected accounts

Expected result:

- one test suite can run against local EMS accounts or RAD external accounts
- no test duplication required

### Phase C: reduce fallback dependence

Implement next:

- use YAML first for DUT identity and test target
- use `ENV_WEB.JSON` only for live inventory fallback and backward compatibility

Expected result:

- fewer hidden dependencies
- simpler config reasoning

### Phase D: optional future inventory split

Only do this if needed:

- move lab inventory snapshots into YAML
- or replace them with API-discovered dynamic inventory

Expected result:

- full decoupling from `ENV_WEB.JSON`
- higher maintenance responsibility on the new project

## Recommended End State

The new framework should eventually depend on `ENV_WEB.JSON` only as an
optional legacy compatibility source, not as the primary truth.

Primary truth should become:

- EMS/API configuration in `ems.yaml`
- accounts in `auth_accounts.yaml`
- platform capability in `hardware_matrix.yaml`
- node-specific test intent in `test_targets.yaml`

This gives the cleanest maintenance model without forcing live lab inventory to
be manually duplicated too early.
