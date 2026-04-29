# NetAtlas EMS REST API Automation

This is a new PyTest based REST API automation framework for NetAtlas EMS.

## Quick Start

```powershell
cd "D:\CodeX\RestApi auto"
python -m pip install -r requirements.txt
pytest -m smoke
```

The framework reads the current EMS environment from:

```text
D:\AScript\PyTest\EMS\web_ems\ENV_WEB.JSON
```

Override it when needed:

```powershell
$env:EMS_ENV_FILE="D:\path\to\ENV_WEB.JSON"
$env:EMS_NODE="NODE3"
pytest
```

Or select the DUT node per run:

```powershell
pytest --ems-node NODE1
pytest --ems-node NODE3
```

`--ems-node` overrides `EMS_NODE` for that pytest run.

## Hardware Targets

`ENV_WEB.JSON` is treated as read-only legacy environment data. New framework
hardware rules and per-node test targets are kept in YAML:

- `configs/hardware_matrix.yaml`: chassis/card capability rules.
- `configs/test_targets.yaml`: NODE-specific report cards, test cards, ONT target and GE service target.

For a new DUT, add the chassis capability to `hardware_matrix.yaml`, then add a
node entry to `test_targets.yaml`. If a node is not listed in YAML, the
framework falls back to the legacy selection logic from `ENV_WEB.JSON`.
For fields listed in both places, YAML wins and `ENV_WEB.JSON` remains a
read-only fallback.

## Roles

- `readwrite`: `EMS.login_username` / `EMS.login_password`
- `readonly`: `EMS.USER.USER5`, expected name `RestApiRO`
- `noaccess`: `EMS.USER.USER4`, expected name `RestApiNA`

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

## Reports

Every pytest run writes reports under:

```text
reports\<EMS version>\
```

Generated artifacts:

- `Web_Ems_Rest_Api_<EMS version>_<chassis>_<controller>_report_<timestamp>.txt`
- `allure-results_<timestamp>`
- `allure-report_<timestamp>` when the Allure CLI is available

The txt report follows the legacy report format with summary, EMS/DUT metadata,
card firmware versions and one result line per case ID.
