from __future__ import annotations

from dataclasses import dataclass

from cases.endpoint_cases import MUTATING_ENDPOINTS, READ_ENDPOINTS
from cases.neox_legacy import legacy_test_cases


@dataclass(frozen=True)
class TestCaseRecord:
    case_id: str
    name: str
    domain: str
    role: str | None = None
    source: str = "legacy"
    markers: tuple[str, ...] = ()


def _endpoint_records() -> tuple[TestCaseRecord, ...]:
    records: list[TestCaseRecord] = []
    for case in [*READ_ENDPOINTS, *MUTATING_ENDPOINTS]:
        if not case.case_id:
            continue
        records.append(
            TestCaseRecord(
                case_id=case.case_id,
                name=case.name,
                domain=case.domain,
                source="cases.endpoint_cases",
                markers=(case.domain,),
            )
        )
    return tuple(records)


# Direct registrations that are currently attached inside test bodies instead
# of EndpointCase metadata.  Keeping them here makes the report/test id contract
# explicit before the test files are reorganized into domain services.
DIRECT_CASES: tuple[TestCaseRecord, ...] = (
    TestCaseRecord("EMS1-6640", "test_get_sessionid", "session", markers=("session", "smoke")),
    TestCaseRecord("EMS1-6651", "test_delete_sessionid", "session", markers=("session",)),
    TestCaseRecord("EMS1-7020", "test_usersession_post_invalid_param_should_return_error", "session", markers=("session",)),
    TestCaseRecord("EMS1-7021", "test_usersession_delete_invalid_param_should_return_error", "session", markers=("session",)),
    TestCaseRecord("EMS1-6654", "test_get_active_alarm_by_id", "alarm", markers=("alarm",)),
    TestCaseRecord("EMS1-6658", "test_patch_active_alarm_by_id", "alarm", markers=("alarm", "mutating")),
    TestCaseRecord("EMS1-6659", "test_delete_active_alarm_by_id", "alarm", markers=("alarm", "mutating")),
    TestCaseRecord("EMS1-6670", "test_get_history_alarm_by_id", "alarm", markers=("alarm",)),
    TestCaseRecord("EMS1-6674", "test_delete_history_alarm_by_id", "alarm", markers=("alarm", "alarm_delete", "destructive")),
    TestCaseRecord("EMS1-7022", "test_post_remote_console_invalid_param_should_return_error", "remote", markers=("remoteconsole", "noaccess")),
    TestCaseRecord("EMS1-7023", "test_ont_service_post_various_invalid_parameters_should_return_error", "provision", markers=("provision", "mutating")),
    TestCaseRecord("EMS1-7024", "test_ge_service_post_various_invalid_parameters_should_return_error", "provision", markers=("provision", "mutating")),
    TestCaseRecord("EMS1-7029", "test_active_alarm_various_invalid_parameters_should_return_error", "alarm", markers=("alarm", "noaccess")),
    TestCaseRecord("EMS1-7030", "test_history_alarm_various_invalid_parameters_should_return_error", "alarm", markers=("alarm", "mutating")),
    TestCaseRecord("EMS1-7031", "test_get_device_name_with_invalid_parameters_should_return_error", "inventory", markers=("inventory",)),
    TestCaseRecord("EMS1-7032", "test_slot_api_with_invalid_parameters_should_return_error", "inventory", markers=("inventory",)),
    TestCaseRecord("EMS1-7033", "test_port_api_with_invalid_parameters_should_return_error", "inventory", markers=("inventory",)),
    TestCaseRecord("EMS1-7034", "test_ont_api_with_invalid_parameters_should_return_error", "ont", markers=("ont",)),
)

SUMMARY_CASES: tuple[TestCaseRecord, ...] = (
    TestCaseRecord("PERM-RO", "readonly_permission_summary", "permission", role="readonly", source="summary", markers=("summary",)),
    TestCaseRecord("PERM-NA", "noaccess_permission_summary", "permission", role="noaccess", source="summary", markers=("summary",)),
)

RAD_SUMMARY_CASES: tuple[TestCaseRecord, ...] = (
    TestCaseRecord("RAD-RW", "rad_external_readwrite_summary", "authmatrix", role="readwrite", source="summary", markers=("authmatrix",)),
    TestCaseRecord("RAD-RO", "rad_external_readonly_summary", "authmatrix", role="readonly", source="summary", markers=("authmatrix",)),
    TestCaseRecord("RAD-NA", "rad_external_noaccess_summary", "authmatrix", role="noaccess", source="summary", markers=("authmatrix",)),
)

AUTOMATED_CASES: tuple[TestCaseRecord, ...] = (
    *_endpoint_records(),
    *DIRECT_CASES,
    *SUMMARY_CASES,
    *RAD_SUMMARY_CASES,
)


def automated_case_ids() -> set[str]:
    return {case.case_id for case in AUTOMATED_CASES}


def legacy_case_name_by_id() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for case in legacy_test_cases():
        case_ids = case.get("case_ids") or []
        if case_ids:
            mapping[str(case_ids[0])] = str(case.get("legacy_name", case_ids[0]))
    return mapping


def legacy_case_order() -> dict[str, int]:
    order: dict[str, int] = {}
    for index, case in enumerate(legacy_test_cases()):
        case_ids = case.get("case_ids") or []
        if case_ids:
            order.setdefault(str(case_ids[0]), index)
    return order


def permission_summary_specs() -> tuple[tuple[str, str, str], ...]:
    return tuple((case.case_id, str(case.role), case.name) for case in SUMMARY_CASES)
