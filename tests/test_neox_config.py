from __future__ import annotations

import pytest


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
def test_ge_config_set_and_clear_readwrite(neox_config_service, readwrite_session, cleanup_registry):
    neox_config_service.verify_ge_config_set_and_clear(readwrite_session, cleanup_registry)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_nni_config_set_and_clear_readwrite(neox_config_service, readwrite_session, cleanup_registry):
    neox_config_service.verify_nni_config_set_and_clear(readwrite_session, cleanup_registry)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_vlan_create_and_delete_readwrite(neox_config_service, readwrite_session, cleanup_registry):
    neox_config_service.verify_vlan_create_and_delete(readwrite_session, cleanup_registry)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_create_and_delete_readwrite(neox_config_service, readwrite_session, cleanup_registry):
    neox_config_service.verify_ont_create_and_delete(readwrite_session, cleanup_registry)
