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

Session reuse is enabled by default after the NODE3 rollout validation. The
explicit equivalent is:

```powershell
pytest --session-cache-mode on
```

`EMS_SESSION_CACHE_MODE=on` provides the equivalent environment setting. Role
sessions are reused within one pytest process, refreshed at
540 seconds before the confirmed 600-second absolute lifetime, and refreshed
after exact `Fail / Not authorized.` responses. Only GET/HEAD requests are
retried once; mutating requests are never replayed automatically.
Use `--session-cache-mode off` or `EMS_SESSION_CACHE_MODE=off` for immediate
rollback to per-test login/logout.

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
pytest -m session_lifetime
pytest -m "session and not session_lifetime"
pytest -m inventory
pytest -m "provision and mutating"
pytest -m "not destructive"
pytest -m remoteconsole --run-remote
pytest -m alarm_delete --run-alarm-delete
pytest --ems-node NODE3 --run-full-testcases
```

EMS1-6640 is marked `session_lifetime` because its readwrite path validates the
600-second absolute lifetime and adds about 10 minutes. It remains part of the
full and `session` suites, but is intentionally excluded from the fast `smoke`
selection. The same testcase still covers all three roles; only readwrite runs
the lifetime boundary checks.

Run multiple nodes sequentially with per-node logs and a summary:

```powershell
.\.venv\Scripts\python.exe tools\run_multi_node.py --nodes NODE1,NODE3,NODE6 --run-full-testcases
.\.venv\Scripts\python.exe tools\run_multi_node.py --nodes NODE1,NODE3 --run-full-testcases --dry-run
.\.venv\Scripts\python.exe tools\run_multi_node.py --nodes NODE1,NODE3 --jobs 2 --auth-profiles default,ems_local_rw2 --run-full-testcases
```

Use explicit execution lanes for the stable split workflow:

```powershell
# Read-only baseline: parallel by node, no lifetime or mutation.
.\.venv\Scripts\python.exe tools\run_multi_node.py --nodes NODE1,NODE2,NODE3 --jobs 3 --auth-profiles default,ems_local_rw2,rad_external

# Node-owned mutation: serial inside each node process, parallel across distinct DUT resources.
.\.venv\Scripts\python.exe tools\run_multi_node.py --nodes NODE1,NODE2,NODE3 --jobs 3 --auth-profiles default,ems_local_rw2,rad_external --lane node-mutating

# EMS-global mutation: exactly one representative node and one job.
.\.venv\Scripts\python.exe tools\run_multi_node.py --nodes NODE1 --jobs 1 --auth-profiles default --lane ems-mutating

# EMS-scoped absolute session lifetime: exactly one representative node and one job.
.\.venv\Scripts\python.exe tools\run_multi_node.py --nodes NODE1 --jobs 1 --auth-profiles default --lane ems-session-lifetime
```

The `node-mutating` lane excludes destructive cases and EMS1-6640. NeoX config
cases are enabled only for NeoX nodes, while each node process remains serial so
ONT and GE lifecycles stay ordered. The `ems-mutating` lane runs shared EMS
profile lifecycles exactly once. Alarm acknowledge/clear remains destructive and
is excluded from both mutation lanes. The `ems-session-lifetime` lane accepts
exactly one node, preventing the 600-second EMS behavior from being repeated for
every DUT. If an ONT target already uses a template that was not created by the
current run, its CRUD workflow is skipped as an ownership precondition; the
existing service is not overwritten or deleted.

Without `--run-full-testcases` or an explicit pytest `-m` expression, the
multi-node runner defaults to `not mutating and not destructive and not
session_lifetime`. This keeps the routine parallel baseline read-only and omits
the 10-minute EMS session-lifetime case. Pass an explicit `-m` expression for a
different bounded selection, or `--run-full-testcases` only when the full
mutating environment workflow is intended.

The multi-node runner still invokes pytest per node. NeoX-only config options
are kept for NeoX chassis and omitted for non-NeoX chassis. Parallel node runs
must assign a distinct auth profile to each node because logging in with the same
EMS account can invalidate an active session. The runner validates the resolved
role usernames as well as profile names. Keep `--jobs 1` when distinct accounts
are unavailable. Each runner-created pytest process also enables
`--formal-testcases-only`, so framework unit tests are not repeated under every
DUT environment unless they are explicitly invoked outside the multi-node runner.

Audit temporary profile graphs left by interrupted runs:

```powershell
# Read-only audit. Only locally registered graphs older than 24 hours are inspected.
.\.venv\Scripts\python.exe tools\cleanup_stale_test_data.py --node NODE1 --auth-profile default

# Explicit cleanup after the audit result has been reviewed.
.\.venv\Scripts\python.exe tools\cleanup_stale_test_data.py --node NODE1 --auth-profile default --cleanup-stale-test-data
```

Each temporary ONT/GE profile graph is registered locally before its first POST.
Normal fixture cleanup removes both the EMS profiles and the local manifest. An
interrupted run leaves the manifest for a later audit. Cleanup is restricted to
the same EMS identity and node, requires the configured minimum age (24 hours by
default), performs exact profile GET checks, and refuses deletion when the node's
ONT/GE target still references the root template or its reference state cannot be
confirmed. Files that do not match the automation-owned temporary naming pattern
are reported as invalid and are never deleted.

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
