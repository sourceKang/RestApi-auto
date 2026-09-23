# Redmine Bug Template

This is the project-owned Redmine bug template for RestApi Auto.
UseTestlink is treated as a transport tool for uploading TestLink results and
linking Redmine issues; it must not be the source of truth for bug wording.

## Review Rule

Before creating or updating Redmine/TestLink, always show the final bug content
and TestLink write plan to the user and wait for explicit approval.

The preview must include:

- Redmine subject.
- Redmine description.
- Redmine field values.
- TestLink testcase ids, result status, build, platform, and bug links.

## Redmine Fields

Use these defaults unless the user gives a different value.

```text
Project: netatlas-ems_pqa
Tracker: Bug
Status: New
Severity: L2 (Redmine built-in priority_id=5)
Priority: blank (custom field ID 119; do not set until its allowed values are confirmed)
Category: current tested EMS build, for example 03.00.11(AAVV.221)b6
Target version: 03.00.11 (AAVA.221) C0 - Internal
```

Custom fields:

```text
FW Ver: current tested EMS build, for example 03.00.11(AAVV.221)b6
Product Line: EMS
Model: NetAtlas EMS
Category: SW
Customer: Generic
Test plan ver: 2.00
Test case No: EMS testcase id, for example EMS1-7122
Test Type: Function
Report Date: report run date
Reporter dept: PQA
Reporter: Kang Cheng
Problem Category: Regression for regression failures, otherwise choose the evidence-backed category
Service Type: Others
Fix Version: blank unless verifying a released fix or user specifies it
Feature Category: EMS-NBI
Bug analysis: User experience unless evidence points to a different analysis
```

Severity and Priority are independent fields. Never send custom field ID 119 as
Redmine `priority_id`, and never reuse the Severity L1/L2/L3 mapping for the custom
Priority field. Review both values and their transport fields in the UseTestlink
preview before approving a write.

Subject convention:

```text
[Regression][RestApi] <area/API> <concise wrong behavior>
```

Use `[Regression]` only when the user or evidence identifies the issue as a
regression.

## Description Template

Keep the top-level labels stable so Redmine bugs are easy to scan.

````text
testcase id: <EMS testcase id>
subject: <same as Redmine subject>
description:
Action: <test name, REST method/path, or short reproduction step>

Target:
EMS Version: <version/build>
Node: <node name or key>
Target: <slot/port/ONT/profile/object, if applicable>

Payload/params:
<METHOD> <API path>
```json
<request body or null>
```

Return:
HTTP <status code>
```json
<response body>
```

Verify:
<report path, testcase line, GET/readback, CLI command, or assertion>

Device log:
```text
<CLI/device log, only when available>
```

Related:
<related testcase or bug id, only when useful>

Expected:
<expected behavior>

Actual:
<actual behavior>

Possible issue:
<concise evidence-based likely cause>
````

Omit optional sections when there is no evidence. Do not include secrets,
session ids, tokens, passwords, or unredacted personal data.

## Bug Split Rules

- Create one bug per independent product symptom.
- If min and max payloads fail with the same root symptom, create one bug and
  list the other testcase under `Related`.
- If clear/setup/cleanup fails for a different reason than create/update, split
  it into a separate bug.
- If the failure is likely test automation or environment setup, say that in
  `Possible issue` instead of filing it as a product defect.

## Evidence Rules

- REST validation or mapping bugs must include payload and response.
- REST/CLI mismatch bugs must include CLI command/output or a report path.
- Confirmation-flow bugs should include the prompt and exact confirmation input
  sequence, for example duplicate `y`.
- Swagger/YAML/schema bugs must include the Swagger/YAML key and payload key.
- Permission bugs must include role, expected access, and actual response.
