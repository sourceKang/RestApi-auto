# Current Test Order

This document describes the current pytest collection order, testcase id
registration, and txt report output contracts for the REST API test framework.

The current collection was verified with `pytest --collect-only --skip-dut-preflight -q`.
Current collection count: 251 tests.

## File Order

1. `tests/test_alarm.py`
2. `tests/test_auth_matrix.py`
3. `tests/test_case_registry.py`
4. `tests/test_case_catalog.py`
5. `tests/test_case_metadata.py`
6. `tests/test_config.py`
7. `tests/test_diagnostics.py`
8. `tests/test_endpoint_case_helper.py`
9. `tests/test_hardware_config.py`
10. `tests/test_inventory.py`
11. `tests/test_preflight.py`
12. `tests/test_profiles.py`
13. `tests/test_provision.py`
14. `tests/test_regression_registry.py`
15. `tests/test_remote.py`
16. `tests/test_reporting.py`
17. `tests/test_service_bundle.py`
18. `tests/test_session.py`
19. `tests/test_topology_v2_config.py`
20. `tests/test_zz_invalid_params.py`
21. `tests/test_zzz_permission_summaries.py`

## Fixed Contracts

- EMS txt report content and formatting.
- EMS testcase ids such as `EMS1-6640`.
- Permission summary ids `PERM-RO` and `PERM-NA`.
- RAD auth matrix summary ids `RAD-RW`, `RAD-RO`, and `RAD-NA`.

## Next Target

Promote `configs/test_plan.yaml` from a baseline into the execution-plan source
of truth, then use it to control test ordering, regression grouping, and report
grouping explicitly.
