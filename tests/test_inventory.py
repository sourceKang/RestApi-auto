from __future__ import annotations

import pytest

from cases import READ_ENDPOINTS


INVENTORY_READ_CASES = [case for case in READ_ENDPOINTS if case.domain == "inventory"]
ONT_READ_CASES = [case for case in READ_ENDPOINTS if case.domain == "ont"]
_ONT_READINESS_CACHE: set[tuple[str, str, str, str]] = set()


@pytest.fixture(scope="session")
def ont_inventory_seed_data(services, session_manager, env_config):
    cache_key = (
        env_config.dut.node_key,
        env_config.dut.slot_id,
        env_config.dut.port_id,
        env_config.dut.ont_sn,
    )
    if cache_key in _ONT_READINESS_CACHE:
        yield
        return

    with session_manager.credentials_session(env_config.readwrite) as session_id:
        services.inventory.ensure_ont_inventory_ready(session_id)
        _ONT_READINESS_CACHE.add(cache_key)
        yield


@pytest.mark.inventory
@pytest.mark.readwrite
@pytest.mark.smoke
@pytest.mark.parametrize("case", INVENTORY_READ_CASES, ids=lambda case: case.name)
def test_inventory_read_endpoints_readwrite(services, readwrite_session, case):
    services.inventory.verify_read_success(readwrite_session, case, "readwrite")


@pytest.mark.inventory
@pytest.mark.readonly
@pytest.mark.parametrize("case", INVENTORY_READ_CASES, ids=lambda case: case.name)
def test_inventory_read_endpoints_readonly(services, readonly_session, case):
    services.inventory.verify_read_success(readonly_session, case, "readonly")


@pytest.mark.inventory
@pytest.mark.noaccess
@pytest.mark.parametrize("case", INVENTORY_READ_CASES, ids=lambda case: case.name)
def test_inventory_read_endpoints_noaccess(services, noaccess_session, case):
    services.inventory.verify_noaccess_rejected(noaccess_session, case)


@pytest.mark.ont
@pytest.mark.readwrite
@pytest.mark.smoke
@pytest.mark.parametrize("case", ONT_READ_CASES, ids=lambda case: case.name)
def test_ont_read_endpoints_readwrite(services, readwrite_session, ont_inventory_seed_data, case):
    services.inventory.verify_read_success(readwrite_session, case, "readwrite")


@pytest.mark.ont
@pytest.mark.readonly
@pytest.mark.parametrize("case", ONT_READ_CASES, ids=lambda case: case.name)
def test_ont_read_endpoints_readonly(services, readonly_session, ont_inventory_seed_data, case):
    services.inventory.verify_read_success(readonly_session, case, "readonly")


@pytest.mark.ont
@pytest.mark.noaccess
@pytest.mark.parametrize("case", ONT_READ_CASES, ids=lambda case: case.name)
def test_ont_read_endpoints_noaccess(services, noaccess_session, case):
    services.inventory.verify_noaccess_rejected(noaccess_session, case)
