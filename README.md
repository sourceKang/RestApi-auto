# NetAtlas EMS REST API Automation

This is a new PyTest based REST API automation framework for NetAtlas EMS.

## Quick Start

```powershell
cd "D:\CodeX\RestApi auto"
python -m pip install -r requirements.txt
pytest -m smoke
```

The framework reads its primary configuration from YAML:

```text
configs\ems.yaml
configs\auth_accounts.yaml
configs\hardware_matrix.yaml
configs\test_targets.yaml
configs\profiles.yaml
```

## Project Layout

- `clients/`: EMS REST API client.
- `services/`: domain services and endpoint case helpers used by tests.
- `config_loader/`: YAML loading and runtime environment resolution.
- `cases/`: endpoint definitions, payload factories, converted case catalog and case registry.
- `configs/`: EMS, auth, hardware and DUT target YAML files.
- `models/`: shared typed data models.
- `tests/`: pytest test cases that call domain services through the `services` fixture.
- `tests/support/`: pytest fixtures, options, collection hooks, preflight checks and reporting hooks.
- `utils/`: shared assertions, reporting, diagnostics and redaction helpers.

Override the EMS YAML file when needed:

```powershell
$env:EMS_YAML_FILE="D:\path\to\ems.yaml"
$env:EMS_NODE="NODE3"
pytest
```

Or select the DUT node per run:

```powershell
pytest --ems-node NODE1
pytest --ems-node NODE3
pytest --ems-node NODE1 --auth-profile rad_external
pytest --ems-node NODE1 --auth-matrix
```

`--ems-node` overrides `EMS_NODE` for that pytest run.
`--auth-profile` overrides `EMS_AUTH_PROFILE` for that pytest run.

## Hardware Targets

New framework hardware rules and per-node test targets are kept in YAML:

- `configs/ems.yaml`: EMS REST URL, version, TLS and timeout defaults.
- `configs/hardware_matrix.yaml`: chassis/card capability rules.
- `configs/test_targets.yaml`: NODE-specific report cards, card inventory, ONT target and GE service target.
- `configs/auth_accounts.yaml`: auth profiles and reusable role-based account pools.
- `configs/profiles.yaml`: profile API test definitions referenced by case catalog metadata.

By default the suite runs the main/local account set selected by
`--auth-profile` (or the default profile when omitted). If you also want the
same pytest run to include lightweight RAD external account summaries, add
`--auth-matrix`.

For a new DUT, add the chassis capability to `hardware_matrix.yaml`, then add a
node entry to `test_targets.yaml`.

YAML configuration guidance lives in:

- `docs/yaml_configuration.md`

## Roles

- `readwrite`: selected by auth profile, default profile uses `admin`
- `readonly`: selected by auth profile, default profile uses `RestApiRO`
- `noaccess`: selected by auth profile, default profile uses `RestApiNA`

When `--auth-matrix` is enabled, the txt report also includes:

- `RAD-RW`: representative readwrite capability summary for `rad_external.readwrite1`
- `RAD-RO`: representative readonly capability summary for `rad_external.readonly1`
- `RAD-NA`: representative noaccess capability summary for `rad_external.noaccess1`

## Useful Runs

```powershell
pytest -m session
pytest -m inventory
pytest -m "provision and mutating"
pytest -m "not destructive"
pytest -m remoteconsole --run-remote
pytest -m alarm_delete --run-alarm-delete
```

Requests and responses are attached to Allure when `allure-pytest` is installed.
Passwords and session ids are redacted from logs.
Allure JSON attachments are summarized by default to keep reports small. Set
`EMS_ATTACH_FULL_JSON=1` only when a run needs complete request/response bodies.

## Reports

Every pytest run writes reports under:

```text
reports\<EMS version>\
```

Generated artifacts:

- `Web_Ems_Rest_Api_<EMS version>_<chassis>_<controller>_report_<timestamp>.txt`
- `.allure-results-current`
- `allure-results_<timestamp>` only when `--archive-allure` or `EMS_ARCHIVE_ALLURE=1` is used
- `allure-report_<timestamp>` only when `--generate-allure-html` or `EMS_GENERATE_ALLURE_HTML=1` is used

The txt report follows the legacy report format with summary, EMS/DUT metadata,
card firmware versions and one result line per case ID.
