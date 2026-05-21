from __future__ import annotations

import json
from typing import Any

import pytest

from services.neox_config.service import GE_FULL_ACCEPTED_PAYLOAD_FILE, ge_port_payload
from tests.support.neox_cli_verification import (
    missing_tokens,
    neox_cli_credentials,
    run_neox_cli_commands,
    write_neox_cli_verify_report,
)
from utils.assertions import assert_api_success


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
def test_ge_config_clear_readwrite(neox_config_service, readwrite_session, cleanup_registry):
    neox_config_service.verify_ge_config_set_and_clear(readwrite_session, cleanup_registry)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ge_config_min_create_readwrite(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
):
    neox_config_service.verify_required_target_data()
    credentials = neox_cli_credentials(env_config, "GE")

    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))
    api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
    payload = ge_port_payload()
    response = api_client.request("POST", neox_config_service.ge_path(), session=readwrite_session, json=payload)
    assert_api_success(response)

    target = neox_config_service.target()
    command = f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}"
    output_by_command = run_neox_cli_commands(env_config, credentials, [command])
    checks = ge_cli_checks(payload["Content"])
    missing = missing_tokens(output_by_command[command], checks)
    report_path = write_neox_cli_verify_report(
        neox_config_service,
        "ge",
        "min",
        neox_config_service.ge_path(),
        payload,
        response,
        output_by_command,
        {command: checks},
        {command: missing},
        target_extra={"ge_slot_id": target.ge_slot_id, "ge_port_id": target.ge_port_id},
    )

    assert not missing, f"Missing GE running-config lines: {missing}. Report: {report_path}"


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ge_config_max_create_readwrite(
    api_client,
    env_config,
    neox_config_service,
    readwrite_session,
    cleanup_registry,
):
    neox_config_service.verify_required_target_data()
    credentials = neox_cli_credentials(env_config, "GE")

    config = json.loads(GE_FULL_ACCEPTED_PAYLOAD_FILE.read_text(encoding="utf-8"))
    payload = config["payload"]
    expected_lines = config["running_config_visible_lines"]

    cleanup_registry.add(lambda: api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session))
    api_client.request("DELETE", neox_config_service.ge_path(), session=readwrite_session)
    response = api_client.request("POST", neox_config_service.ge_path(), session=readwrite_session, json=payload)
    assert_api_success(response)

    target = neox_config_service.target()
    command = f"show running-config interface ge {target.ge_slot_id}-{target.ge_port_id}"
    output_by_command = run_neox_cli_commands(env_config, credentials, [command])
    missing = missing_tokens(output_by_command[command], expected_lines)
    report_path = write_neox_cli_verify_report(
        neox_config_service,
        "ge",
        "max",
        neox_config_service.ge_path(),
        payload,
        response,
        output_by_command,
        {command: expected_lines},
        {command: missing},
        target_extra={"ge_slot_id": target.ge_slot_id, "ge_port_id": target.ge_port_id},
    )

    assert not missing, f"Missing GE running-config lines: {missing}. Report: {report_path}"


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ge_config_error_readwrite(neox_config_service, readwrite_session):
    neox_config_service.verify_ge_config_invalid_payload(readwrite_session)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_nni_config_clear_readwrite(neox_config_service, readwrite_session, cleanup_registry):
    neox_config_service.verify_nni_config_set_and_clear(readwrite_session, cleanup_registry)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_nni_config_error_readwrite(neox_config_service, readwrite_session):
    neox_config_service.verify_nni_config_invalid_payload(readwrite_session)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_vlan_config_min_create_readwrite(neox_config_service, readwrite_session, cleanup_registry):
    neox_config_service.verify_vlan_case_created(readwrite_session, cleanup_registry, "min")


@pytest.mark.mutating
@pytest.mark.readwrite
def test_vlan_config_max_create_readwrite(neox_config_service, readwrite_session, cleanup_registry):
    neox_config_service.verify_vlan_case_created(readwrite_session, cleanup_registry, "max")


@pytest.mark.mutating
@pytest.mark.readwrite
def test_vlan_config_clear_readwrite(neox_config_service, readwrite_session, cleanup_registry):
    neox_config_service.verify_vlan_case_set_and_clear(readwrite_session, cleanup_registry, "max")


@pytest.mark.mutating
@pytest.mark.readwrite
def test_vlan_config_error_readwrite(neox_config_service, readwrite_session):
    neox_config_service.verify_vlan_config_invalid_payload(readwrite_session)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_min_create_readwrite(neox_config_service, readwrite_session, cleanup_registry):
    neox_config_service.verify_ont_case_created(readwrite_session, cleanup_registry, "min")


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_max_create_readwrite(neox_config_service, readwrite_session, cleanup_registry):
    neox_config_service.verify_ont_case_created(readwrite_session, cleanup_registry, "max")


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_clear_readwrite(neox_config_service, readwrite_session, cleanup_registry):
    neox_config_service.verify_ont_config_set_and_clear(readwrite_session, cleanup_registry)


@pytest.mark.mutating
@pytest.mark.readwrite
def test_ont_config_error_readwrite(neox_config_service, readwrite_session):
    neox_config_service.verify_ont_config_invalid_payload(readwrite_session)


def ge_cli_checks(content: dict[str, Any]) -> list[str]:
    checks = []
    if content.get("portenable") == "enable":
        checks.append("enable")
    if "auto_nego" in content:
        checks.append(f"auto-negotiation {content['auto_nego']}")
    if "flow" in content:
        checks.append(f"flow-control {content['flow']}")
    if "portspeed" in content:
        checks.append(f"speed {content['portspeed']}")
    if "portname" in content:
        checks.append(f"name \"{content['portname']}\"")
    if "arpinspection" in content:
        checks.append(f"arp-inspection {content['arpinspection']}")
    if "copycpbit" in content:
        checks.append(f"vlan copy_cpbit {content['copycpbit']}")
    if "outertpid" in content:
        checks.append(f"vlan outer-tpid {content['outertpid']}")
    if "frametype" in content:
        checks.append(f"frame-type {content['frametype']}")
    return checks
