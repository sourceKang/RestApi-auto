# Current Test Order Baseline

This baseline was captured before the automation architecture refactor.  It
exists so future changes can intentionally preserve or change collection order,
testcase id registration, and txt report output.

The baseline was verified with `pytest --collect-only -q` on Python 3.13.0 and
pytest 8.2.0.  Current collection count: 240 tests.

## File Order

1. `tests/test_alarm.py`
2. `tests/test_auth_matrix.py`
3. `tests/test_automation_registry.py`
4. `tests/test_config.py`
5. `tests/test_hardware_config.py`
6. `tests/test_inventory.py`
7. `tests/test_legacy_registry.py`
8. `tests/test_profiles.py`
9. `tests/test_provision.py`
10. `tests/test_regression_registry.py`
11. `tests/test_remote.py`
12. `tests/test_reporting.py`
13. `tests/test_session.py`
14. `tests/test_topology_v2_config.py`
15. `tests/test_zz_invalid_params.py`
16. `tests/test_zzz_permission_summaries.py`

## Fixed During Refactor

- Legacy txt report content and formatting.
- EMS testcase ids such as `EMS1-6640`.
- Permission summary ids `PERM-RO` and `PERM-NA`.
- RAD auth matrix summary ids `RAD-RW`, `RAD-RO`, and `RAD-NA`.

## Next Target

Promote `configs/test_plan_legacy.yaml` from a baseline into the execution-plan
source of truth, then use it to control test ordering, regression grouping, and
report grouping explicitly.
