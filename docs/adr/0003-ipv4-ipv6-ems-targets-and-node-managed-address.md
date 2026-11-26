# ADR 0003: Separate IPv4/IPv6 EMS targets and a per-node managed address family

## Context

From 2026-11 the lab tests EMS over both IPv4 and IPv6. Two independent things can be IPv4 or IPv6:

1. The address the tests use to reach EMS (`ems.targets.<name>.rest_api_url`).
2. The address EMS manages a node by. EMS keeps one management address per node, and REST fields such as `IPAddress`, the `geservicefilter` `IP` key and alarm `DevIP` carry that address.

Before this change both were single values. On 2026-11-20 the `ubuntu` URL was switched to IPv6 in place, so IPv4 and IPv6 runs landed in the same `<version>_ubuntu` report folder. After the .8 EMS was reinstalled (b17, 2026-11-19) it managed NODE3 by `2001:2:169:0:fad4:a3ff:fec9:e1b0` while NODE1 stayed on IPv4; `test_targets.yaml` still had NODE3's `device_ip: 192.168.169.58`, and the NODE3 full run reported 10 failures and 14 skips (device/slot `IPAddress` mismatch, GE port and ONT readiness, `geservicefilter` by IP), none of them an API defect.

## Decision

- **EMS URL by target.** `configs/ems.yaml` keeps `ubuntu` on the IPv4 URL and adds `ubuntu_ipv6` for the same server over IPv6. Reports go to `reports/<version>_<target>/`, so IPv4 and IPv6 runs stay apart in reports, `formal_runs.yaml` and comparisons.
- **Node managed address per node.** A node in `test_targets.yaml` may set `device_ip_v6` and `managed_ip_family` (`ipv4` default, or `ipv6`). `EMS_NODE_IP_FAMILY` overrides it for one run. `config_loader.settings.load_environment` sets `dut.device_ip` to the managed address and keeps the node's own IPv4 address in `dut.device_ip_v4`; `ssh_host` still defaults to the IPv4 `device_ip`, so CLI access does not change.
- It is a node setting, not a target setting, because it describes how the node was added to EMS: the same node can be reached through `ubuntu` or `ubuntu_ipv6` while EMS manages it by one address.
- **Preflight check.** After the device inventory check, `services.preflight` compares EMS's `IPAddress` for the node with `dut.device_ip` (compared as IP addresses, so other valid spellings match). A mismatch stops the run before any test with the actual address and the setting to change. A response without `IPAddress` is not judged.
- **Device CLI output** (the remote console `inband` line) shows the node's own IPv4 address and is checked against `device_ip_v4`.
- **Alarm DevIP** is the managed address: on b17 the alarms EMS holds for IPv6-managed NODE3 carry `DevIP: 2001:2:169:0:fad4:a3ff:fec9:e1b0`, so the alarm `KeyWord` filter and DevIP assertion keep using `dut.device_ip`. Device traps (e.g. Login Success) reach EMS only if the node's SNMP trap destination matches how EMS manages it; NODE3's trap destinations are IPv4 only (`192.168.128.8`), and on 2026-11-24 no Login Success alarm was recorded for it under IPv4 or IPv6, so the alarm lifecycle cases skip until that is set up.
- **Reports** add `Node IP Family: ipv4|ipv6` next to `Node IP`. The step comparison (`tools/case_step_diff.py`) masks IPv6 addresses as `<ip>` as it does IPv4, so IPv4 and IPv6 runs of the same case compare without address noise. The IPv6 pattern needs four colons or `::`, so clock times are not masked.

## Alternatives

- Detect the managed family at runtime and switch `device_ip`: rejected. The environment is loaded in more than ten places (fixtures, preflight, report hooks, tools); changing it mid-run would be hidden state, and a wrong setup would be silently accepted instead of reported.
- Put the family on the EMS target: rejected, because NODE1 and NODE3 were managed by different families on the same server at the same time.
- Keep one `ubuntu` target and edit its URL: rejected, it mixes IPv4 and IPv6 results under one report folder and build.

## Consequences

- Switching a node between IPv4 and IPv6 management is done by the user in EMS (re-adding the node); `managed_ip_family` must be changed with it. Until then the preflight reports the mismatch.
- `test_targets.local.yaml` replaces the committed file as a whole, so `device_ip_v6`/`managed_ip_family` must be set in the local copy too.
- TestLink: how IPv4 and IPv6 results are separated (build suffix, platform or notes) is still open; this ADR does not change the import.

## Validation

- Offline: `tests/test_node_ip_family.py` (family selection, env override, config errors, preflight match/mismatch/missing address, IPv4/IPv6 masking); `pytest -m offline`.
- Live: NODE3 full run through `ubuntu_ipv6` with `managed_ip_family: ipv6`, and NODE1 through `ubuntu` on IPv4 (see `docs/work-status.md`).
