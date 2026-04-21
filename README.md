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
