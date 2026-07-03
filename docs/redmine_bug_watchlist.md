# Redmine Bug Watchlist

Purpose: track Redmine bugs from the captured NeoX/RestApi list and compare them with later test reports to identify which fixes are verified.

Source: user screenshot on 2026-06-22 and authenticated Redmine API lookup from http://172.20.0.37/projects/netatlas-ems_pqa/issues?set_filter=1&tracker_id=1. API key is not stored in this file.

## Summary

| RM ID | Redmine status | Priority | Fix Version | Fixed date | Testcase ID(s) | Report status in screenshot | Verification result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [RM 255427](http://172.20.0.37/issues/255427) | Released | L2 | 03.00.11(AAVV.221)b6 | 2026-06-17 | EMS1-7120 | Not Run | Needs manual review after 2026-06-22 Node3 b6 run: EMS1-7120 failed, and the report did not exercise a line-id payload. |
| [RM 255423](http://172.20.0.37/issues/255423) | Released | L2 | 03.00.11(AAVV.221)b6 | 2026-06-17 | EMS1-6853 | Not Run | Needs manual review after 2026-06-22 Node3 b6 run: EMS1-6853 passed, but NeoX RateLimitProfile min/max failed with Invalid JSON input. |
| [RM 255185](http://172.20.0.37/issues/255185) | Released | L1 | 03.00.11(AAVV.221)b6 | 2026-06-17 | EMS1-7124 | Not Run | Still failing after 2026-06-22 Node3 b6 run: EMS1-7124 failed with NNI POST returning `% Invalid command "y"`. |
| [RM 255162](http://172.20.0.37/issues/255162) | Released | L2 | 03.00.11(AAVV.221)b6 | 2026-06-17 | EMS1-7120, EMS1-7119 | Not Run | Needs manual review after 2026-06-22 Node3 b6 run: EMS1-7119 passed, EMS1-7120 failed for other missing CLI tokens; ACL profile mode symptom was not isolated. |
| [RM 255125](http://172.20.0.37/issues/255125) | Released | L2 | 03.00.11(AAVV.221)b6 | 2026-06-17 | EMS1-7120 | Not Run | Needs manual review after 2026-06-22 Node3 b6 run: subnet trunk CLI line was present, but EMS1-7120 still failed on unrelated DHCP/LLDP tokens. |
| [RM 254861](http://172.20.0.37/issues/254861) | Closed | L2 | 03.00.11(AAVV.221)b6 | 2026-06-17 | EMS1-7160 | Not Run | Verified PASS on 2026-06-23 Node3 b6 after payload correction from `spoofingdisable` to `spoofingable`; min and max ONTSecurityProfile create/readwrite both passed. |
| [RM 254820](http://172.20.0.37/issues/254820) | Released | L2 | 03.00.11(AAVV.221)b6 | 2026-06-17 | EMS1-7140 | Not Run | Still failing after 2026-06-22 Node3 b6 run: EMS1-7140 failed with Invalid JSON input for ONTAclProfile. |

## Redmine Details

### RM 255427

- Subject: [RestApi][YAML]NeoX GE config REST API missing parameter for Port-Line-ID field.
- Status: Released; assignee: Leaf Yeh; author: Kang.Cheng Chang.
- FW Ver: 03.00.11(AAVV.221)b4; Fix Version: 03.00.11(AAVV.221)b6.
- Problem category: Design issue; bug analysis: No spec defined.
- Testcase: EMS1-7120.
- Issue detail: GE config REST schema for `/configNeoXSeries/interface/ge/{devicename}/{slotid}/{portid}` did not expose a parameter for CLI `line-id` / Port-Line-ID. Existing `tel` maps to Port-Telephone-No., not Port-Line-ID.
- Expected: REST GE config should provide a set/clear payload field mapped to CLI `line-id`.
- Actual: Swagger/test payload had no `line-id`, `lineid`, or equivalent field.
- Fix note: Add the line-id setting.
- Verification focus: GE max config should include and verify Port-Line-ID / line-id behavior in EMS1-7120 report and CLI readback.

### RM 255423

- Subject: [RestAPI][/profile/RateLimitProfile/{profilename}][YAML][NeoX Config] Missing Per-VLAN Egress Rate Limit Parameters.
- Status: Released; assignee: Leaf Yeh; author: Kang.Cheng Chang.
- FW Ver: 03.00.11(AAVV.221)b4; Fix Version: 03.00.11(AAVV.221)b6.
- Problem category: Design issue; bug analysis: No spec defined.
- Testcase: EMS1-6853.
- Issue detail: YAML, NeoX RateLimit config, and REST `/profile/RateLimitProfile/{profilename}` did not expose per-VLAN egress rate-limit settings even though CLI supports `vlan <1-4094> egress active` and `vlan <1-4094> egress rate <64-10000000>`.
- Expected: REST/profile config should support per-VLAN egress active/rate parameters.
- Actual: Feature was supported by device CLI but missing from REST schema/config interface.
- Fix note: Add the vlan egress setting.
- Verification focus: EMS1-6853 should show the new per-VLAN egress fields are accepted and applied/read back correctly.

### RM 255185

- Subject: [RestApi]NeoX Config/Profile API uses inconsistent switch values in payload fields and needs unified enable/disable handling.
- Status: Released; assignee: Leaf Yeh; author: Kang.Cheng Chang.
- FW Ver: 03.00.11(AAVV.221)b3; Fix Version: 03.00.11(AAVV.221)b6.
- Problem category: Design issue; bug analysis: User experience.
- Testcase: EMS1-7124.
- Related issues noted in Redmine: RM 254820, RM 254861.
- Issue detail: NeoX config/profile switch-type fields used inconsistent values such as `enable`, `disable`, `active`, `no`, empty string, whitespace, and legacy numeric values. Affected areas include GE config, NNI config, ONT config, ONTAclProfile, ONTSecurityProfile, IGMPGroupPrivilegeProfile, RateLimitProfile, ONTUNIProfile, ONTTemplateProfile, and ONTVoipCommonProfile.
- Expected: Use one consistent switch representation, preferably `enable`/`disable`, or clearly document and validate exceptions.
- Actual: Mixed switch representations made payload behavior unclear and increased REST-to-CLI mapping risk.
- Fix note: Modify setting to input `enable` or `disable` for enablement-related settings, and rename keyname from `inactive` to `active`.
- Verification focus: EMS1-7124 and related profile/config cases should pass with normalized switch values and no legacy ambiguous values.

### RM 255162

- Subject: [RestApi]NeoX GE REST config field profile_aclprofilename is misleading; actual behavior requires ACL profile mode setting.
- Status: Released; assignee: Leaf Yeh; author: Kang.Cheng Chang.
- FW Ver: 03.00.11(AAVV.221)b3; Fix Version: 03.00.11(AAVV.221)b6.
- Problem category: Design issue; bug analysis: No spec defined.
- Testcase: EMS1-7120 in Redmine; screenshot also maps this issue to EMS1-7119.
- Issue detail: REST parameter `profile_aclprofilename` suggested users should provide an ACL profile name, but the device requires ACL profile mode to be set to `profile` first.
- Payload observed: `{ "Content": { "profile_aclprofilename": "cli_test" } }`.
- Actual CLI result: `acl cli_test` returned `error: please set Acl-profile mode: profile`.
- Expected: API field name and behavior should be clarified/corrected. If intended to configure ACL profile mode, it should accept/set the mode value such as `profile` instead of misleading users to send a profile name.
- b5 note: Redmine notes said the bug still existed on 03.00.11(AAVV.221)b5.
- Fix note: Add the command for ACL profile mode.
- Verification focus: EMS1-7120 and EMS1-7119 should verify ACL profile mode is configured before/with ACL profile name behavior.

### RM 255125

- Subject: [RestApi]NeoX GE REST config returns Success but vlantrunk_subnet_list is not applied to device.
- Status: Released; assignee: Leaf Yeh; author: Kang.Cheng Chang.
- FW Ver: 03.00.11(AAVV.221)b3; Fix Version: 03.00.11(AAVV.221)b6.
- Problem category: BAT; bug analysis: No spec defined.
- Testcase: EMS1-7120.
- Issue detail: POST to NeoX GE 1-39 returned `{ "retstatus": "Success", "retresult": "" }`, but CLI verification showed `vlantrunk_subnet_list` was not applied.
- Payload focus: `vlantrunk_subnet_list` with `univid: 1314`, `subnetip: 192.0.2.0`, `subnetmask: 255.255.255.0`, `svid: 1314`.
- Expected CLI: `vlan trunk uni-subnet 192.0.2.0/24 svlan 1314`.
- Actual: Rule missing from `show running-config interface ge 1-39` and `show interface ge 1-39 vlan`.
- Possible cause from report: CLI requires confirmation for per-card setting: `Warning: This is per-card setting, rules will be applied to all ports, please confirm [y/N]`.
- Fix note: Auto-responds with `y` for all `y/n` or `y/N` prompts.
- Verification focus: EMS1-7120 should verify subnet trunk rule appears in CLI after REST success.

### RM 254861

- Subject: [RestAPI][NeoX Config][ONTSecurityProfile] Inconsistent spoofingdisable Parameter Behavior Causes User Confusion.
- Status: Closed; assignee: Leaf Yeh; author: Kang.Cheng Chang.
- FW Ver: 03.00.11(AAVV.221)b3; Fix Version: 03.00.11(AAVV.221)b6.
- Problem category: Design issue; bug analysis: User experience.
- Testcase: EMS1-7160.
- Issue detail: `spoofingdisable` behavior in ONTSecurityProfile was inconsistent and confusing.
- Example payload: `{ "Content": { "fdb": "1023", "spoofingdisable": " " } }`.
- Actual behavior: whitespace value made spoofing status become enable; empty string made spoofing status become disable.
- Expected: Use explicit consistent values such as `enable`/`disable` or return validation error for ambiguous values.
- Fix note: Modify setting to input `enable` or `disable` for enablement-related settings, and rename keyname from `inactive` to `active`.
- Verification focus: EMS1-7160 should verify ONTSecurityProfile no longer depends on whitespace/empty-string behavior.
- 2026-06-23 automation update: min/max payload now uses `spoofingable` with explicit `disable`/`enable` values, matching OpenAPI 20260614.
- 2026-06-23 formal verification: Node3 b6 `test_neox_profile_min_create_readwrite[ONTSecurityProfile]` and `test_neox_profile_max_create_readwrite[ONTSecurityProfile]` both passed.

### RM 254820

- Subject: [RestAPI][NeoX Config][ONTAclProfile] "enable":"no" Configuration Is Applied as Active Status on Device.
- Status: Released; assignee: Leaf Yeh; author: Kang.Cheng Chang.
- FW Ver: 03.00.11(AAVV.221)b2; Fix Version: 03.00.11(AAVV.221)b6.
- Problem category: Design issue; bug analysis: User experience.
- Testcase: EMS1-7140.
- Issue detail: ONTAclProfile REST payload with `"enable": "no"` was still applied as active/enabled on the device.
- Payload focus: `enable: no`, `policy: trust`, `interface: both`, `counter: enable`, `logging: enable`, and ACL match fields including protocol, ports, IP/mask, and MAC addresses.
- Actual CLI: profile appeared enabled/active, e.g. `swagger_test1 |  Y   T  L&W   N   Y ...`.
- Expected: Either apply disabled state correctly when `enable: no`, or return validation/error if the parameter is unsupported or ignored.
- Fix note: Modify setting to input `enable` or `disable` for enablement-related settings, and rename keyname from `inactive` to `active`.
- Verification focus: EMS1-7140 should verify `enable` handling uses explicit enable/disable semantics and device active status matches payload.

## 2026-06-22 Node3 b6 Verification

Command: `.venv\Scripts\python.exe -m pytest --ems-node NODE3 --run-neox-config --archive-allure`

Report:

- TXT: `reports/03.00.11 (AAVV.221) b6/Web_Ems_Rest_Api_03.00.11 (AAVV.221) b6_NeoX-03_NXC400_report_2026-06-22_10-30-53.txt`
- HTML: `reports/03.00.11 (AAVV.221) b6/Web_Ems_Rest_Api_03.00.11 (AAVV.221) b6_NeoX-03_NXC400_report_2026-06-22_10-30-53.html`
- Raw Allure archive: `reports/03.00.11 (AAVV.221) b6/allure-results_2026-06-22_10-30-53`

Overall pytest result: 394 selected, 333 passed, 33 failed, 28 skipped, 41 deselected.

Report summary result: 197 Pass / 30 Fail.

Watchlist testcase results:

- EMS1-6853: Pass (`test_post_profile_by_ratelimitprofile`).
- EMS1-7119: Pass (`test_ge_config_min_create_readwrite`).
- EMS1-7120: Fail (`test_ge_config_max_create_readwrite`), missing GE running-config lines for DHCP l2agent ip-mac-binding and LLDP system TLVs. The same CLI report shows `vlan trunk uni-untag subnet 192.0.2.0/24 svlan 1314 spbit 3` is present.
- EMS1-7124: Fail (`test_nni_config_max_create_readwrite`), REST response body contained `retval: y :   % Invalid command "y"`.
- EMS1-7140: Fail (`test_neox_profile_max_create_readwrite[ONTAclProfile]`), REST response `retresult: Invalid JSON input`.
- EMS1-7160: 2026-06-22 b6 run failed with old payload (`Invalid field: spoofingdisable`); 2026-06-23 formal Node3 b6 retest passed for both min and max ONTSecurityProfile create/readwrite after payload correction.

Related evidence:

- NeoX RateLimitProfile min/max still failed with `Invalid JSON input`, so RM 255423 should not be marked fully verified even though EMS1-6853 passed.
- GE max request did not include a `line-id` field, and CLI `Port-Line-ID` was blank, so RM 255427 needs a targeted retest or payload update before it can be verified.
- GE max did apply the subnet trunk line, so RM 255125's core symptom appears improved; the testcase remains red due to other expected tokens.
## Follow-up Check Rule

After a new test report is available:

1. Match each `Testcase ID(s)` against the latest report result.
2. Mark `Verification result` as `Verified fixed` only when all listed testcase IDs pass and no related failure evidence remains in CLI/readback verification.
3. Mark `Still failing` when any listed testcase ID fails with the same symptom.
4. Mark `Needs manual review` when the testcase is skipped, not run, blocked by environment, or the report failure is unrelated to the Redmine subject.

## Report Mapping Notes

- RM 255427, RM 255162, and RM 255125 all touch GE config and may all depend on EMS1-7120 results.
- RM 255162 also appeared with EMS1-7119 in the screenshot, so verify both min and max GE config behavior when possible.
- RM 255185 is broad switch-value cleanup; if EMS1-7124 passes but related profile cases fail with the same switch semantics, keep it as `Needs manual review` instead of marking fully fixed.
- RM 254861 Redmine status is Closed and custom Fix Version is b6; formal Node3 b6 retest passed on 2026-06-23 after automation payload correction.