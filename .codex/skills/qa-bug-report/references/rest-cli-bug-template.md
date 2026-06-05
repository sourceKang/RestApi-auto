# RestApi Auto Bug Templates

Use this reference when drafting project bugs from REST responses, payloads, reports, CLI/device state, or readback checks.

## Compact Universal Format

````text
testcase id:
EMS1-xxxx

subject:
<Product/API/test area> <short wrong behavior>

description:
<1 sentence reproduction and failure summary.>

Payload:
```json
{
  "Content": {}
}
```

Verify:
```text
<CLI command, GET request, report check, or test assertion>
```

Expected: <expected behavior/value/status>.

Actual: <actual REST response/readback/CLI/test result>.

Possible issue: <one concise likely cause based on evidence>.
````

## REST False Success Pattern

Use when POST/PUT/PATCH/DELETE returns success but the target state is not changed.

```text
description:
Send below request to <endpoint/target>. REST API returns `Success`, but verification by <CLI/GET/report> shows <field/config/state> is not applied.

Payload:
...

Verify:
...

Expected: <target state should match payload>.

Actual: REST response is `{"retstatus":"Success","retresult":""}`, but <state is missing/unchanged/different>.

Possible issue: REST backend may not map this field correctly, may report success before device/state apply completes, or may ignore the payload value.
```

## Validation Or Permission Pattern

Use when an invalid request or role behavior is wrong.

```text
description:
Send below request as <role/session>. The API should <reject/allow> it, but actual response is <wrong behavior>.

Payload/params:
...

Expected: <HTTP/retstatus/message or access behavior>.

Actual: <HTTP/retstatus/message or access behavior>.

Possible issue: Validation or permission check may be missing, applied after the operation, or using the wrong role/session context.
```

## Example: NeoX DDMI

````text
testcase id:
EMS1-7120

subject:
NeoX GE DDMI REST API returns Success but DDMI thresholds are not applied to device

description:
POST below DDMI payload to NeoX GE 1-39. REST API returns `Success`, but `show interface ge 1-39 ddmi config` shows the values are unchanged.

Payload:
```json
{
  "Content": {
    "bias_alarm_high": "90",
    "bias_alarm_low": "5",
    "temperature_alarm_high": "100",
    "temperature_alarm_low": "-40",
    "voltage_alarm_high": "3.59",
    "voltage_alarm_low": "2.8"
  }
}
```

Expected: CLI should show requested DDMI thresholds.

Actual: REST response is `{"retstatus":"Success","retresult":""}`, but CLI before/after values are unchanged.

Possible issue: REST backend may ignore DDMI payload values, use wrong field mapping, or default/clamp thresholds while still reporting success.
````

## Example: NeoX vlantrunk_subnet_list

````text
testcase id:
EMS1-7120

subject:
NeoX GE REST config returns Success but vlantrunk_subnet_list is not applied to device

description:
POST below payload to NeoX GE 1-39. REST API returns `Success`, but CLI verification shows `vlantrunk_subnet_list` is not applied.

Payload:
```json
{
  "Content": {
    "vlantrunk_subnet_list": [
      {
        "univid": 1314,
        "subnetip": "192.0.2.0",
        "subnetmask": "255.255.255.0",
        "svid": 1314
      }
    ]
  }
}
```

Verify by CLI:
```text
show running-config interface ge 1-39
show interface ge 1-39 vlan
```

Expected: CLI should show `vlan trunk uni-subnet 192.0.2.0/24 svlan 1314`.

Actual: REST response is `{"retstatus":"Success","retresult":""}`, but the subnet trunk rule is missing in CLI.

Possible issue: CLI requires `[y/N]` confirmation for this per-card setting, so the REST backend may not handle the confirmation flow or may report success before the device command is accepted.
````
