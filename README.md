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
configs\profiles\manifest.yaml
```
Before running against a real EMS, review the checked-in YAML files and adjust
them for your lab:

- `configs/ems.yaml`: EMS URL, EMS version, TLS verification and timeout.
- `configs/hardware_matrix.yaml`: supported chassis/card firmware metadata.
- `configs/test_targets.yaml`: per-node slots, ports, ONT target and report targets.
- `configs/auth_accounts.yaml`: auth profiles and role-based accounts.

Do not commit real passwords, tokens, devKeys or private lab credentials.
Keep the canonical YAML files shareable by storing local credentials in the
ignored `.env` file. Values such as `${EMS_AUTH_READWRITE_DEFAULT_USERNAME:-example}`
resolve from the process environment first, then `.env`, and finally the public
fallback after `:-`. The NeoX test data under `configs/neox_config/` is part of
the runnable test dataset and should be kept with the code that consumes it.

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
- `configs/profiles/manifest.yaml`: ordered profile data files referenced by case catalog metadata.

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

Run the per-version OpenAPI YAML versus live Swagger key guard before device-affecting tests:

```powershell
.\.venv\Scripts\python.exe tools\run_openapi_version_guard.py
```

Details: `docs/openapi_version_guard.md`

```powershell
pytest -m session
pytest -m inventory
pytest -m "provision and mutating"
pytest -m "not destructive"
pytest -m remoteconsole --run-remote
pytest -m alarm_delete --run-alarm-delete
pytest --ems-node NODE3 --run-full-testcases
```

Run multiple nodes sequentially with per-node logs and a summary:

```powershell
.\.venv\Scripts\python.exe tools\run_multi_node.py --nodes NODE1,NODE3,NODE6 --run-full-testcases
.\.venv\Scripts\python.exe tools\run_multi_node.py --nodes NODE1,NODE3 --run-full-testcases --dry-run
.\.venv\Scripts\python.exe tools\run_multi_node.py --nodes NODE1,NODE3 --jobs 2 --auth-profiles default,ems_local_rw2 --run-full-testcases
```

The multi-node runner still invokes pytest per node. NeoX-only config options
are kept for NeoX chassis and omitted for non-NeoX chassis. Parallel node runs
must assign a distinct auth profile to each node because logging in with the same
EMS account can invalidate an active session. Keep `--jobs 1` when distinct
accounts are unavailable.

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
- `Web_Ems_Rest_Api_<EMS version>_<chassis>_<controller>_report_<timestamp>.html`
- `.allure-results-current`
- `allure-results_<timestamp>` only when `--archive-allure` or `EMS_ARCHIVE_ALLURE=1` is used
- `allure-report_<timestamp>` only when `--generate-allure-html` or `EMS_GENERATE_ALLURE_HTML=1` is used

`allure-pytest` from `requirements.txt` produces the raw Allure results.
Generating the HTML report also requires Allure Commandline and Java on the
machine running pytest. Verify them before using `--generate-allure-html`:

```powershell
where allure
java -version
```

On Windows, install Allure Commandline with Chocolatey, Scoop, or npm. If
PowerShell blocks `npm.ps1`, use `npm.cmd install -g allure-commandline`.

The txt report follows the legacy report format with summary, EMS/DUT metadata,
card firmware versions and one result line per case ID.
The HTML summary is generated on every pytest run and gives a browser-friendly
overview of totals, failed cases, environment metadata and links to related
report artifacts.
