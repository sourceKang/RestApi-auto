from __future__ import annotations

import pytest

from cases.endpoint_cases import MUTATING_ENDPOINTS, READ_ENDPOINTS
from tests.support.ge_cli_config import (
    monitor_ge_patch_transition,
    running_config_from_result,
    wait_for_ge_cli_config,
)


PROVISION_READ_CASES = [case for case in READ_ENDPOINTS if case.domain == "provision"]
PROVISION_ONT_READ_CASES = [case for case in PROVISION_READ_CASES if case.name.startswith("ont_service")]
PROVISION_GE_READ_CASES = [case for case in PROVISION_READ_CASES if case.name.startswith("ge_service")]
PROVISION_MUTATING_CASES = [case for case in MUTATING_ENDPOINTS if case.domain == "provision"]


@pytest.fixture(scope="module")
def ont_provision_seed_data(prepared_ont_inventory):
    yield prepared_ont_inventory


@pytest.fixture(scope="session")
def ont_mutating_workflow_template(prepared_ont_inventory, temporary_ont_template):
    expected = str(temporary_ont_template)
    if prepared_ont_inventory != expected:
        pytest.fail(
            "ONT mutating workflow requires this run's temporary template: "
            f"expected={expected}, actual={prepared_ont_inventory}"
        )
    return temporary_ont_template


@pytest.fixture(scope="module")
def ge_provision_seed_data(prepared_ge_service):
    yield prepared_ge_service


@pytest.fixture(scope="session")
def ge_mutating_workflow_template(prepared_ge_service, temporary_ge_template):
    expected = str(temporary_ge_template)
    if prepared_ge_service != expected:
        pytest.fail(
            "GE mutating workflow requires this run's temporary template: "
            f"expected={expected}, actual={prepared_ge_service}"
        )
    return temporary_ge_template


@pytest.mark.provision
@pytest.mark.readwrite
@pytest.mark.parametrize("case", PROVISION_ONT_READ_CASES, ids=lambda case: case.name)
def test_ont_provision_read_endpoints_readwrite(services, readwrite_session, ont_provision_seed_data, case):
    services.provision.verify_read_success(
        readwrite_session,
        case,
        "readwrite",
        ont_template=ont_provision_seed_data,
    )


@pytest.mark.provision
@pytest.mark.readwrite
@pytest.mark.parametrize("case", PROVISION_GE_READ_CASES, ids=lambda case: case.name)
def test_ge_provision_read_endpoints_readwrite(services, readwrite_session, ge_provision_seed_data, case):
    services.provision.verify_read_success(
        readwrite_session,
        case,
        "readwrite",
        ge_template=ge_provision_seed_data,
    )


@pytest.mark.provision
@pytest.mark.readonly
@pytest.mark.parametrize("case", PROVISION_ONT_READ_CASES, ids=lambda case: case.name)
def test_ont_provision_read_endpoints_readonly(services, readonly_session, ont_provision_seed_data, case):
    services.provision.verify_read_success(
        readonly_session,
        case,
        "readonly",
        ont_template=ont_provision_seed_data,
    )


@pytest.mark.provision
@pytest.mark.readonly
@pytest.mark.parametrize("case", PROVISION_GE_READ_CASES, ids=lambda case: case.name)
def test_ge_provision_read_endpoints_readonly(services, readonly_session, ge_provision_seed_data, case):
    services.provision.verify_read_success(
        readonly_session,
        case,
        "readonly",
        ge_template=ge_provision_seed_data,
    )


@pytest.mark.provision
@pytest.mark.noaccess
@pytest.mark.parametrize("case", PROVISION_READ_CASES, ids=lambda case: case.name)
def test_provision_read_endpoints_noaccess(services, noaccess_session, case):
    services.provision.verify_read_rejected(noaccess_session, case)


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readonly
@pytest.mark.parametrize("case", PROVISION_MUTATING_CASES, ids=lambda case: case.name)
def test_mutating_endpoints_reject_readonly(services, readonly_session, case):
    services.provision.verify_mutation_rejected(readonly_session, case, "readonly")


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.noaccess
@pytest.mark.parametrize("case", PROVISION_MUTATING_CASES, ids=lambda case: case.name)
def test_mutating_endpoints_reject_noaccess(services, noaccess_session, case):
    services.provision.verify_mutation_rejected(noaccess_session, case, "noaccess")


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_post_ont_service_by_sn(
    services,
    readwrite_session,
    temporary_ont_template,
    ont_service_workflow_state,
):
    ont_service_workflow_state.begin_post(str(temporary_ont_template))
    try:
        services.provision.verify_ont_service_post(
            readwrite_session,
            ont_template=temporary_ont_template,
        )
    except Exception as error:
        ont_service_workflow_state.fail_post(error)
        raise
    ont_service_workflow_state.complete_post()


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_put_ont_service_by_sn(services, readwrite_session, ont_mutating_workflow_template):
    services.provision.verify_ont_service_put(
        readwrite_session,
        ont_template=ont_mutating_workflow_template,
    )


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_patch_ont_service_by_sn(services, readwrite_session, ont_mutating_workflow_template):
    services.provision.verify_ont_service_patch(
        readwrite_session,
        ont_template=ont_mutating_workflow_template,
    )


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_delete_ont_service_by_sn(
    services,
    readwrite_session,
    ont_mutating_workflow_template,
    ont_service_workflow_state,
):
    services.provision.verify_ont_service_delete(
        readwrite_session,
        ont_template=ont_mutating_workflow_template,
    )
    ont_service_workflow_state.mark_deleted()


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_post_ge_service_by_port(
    services,
    readwrite_session,
    temporary_ge_template,
    env_config,
    ge_service_workflow_state,
):
    ge_service_workflow_state.begin_post(str(temporary_ge_template))
    try:
        payload = services.provision.verify_ge_service_post(
            readwrite_session,
            ge_template=temporary_ge_template,
        )
        ge_service_workflow_state.complete_post()
        info = payload["geservice"]
        wait_for_ge_cli_config(
            env_config,
            temporary_ge_template.definition,
            telephone=info["Tel"],
            port_name=info["PortName"],
            attachment_name="EMS1-6661 POST Success CLI verification",
            timeout=120,
            interval=10,
        )
        ge_service_workflow_state.complete_cli()
    except Exception as error:
        if ge_service_workflow_state.post_succeeded:
            ge_service_workflow_state.fail_cli(error)
        else:
            ge_service_workflow_state.fail_post(error)
        raise


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_put_ge_service_by_serviceid(
    services,
    readwrite_session,
    ge_mutating_workflow_template,
    env_config,
    ge_service_workflow_state,
):
    try:
        payload = services.provision.verify_ge_service_put(
            readwrite_session,
            ge_template=ge_mutating_workflow_template,
        )
        info = payload["geservice"]
        cli_result = wait_for_ge_cli_config(
            env_config,
            ge_mutating_workflow_template.definition,
            telephone=info["Tel"],
            port_name=info["PortName"],
            attachment_name="EMS1-6662 PUT Success CLI verification",
            timeout=120,
            interval=10,
            consecutive_stable_successes=2,
        )
        ge_service_workflow_state.complete_put(
            running_config_from_result(
                cli_result,
                env_config.dut.ge_slot_id,
                env_config.dut.ge_port_id,
            )
        )
    except Exception as error:
        ge_service_workflow_state.fail_put(error)
        raise


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_patch_ge_service_by_serviceid(
    services,
    readwrite_session,
    ge_mutating_workflow_template,
    env_config,
    ge_service_workflow_state,
):
    if ge_service_workflow_state.put_failure:
        pytest.skip(f"Blocked because EMS1-6662 PUT failed: {ge_service_workflow_state.put_failure}")
    if not ge_service_workflow_state.put_succeeded or not ge_service_workflow_state.put_cli_verified:
        pytest.skip("Blocked because EMS1-6662 PUT and CLI verification did not complete in this selection.")

    expected_port_name = f"modify_{env_config.dut.ge_port_name}"
    expected_telephone = f"{env_config.dut.ge_telephone}0123"

    def transition_monitor(patch_action, state_reader):
        result = monitor_ge_patch_transition(
            env_config,
            baseline_running_config=ge_service_workflow_state.put_running_config,
            port_name=expected_port_name,
            telephone=expected_telephone,
            patch_action=patch_action,
            state_reader=state_reader,
            timeout=120,
            interval=2,
            success_evidence_grace=20,
        )
        return result.final_service

    try:
        payload = services.provision.verify_ge_service_patch(
            readwrite_session,
            ge_template=ge_mutating_workflow_template,
            transition_monitor=transition_monitor,
        )
        info = payload["geservice"]
        wait_for_ge_cli_config(
            env_config,
            ge_mutating_workflow_template.definition,
            telephone=info["Tel"],
            port_name=info["PortName"],
            attachment_name="EMS1-6663 PATCH final CLI verification",
            timeout=120,
            interval=10,
        )
        ge_service_workflow_state.complete_patch()
    except Exception as error:
        ge_service_workflow_state.fail_patch(error)
        raise


@pytest.mark.provision
@pytest.mark.mutating
@pytest.mark.readwrite
def test_delete_ge_service_by_serviceid(
    services,
    readwrite_session,
    ge_mutating_workflow_template,
    ge_service_workflow_state,
):
    if ge_service_workflow_state.patch_failure:
        pytest.skip(f"Blocked because EMS1-6663 PATCH failed: {ge_service_workflow_state.patch_failure}")
    if not ge_service_workflow_state.patch_succeeded:
        pytest.skip("Blocked because EMS1-6663 PATCH did not complete in this selection.")
    services.provision.verify_ge_service_delete(readwrite_session, ge_template=ge_mutating_workflow_template)
    ge_service_workflow_state.mark_deleted()
