from __future__ import annotations

import pytest

from cases import READ_ENDPOINTS

from tests.support.fixtures import prepare_ont_inventory_with_session_rotation
from tests.support.ont_workflow import OntInventoryPreconditionError


INVENTORY_READ_CASES = [case for case in READ_ENDPOINTS if case.domain == "inventory"]
ONT_READ_CASES = [case for case in READ_ENDPOINTS if case.domain == "ont"]
_GE_READINESS_CACHE: set[tuple[str, str, str]] = set()
_GE_SETUP_FAILURES: dict[tuple[str, str, str], str] = {}


@pytest.fixture(scope="session")
def ont_inventory_seed_data(prepared_ont_inventory):
    yield prepared_ont_inventory


@pytest.fixture
def ont_readwrite_session(session_manager, env_config, ont_inventory_seed_data):
    with session_manager.credentials_session(env_config.readwrite) as session_id:
        yield session_id


@pytest.fixture
def ge_inventory_seed_data(request, services, session_manager, env_config, prepared_ge_service):
    case = getattr(getattr(request.node, "callspec", None), "params", {}).get("case")
    if case is None or not str(case.name).startswith("port_"):
        yield
        return

    cache_key = (
        env_config.dut.node_key,
        env_config.dut.ge_slot_id,
        env_config.dut.ge_port_id,
    )
    if cache_key in _GE_READINESS_CACHE:
        yield None
        return
    if cache_key in _GE_SETUP_FAILURES:
        yield _GE_SETUP_FAILURES[cache_key]
        return

    with session_manager.credentials_session(env_config.readwrite) as session_id:
        try:
            services.inventory.wait_for_ge_port_inventory(session_id)
        except AssertionError as error:
            reason = f"GE inventory setup failed: {error}"
            _GE_SETUP_FAILURES[cache_key] = reason
        else:
            reason = None
            _GE_READINESS_CACHE.add(cache_key)
    yield reason


@pytest.fixture
def inventory_readwrite_session(session_manager, env_config, ge_inventory_seed_data):
    assert_ge_inventory_seed_ready(ge_inventory_seed_data)
    with session_manager.credentials_session(env_config.readwrite) as session_id:
        yield session_id


@pytest.mark.inventory
@pytest.mark.readwrite
@pytest.mark.smoke
@pytest.mark.parametrize("case", INVENTORY_READ_CASES, ids=lambda case: case.name)
def test_inventory_read_endpoints_readwrite(services, inventory_readwrite_session, case):
    services.inventory.verify_read_success(inventory_readwrite_session, case, "readwrite")


@pytest.mark.inventory
@pytest.mark.readonly
@pytest.mark.parametrize("case", INVENTORY_READ_CASES, ids=lambda case: case.name)
def test_inventory_read_endpoints_readonly(services, readonly_session, ge_inventory_seed_data, case):
    assert_ge_inventory_seed_ready(ge_inventory_seed_data)
    services.inventory.verify_read_success(readonly_session, case, "readonly")


@pytest.mark.inventory
@pytest.mark.noaccess
@pytest.mark.parametrize("case", INVENTORY_READ_CASES, ids=lambda case: case.name)
def test_inventory_read_endpoints_noaccess(services, noaccess_session, case):
    services.inventory.verify_noaccess_rejected(noaccess_session, case)


def assert_ge_inventory_seed_ready(setup_failure: str | None) -> None:
    if setup_failure:
        pytest.fail(setup_failure)


@pytest.mark.ont
@pytest.mark.readwrite
@pytest.mark.smoke
def test_ont_inventory_ready_after_post(
    services,
    session_manager,
    env_config,
    request,
    ont_service_workflow_state,
):
    if ont_service_workflow_state.post_failure:
        pytest.skip(
            "Blocked because EMS1-6666 POST failed: "
            f"{ont_service_workflow_state.post_failure}"
        )
    try:
        prepare_ont_inventory_with_session_rotation(
            services,
            session_manager,
            env_config,
            lambda: request.getfixturevalue("temporary_ont_template"),
            workflow_state=ont_service_workflow_state,
        )
    except OntInventoryPreconditionError as error:
        ont_service_workflow_state.block_readiness_precondition(error)
        pytest.skip(f"ONT inventory precondition not met: {error}")
    except AssertionError as error:
        ont_service_workflow_state.fail_readiness(error)
        pytest.fail(f"ONT workflow readiness failed: {error}")


@pytest.mark.ont
@pytest.mark.readwrite
@pytest.mark.smoke
@pytest.mark.parametrize("case", ONT_READ_CASES, ids=lambda case: case.name)
def test_ont_read_endpoints_readwrite(services, ont_readwrite_session, ont_inventory_seed_data, case):
    services.inventory.verify_read_success(
        ont_readwrite_session,
        case,
        "readwrite",
        ont_template=ont_inventory_seed_data,
    )


@pytest.mark.ont
@pytest.mark.readonly
@pytest.mark.parametrize("case", ONT_READ_CASES, ids=lambda case: case.name)
def test_ont_read_endpoints_readonly(services, readonly_session, ont_inventory_seed_data, case):
    services.inventory.verify_read_success(
        readonly_session,
        case,
        "readonly",
        ont_template=ont_inventory_seed_data,
    )


@pytest.mark.ont
@pytest.mark.noaccess
@pytest.mark.parametrize("case", ONT_READ_CASES, ids=lambda case: case.name)
def test_ont_read_endpoints_noaccess(services, noaccess_session, case):
    services.inventory.verify_noaccess_rejected(noaccess_session, case)
