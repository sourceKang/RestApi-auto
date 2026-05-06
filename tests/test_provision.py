from __future__ import annotations

import pytest

from cases.endpoint_cases import MUTATING_ENDPOINTS, READ_ENDPOINTS
from utils.cleanup import CleanupRegistry


PROVISION_READ_CASES = [case for case in READ_ENDPOINTS if case.domain == "provision"]
PROVISION_MUTATING_CASES = [case for case in MUTATING_ENDPOINTS if case.domain == "provision"]


@pytest.fixture(scope="module")
def provision_seed_data(provision_service, session_manager):
    registry = CleanupRegistry()
    with session_manager.credentials_session(provision_service.env_config.readwrite) as session_id:
        provision_service.ensure_seed_data(session_id, registry)
        yield


@pytest.mark.provision
@pytest.mark.readwrite
@pytest.mark.parametrize("case", PROVISION_READ_CASES, ids=lambda case: case.name)
def test_provision_read_endpoints_readwrite(provision_service, readwrite_session, provision_seed_data, case):
    provision_service.verify_read_success(readwrite_session, case, "readwrite")


@pytest.mark.provision
@pytest.mark.readonly
@pytest.mark.parametrize("case", PROVISION_READ_CASES, ids=lambda case: case.name)
def test_provision_read_endpoints_readonly(provision_service, readonly_session, provision_seed_data, case):
    provision_service.verify_read_success(readonly_session, case, "readonly")


@pytest.mark.provision
@pytest.mark.noaccess
@pytest.mark.parametrize("case", PROVISION_READ_CASES, ids=lambda case: case.name)
def test_provision_read_endpoints_noaccess(provision_service, noaccess_session, case):
    provision_service.verify_read_rejected(noaccess_session, case)


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.parametrize("case", PROVISION_MUTATING_CASES, ids=lambda case: case.name)
def test_mutating_endpoints_reject_readonly(provision_service, readonly_session, case):
    provision_service.verify_mutation_rejected(readonly_session, case, "readonly")


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.parametrize("case", PROVISION_MUTATING_CASES, ids=lambda case: case.name)
def test_mutating_endpoints_reject_noaccess(provision_service, noaccess_session, case):
    provision_service.verify_mutation_rejected(noaccess_session, case, "noaccess")


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_service_crud_readwrite(provision_service, readwrite_session, cleanup_registry):
    provision_service.verify_ont_service_crud(readwrite_session, cleanup_registry)


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_ge_service_crud_readwrite(provision_service, readwrite_session, cleanup_registry):
    provision_service.verify_ge_service_crud(readwrite_session, cleanup_registry)
