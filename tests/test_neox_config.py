from __future__ import annotations

import pytest

from services.neox_config.service import (
    ge_port_payload,
    nni_max_payload,
    nni_min_payload,
    ont_config_payload,
    ont_max_payload,
    ont_min_payload,
    vlan_case,
)
from utils.assertions import assert_api_failure, assert_api_success


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.destructive,
]


def test_neox_target_data_is_configured(neox_config_service):
    neox_config_service.verify_required_target_data()


@pytest.mark.mutating
@pytest.mark.readonly
def test_ge_config_mutation_rejects_readonly(neox_config_service, readonly_session):
    neox_config_service.verify_ge_config_rejected(readonly_session)


@pytest.mark.mutating
@pytest.mark.noaccess
def test_ge_config_mutation_rejects_noaccess(neox_config_service, noaccess_session):
    neox_config_service.verify_ge_config_rejected(noaccess_session)


@pytest.mark.mutating
@pytest.mark.readonly
def test_nni_config_mutation_rejects_readonly(neox_config_service, readonly_session):
    neox_config_service.verify_nni_config_rejected(readonly_session)


@pytest.mark.mutating
@pytest.mark.noaccess
def test_nni_config_mutation_rejects_noaccess(neox_config_service, noaccess_session):
    neox_config_service.verify_nni_config_rejected(noaccess_session)


@pytest.mark.mutating
@pytest.mark.readonly
def test_vlan_config_mutation_rejects_readonly(neox_config_service, readonly_session):
    neox_config_service.verify_vlan_config_rejected(readonly_session)


@pytest.mark.mutating
@pytest.mark.noaccess
def test_vlan_config_mutation_rejects_noaccess(neox_config_service, noaccess_session):
    neox_config_service.verify_vlan_config_rejected(noaccess_session)


@pytest.mark.mutating
@pytest.mark.readonly
def test_ont_config_mutation_rejects_readonly(neox_config_service, readonly_session):
    neox_config_service.verify_ont_config_rejected(readonly_session)


@pytest.mark.mutating
@pytest.mark.noaccess
def test_ont_config_mutation_rejects_noaccess(neox_config_service, noaccess_session):
    neox_config_service.verify_ont_config_rejected(noaccess_session)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ge_config_clear_readwrite(neox_config_service, api_client, readwrite_session, cleanup_registry):
    neox_config_service.verify_node3_target()
    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))
    response = api_client.request("POST", neox_config_service.ge_path(), session=readwrite_session, json=ge_port_payload())
    assert_api_success(response)
    response = api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
    assert_api_success(response)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ge_config_error_readwrite(neox_config_service, api_client, readwrite_session):
    neox_config_service.verify_node3_target()
    response = api_client.request(
        "POST",
        neox_config_service.ge_path(),
        session=readwrite_session,
        json={"Content": {"portenable": "invalid"}},
    )
    assert_api_failure(response, accepted_messages=("invalid json input",))


@pytest.mark.mutating
@pytest.mark.readwrite
def test_nni_config_clear_readwrite(neox_config_service, api_client, readwrite_session, cleanup_registry):
    neox_config_service.verify_node3_target()
    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.nni_path(), session=readwrite_session))
    response = api_client.request("POST", neox_config_service.nni_path(), session=readwrite_session, json=nni_min_payload())
    assert_api_success(response)
    response = api_client.request("DELETE", neox_config_service.nni_path(), session=readwrite_session)
    assert_api_success(response)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_nni_config_min_create_readwrite(neox_config_service, api_client, readwrite_session, cleanup_registry):
    neox_config_service.verify_node3_target()
    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.nni_path(), session=readwrite_session))
    response = api_client.request("POST", neox_config_service.nni_path(), session=readwrite_session, json=nni_min_payload())
    assert_api_success(response)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_nni_config_error_readwrite(neox_config_service, api_client, readwrite_session):
    neox_config_service.verify_node3_target()
    response = api_client.request(
        "POST",
        neox_config_service.nni_path(),
        session=readwrite_session,
        json={"Content": {"portenable": "invalid"}},
    )
    assert_api_failure(response, accepted_messages=("invalid json input",))


@pytest.mark.mutating
@pytest.mark.readwrite
def test_vlan_config_min_create_readwrite(neox_config_service, api_client, readwrite_session, cleanup_registry):
    neox_config_service.verify_node3_target()
    vid, payload = vlan_case("min")
    path = neox_config_service.vlan_path_for_vid(vid)
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    response = api_client.request("POST", path, session=readwrite_session, json=payload)
    assert_api_success(response)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_vlan_config_max_create_readwrite(neox_config_service, api_client, readwrite_session, cleanup_registry):
    neox_config_service.verify_node3_target()
    vid, payload = vlan_case("max")
    path = neox_config_service.vlan_path_for_vid(vid)
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    response = api_client.request("POST", path, session=readwrite_session, json=payload)
    assert_api_success(response)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_vlan_config_clear_readwrite(neox_config_service, api_client, readwrite_session, cleanup_registry):
    neox_config_service.verify_node3_target()
    vid, payload = vlan_case("max")
    path = neox_config_service.vlan_path_for_vid(vid)
    cleanup_registry.add(lambda: api_client.request("DELETE", path, session=readwrite_session))
    response = api_client.request("POST", path, session=readwrite_session, json=payload)
    assert_api_success(response)
    response = api_client.request("DELETE", path, session=readwrite_session)
    assert_api_success(response)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_vlan_config_error_readwrite(neox_config_service, api_client, readwrite_session):
    neox_config_service.verify_node3_target()
    response = api_client.request(
        "POST",
        neox_config_service.vlan_path_for_vid("4094"),
        session=readwrite_session,
        json={"vlanname": "REST_API_BAD_VLAN", "tpid": "invalid-tpid"},
    )
    assert_api_failure(response, accepted_messages=("invalid json input",))


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_min_create_readwrite(neox_config_service, api_client, readwrite_session, cleanup_registry):
    neox_config_service.verify_node3_target()
    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ont_path(), session=readwrite_session))
    response = api_client.request(
        "POST",
        neox_config_service.ont_path(),
        session=readwrite_session,
        json=ont_min_payload(neox_config_service.target()),
    )
    assert_api_success(response)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_max_create_readwrite(neox_config_service, api_client, readwrite_session, cleanup_registry):
    neox_config_service.verify_node3_target()
    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ont_path(), session=readwrite_session))
    response = api_client.request(
        "POST",
        neox_config_service.ont_path(),
        session=readwrite_session,
        json=ont_max_payload(neox_config_service.target()),
    )
    assert_api_success(response)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_clear_readwrite(neox_config_service, api_client, readwrite_session, cleanup_registry):
    neox_config_service.verify_node3_target()
    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ont_path(), session=readwrite_session))
    response = api_client.request(
        "POST",
        neox_config_service.ont_path(),
        session=readwrite_session,
        json=ont_config_payload(neox_config_service.target()),
    )
    assert_api_success(response)
    response = api_client.request("DELETE", neox_config_service.ont_path(), session=readwrite_session)
    assert_api_success(response)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_error_readwrite(neox_config_service, api_client, readwrite_session):
    neox_config_service.verify_node3_target()
    payload = ont_config_payload(neox_config_service.target())
    payload["Content"]["registmethod"] = "invalid"
    response = api_client.request("POST", neox_config_service.ont_path(), session=readwrite_session, json=payload)
    assert_api_failure(response, accepted_messages=("invalid json input",))
