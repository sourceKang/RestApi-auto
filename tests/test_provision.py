from __future__ import annotations

import pytest

from cases.endpoint_cases import MUTATING_ENDPOINTS, READ_ENDPOINTS
from cases.payloads import ge_service_modified_payload, ge_service_payload, ont_service_modified_payload, ont_service_payload
from cases.neox_legacy import profile_definition_by_name
from utils.assertions import assert_api_failure, assert_api_success
from utils.case_metadata import attach_case_id
from utils.names import unique_name


PROVISION_READ_CASES = [case for case in READ_ENDPOINTS if case.domain == "provision"]
PROVISION_MUTATING_CASES = [case for case in MUTATING_ENDPOINTS if case.domain == "provision"]


@pytest.mark.provision
@pytest.mark.readwrite
@pytest.mark.parametrize("case", PROVISION_READ_CASES, ids=lambda case: case.name)
def test_provision_read_endpoints_readwrite(api_client, env_config, readwrite_session, case):
    attach_case_id(case.case_id, case.name)
    name = unique_name(case.name)
    response = api_client.request(
        case.method,
        case.build_path(env_config),
        session=readwrite_session,
        params=case.build_params(env_config, name),
    )
    if response.retstatus == "Fail" and "No data found" in response.retresult:
        pytest.skip(f"{case.name} has no existing data in this EMS environment.")
    assert_api_success(response)


@pytest.mark.provision
@pytest.mark.readonly
@pytest.mark.parametrize("case", PROVISION_READ_CASES, ids=lambda case: case.name)
def test_provision_read_endpoints_readonly(api_client, env_config, readonly_session, case):
    attach_case_id(case.case_id, case.name)
    name = unique_name(case.name)
    response = api_client.request(
        case.method,
        case.build_path(env_config),
        session=readonly_session,
        params=case.build_params(env_config, name),
    )
    if response.retstatus == "Fail" and "No data found" in response.retresult:
        pytest.skip(f"{case.name} has no existing data in this EMS environment.")
    assert_api_success(response)


@pytest.mark.provision
@pytest.mark.noaccess
@pytest.mark.parametrize("case", PROVISION_READ_CASES, ids=lambda case: case.name)
def test_provision_read_endpoints_noaccess(api_client, env_config, noaccess_session, case):
    attach_case_id(case.case_id, case.name)
    name = unique_name(case.name)
    response = api_client.request(
        case.method,
        case.build_path(env_config),
        session=noaccess_session,
        params=case.build_params(env_config, name),
    )
    assert_api_failure(response, accepted_messages=("not authorized", "no access", "permission", "privilege"))


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.parametrize("case", PROVISION_MUTATING_CASES, ids=lambda case: case.name)
def test_mutating_endpoints_reject_readonly(api_client, env_config, readonly_session, case):
    attach_case_id(case.case_id, case.name)
    name = unique_name(case.name)
    response = api_client.request(
        case.method,
        case.build_path(env_config),
        session=readonly_session,
        json=case.build_payload(env_config, name),
    )
    assert_api_failure(response, accepted_messages=("not authorized", "no access", "permission", "privilege"))


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.parametrize("case", PROVISION_MUTATING_CASES, ids=lambda case: case.name)
def test_mutating_endpoints_reject_noaccess(api_client, env_config, noaccess_session, case):
    attach_case_id(case.case_id, case.name)
    name = unique_name(case.name)
    response = api_client.request(
        case.method,
        case.build_path(env_config),
        session=noaccess_session,
        json=case.build_payload(env_config, name),
    )
    assert_api_failure(response, accepted_messages=("not authorized", "no access", "permission", "privilege"))


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_service_crud_readwrite(api_client, env_config, readwrite_session, cleanup_registry):
    attach_case_id("EMS1-6666", "test_post_ont_service_by_sn")
    name = unique_name("ont_service")
    path = f"/ontservice/{env_config.dut.ont_sn}"
    _ensure_profile_by_name(api_client, readwrite_session, cleanup_registry, env_config.dut.ont_template)

    existing = api_client.request("GET", path, session=readwrite_session)
    if existing.retstatus == "Success":
        delete = api_client.request("DELETE", path, session=readwrite_session)
        assert_api_success(delete)

    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))

    create = api_client.request("POST", path, session=readwrite_session, json=ont_service_payload(env_config, name))
    assert_api_success(create)

    get_created = api_client.request("GET", path, session=readwrite_session)
    assert_api_success(get_created)

    update = api_client.request("PUT", path, session=readwrite_session, json=ont_service_modified_payload(env_config, name))
    assert_api_success(update)

    delete = api_client.request("DELETE", path, session=readwrite_session)
    assert_api_success(delete)


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_ge_service_crud_readwrite(api_client, env_config, readwrite_session, cleanup_registry):
    attach_case_id("EMS1-6661", "test_post_ge_service_by_port")
    name = unique_name("ge_service")
    dut = env_config.dut
    port_path = f"/geservice/{dut.device_name}/{dut.ge_slot_id}/{dut.ge_port_id}"
    _ensure_profile_by_name(api_client, readwrite_session, cleanup_registry, dut.ge_template)

    existing = api_client.request("GET", port_path, session=readwrite_session)
    if existing.retstatus == "Success":
        service_id = _ge_service_id(existing.json)
        if service_id:
            delete = api_client.request("DELETE", f"/geservice/{service_id}", session=readwrite_session)
            assert_api_success(delete)

    create = api_client.request("POST", port_path, session=readwrite_session, json=ge_service_payload(env_config, name))
    assert_api_success(create)

    get_created = api_client.request("GET", port_path, session=readwrite_session)
    assert_api_success(get_created)
    service_id = _ge_service_id(get_created.json)
    assert service_id, f"GE service was created but no service id was found: {get_created.json!r}"

    cleanup_registry.add(lambda: api_client.request("DELETE", f"/geservice/{service_id}", session=readwrite_session))

    update = api_client.request(
        "PUT",
        f"/geservice/{service_id}",
        session=readwrite_session,
        json=ge_service_modified_payload(env_config, name),
    )
    assert_api_success(update)

    delete = api_client.request("DELETE", f"/geservice/{service_id}", session=readwrite_session)
    assert_api_success(delete)


def _ge_service_id(payload):
    if not isinstance(payload, dict):
        return None
    retval = payload.get("retval", {})
    if not isinstance(retval, dict):
        return None
    service = retval.get("geserviceinfo", retval)
    if isinstance(service, dict):
        return service.get("GeServiceID") or service.get("geserviceid") or service.get("serviceid")
    return None


def _ensure_profile_by_name(api_client, session_id, cleanup_registry, profilename, seen=None):
    definition = profile_definition_by_name(profilename)
    if definition is None:
        pytest.skip(f"No converted profile data found for prerequisite profile {profilename}.")
    seen = seen or set()
    key = (definition["profiletype"], definition["profilename"])
    if key in seen:
        return
    seen.add(key)

    for dependency in _profile_refs(definition.get("post_profile_info", {})):
        _ensure_profile_by_name(api_client, session_id, cleanup_registry, dependency, seen)

    path = f"/profile/{definition['profiletype']}/{definition['profilename']}"
    existing = api_client.request("GET", path, session=session_id)
    if existing.retstatus == "Success":
        return

    created = api_client.request(
        "POST",
        path,
        session=session_id,
        json={"Content": definition.get("post_profile_info", {})},
    )
    if created.retstatus != "Success":
        pytest.skip(f"Cannot create prerequisite profile {profilename}: {created.json!r}")
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=session_id))


def _profile_refs(value):
    refs = set()
    if isinstance(value, dict):
        for item in value.values():
            refs.update(_profile_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(_profile_refs(item))
    elif isinstance(value, str) and value.startswith("#RestApi"):
        refs.add(value)
    return refs
