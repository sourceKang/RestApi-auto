---
name: qa-bug-report
description: Draft concise RestApi Auto QA bug reports in the user's testcase id, subject, description format. Use when the user asks to create, supplement, revise, or optimize a bug, bug subject/description, defect report, testcase-linked issue, REST API issue, CLI/device verification issue, permission/auth issue, payload/schema issue, or report-derived failure from this project.
---

# QA Bug Report

## Output Contract

Always use this exact top-level format unless the user asks for another format:

```text
testcase id:
subject:
description:
```

Keep the description short enough for RD to scan, but include the concrete reproduction data needed to debug. This skill is project-wide for RestApi Auto, not limited to NeoX config.

## Workflow

1. Identify the testcase id.
2. Write one subject that names the API/feature, the false success or wrong behavior, and the affected field when known.
3. Build the description with reproduction evidence:
   - Action: REST method/path, test name, or short reproduction step.
   - Payload/params: include the relevant minimal JSON body, query params, path params, or headers when available.
   - Verify: include CLI command, GET/readback, report path, response body, or observed check.
   - Expected: one sentence or a small CLI token.
   - Actual: response, UI/report result, CLI mismatch, missing config, wrong status, or error.
   - Possible issue: add a concise analysis when evidence suggests mapping, validation, permission, confirmation, defaulting, async apply, cleanup, or state-sync problems.
4. Prefer the user's wording and keep Traditional Chinese labels only if the user uses them. Otherwise keep the three labels exactly as shown.

## Testcase Id Rules

Use this order:

1. Use the testcase id explicitly provided by the user.
2. If a pytest function, endpoint case, or report name is provided, search project mappings before answering:
   - `cases/neox_case_ids.py`
   - `cases/registry.py`
   - `cases/case_catalog.py`
   - `cases/regression.py`
   - `tests/support/collection.py`
   - `utils/case_metadata.py`
   - nearby test files for `attach_case_id(...)`, `case_id=...`, or `case_ids`.
3. If the failure is a NeoX profile parameterized case, derive the id using `cases/neox_case_ids.py` rather than guessing.
4. If no testcase id can be found, write `UNKNOWN` and mention the lookup gap only if useful.

Known direct NeoX config ids:

```text
test_ge_config_clear_readwrite: EMS1-7118
test_ge_config_min_create_readwrite: EMS1-7119
test_ge_config_max_create_readwrite: EMS1-7120
test_ge_config_error_readwrite: EMS1-7121
test_nni_config_clear_readwrite: EMS1-7122
test_nni_config_min_create_readwrite: EMS1-7123
test_nni_config_max_create_readwrite: EMS1-7124
test_nni_config_error_readwrite: EMS1-7125
test_vlan_config_clear_readwrite: EMS1-7126
test_vlan_config_min_create_readwrite: EMS1-7127
test_vlan_config_max_create_readwrite: EMS1-7128
test_vlan_config_error_readwrite: EMS1-7129
test_ont_config_clear_readwrite: EMS1-7130
test_ont_config_min_create_readwrite: EMS1-7131
test_ont_config_max_create_readwrite: EMS1-7132
test_ont_config_error_readwrite: EMS1-7133
```

For NeoX GE field-level bugs found during max payload/config verification, use `EMS1-7120` unless the user points to a different testcase.

## Bug Types

Choose the smallest useful description pattern:

- REST false success: response says `Success` but readback/CLI/device state is wrong.
- REST validation bug: invalid payload returns success, wrong error code, unclear message, or accepts unsupported fields.
- REST schema/mapping bug: payload key exists in swagger/test data but maps to the wrong device command or is ignored.
- Permission/auth bug: readwrite/readonly/noaccess behavior differs from expected access matrix.
- Inventory/provisioning/state bug: async state does not converge, cleanup fails, or GET result disagrees with POST/DELETE.
- Report/test automation bug: testcase expectation or generated report is wrong; distinguish product issue from automation issue.

## REST And Device/CLI Bugs

When the bug is a REST/CLI verification mismatch, read `references/rest-cli-bug-template.md` if examples or phrasing are needed.

Common possible issue patterns:

- REST returns `Success` but CLI config is missing: backend may report success before the device command is accepted, or the REST field may not map to the CLI command.
- CLI-first works only after a warning confirmation: REST backend may not handle the interactive confirmation flow.
- REST returns `Success` but CLI value stays default or changes to a different value: backend may ignore payload values, clamp/default them, or use wrong field names/types.
- Payload list item is accepted but not visible: list serialization, key naming, or per-card/per-port scope mapping may be wrong.
- GET/readback differs from POST payload: persistence layer, response model, or async refresh may be stale.
- Permission response is wrong: role checking may happen at the wrong layer or reuse a cached session/access profile.

## Style

Use compact RD-facing language. Do not over-explain the test framework. Include exact payload and CLI evidence when available. If evidence is incomplete, state what was verified and what remains unverified.
