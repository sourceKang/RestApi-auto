from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from config_loader import load_environment
from models.api import ApiResponse
from services.inventory.service import InventoryService, _assert_any_field_present, _assert_ont_fields, _assert_port_fields
from tests.support.fixtures import prepare_ont_inventory_with_session_rotation, prepared_ge_service
from tests.support.ge_workflow import GeServiceWorkflowState
from tests.support.ont_workflow import OntInventoryPreconditionError, OntServiceWorkflowState


def test_field_presence_can_allow_empty_telephone_without_allowing_missing_field():
    _assert_any_field_present({"Telephone": ""}, ("Telephone", "telephone"), "Port", allow_empty=True)

    with pytest.raises(AssertionError, match="missing one of Telephone/telephone"):
        _assert_any_field_present({}, ("Telephone", "telephone"), "Port", allow_empty=True)


def _ont_inventory_item(env, template_name):
    fw_image = str(env.node_target.get("ont", {}).get("fw_image") or "")
    return {
        "DevName": env.dut.device_name,
        "IPAddress": env.dut.device_ip,
        "Slot": env.dut.slot_id,
        "Port": env.dut.port_id,
        "ONT": env.dut.ont_id,
        "sn": env.dut.ont_sn,
        "password": env.dut.ont_password,
        "templateName": template_name,
        "description": env.dut.ont_description,
        "model": env.node_target["ont"]["model"],
        "activeVersion": "",
        "activeFwVersion": fw_image,
    }


def test_olt140x_ont_inventory_requires_template_field_but_allows_empty_value():
    env = load_environment(node="NODE2")

    _assert_ont_fields(_ont_inventory_item(env, ""), env, ont_template="#Temporary")


def test_neox_ont_inventory_still_requires_expected_template_value():
    env = load_environment(node="NODE3")

    with pytest.raises(AssertionError, match="templateName"):
        _assert_ont_fields(_ont_inventory_item(env, ""), env, ont_template="#Temporary")


def test_port_inventory_accepts_operation_status_without_provisioning_status():
    env_config = SimpleNamespace(
        dut=SimpleNamespace(
            device_name="California_IES4204_169.57",
            device_ip="192.168.169.57",
            ge_slot_id="1",
            ge_port_id="39",
            ge_port_name="1g_Hsinchu",
        ),
        node_target={
            "submap_name": "!!!AutoMuskSubmap",
            "ge_service_card": "GLC1440X-55",
            "cards": {
                "GLC1440X-55": {
                    "ports": {
                        "39": {
                            "port_id": "39",
                            "port_type": "Ethernet Access",
                            "port_speed": "1G",
                        }
                    }
                }
            },
        },
    )
    item = {
        "SubmapName": "!!!AutoMuskSubmap",
        "Speed": "1G",
        "portAdminState": "1",
        "DevName": "California_IES4204_169.57",
        "Telephone": "011+886+7+2737",
        "Mode": "",
        "DevType": "19",
        "PortID": "39",
        "index": 1,
        "PortName": "1g_Hsinchu",
        "portOperationStatus": "1",
        "SlotID": "1",
        "txPower": "-3.4708",
        "rxPower": "-1.0095",
        "portAlarmStatus": "0",
        "Enable": "Enable",
        "IPAddress": "192.168.169.57",
        "DevID": "2018",
        "PortType": "6",
    }

    _assert_port_fields(item, env_config)


def test_olt1408ac_port_inventory_uses_cli_confirmed_rest_up_status_two():
    env = load_environment(node="NODE2")
    item = {
        "SubmapName": env.node_target.get("submap_name", ""),
        "Speed": "2.5G",
        "portAdminState": "1",
        "DevName": env.dut.device_name,
        "Telephone": "",
        "PortID": env.dut.port_id,
        "PortName": env.dut.ge_port_name,
        "portOperationStatus": "2",
        "SlotID": env.dut.slot_id,
        "txPower": "5.36",
        "rxPower": "N/A",
        "IPAddress": env.dut.device_ip,
    }

    _assert_port_fields(item, env)


class FakeApiClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.responses.pop(0)


def api_response(retstatus, retresult=""):
    return ApiResponse(200, {"retstatus": retstatus, "retresult": retresult}, "", 0, "id", "GET", "url")


def ont_diagnostic_env():
    return SimpleNamespace(
        dut=SimpleNamespace(
            node_key="NODE3",
            device_name="Taiwan_NeoX-03_169.58",
            slot_id="3",
            port_id="16",
            ont_id="1",
            ont_sn="DYNAMIC_SN",
            ont_description="dynamic_ont",
        )
    )


def test_wait_for_ont_service_visibility_recovers_on_third_observation():
    missing = api_response("Fail", "No data found")
    visible = api_response("Success")
    client = FakeApiClient([missing, visible])
    service = InventoryService(client, ont_diagnostic_env())
    sleeps = []

    result = service.wait_for_ont_service_visibility(
        "session",
        missing,
        attempts=3,
        interval=5,
        sleeper=sleeps.append,
    )

    assert result is visible
    assert sleeps == [5, 5]
    assert [method for method, _, _ in client.calls] == ["GET", "GET"]


def test_collect_ont_consistency_diagnostic_classifies_partial_visibility_without_mutation():
    visible = ApiResponse(
        200,
        {
            "retstatus": "Success",
            "retval": {"ontinfo": {"SN": "DYNAMIC_SN"}},
        },
        "",
        0,
        "id",
        "GET",
        "url",
    )
    client = FakeApiClient([visible] + [api_response("Fail", "No data found")] * 5)
    service = InventoryService(client, ont_diagnostic_env())

    evidence = service.collect_ont_consistency_diagnostic("session")

    assert evidence["classification"] == "ontservice_missing_but_ont_inventory_visible"
    assert evidence["visible_paths"] == ["ont_by_device"]
    assert len(client.calls) == 6
    assert {method for method, _, _ in client.calls} == {"GET"}


def test_collect_ont_consistency_diagnostic_classifies_node_inventory_missing():
    client = FakeApiClient([api_response("Fail", "No data found")] * 6)
    service = InventoryService(client, ont_diagnostic_env())

    evidence = service.collect_ont_consistency_diagnostic("session")

    assert evidence["classification"] == "ems_node_inventory_not_visible"
    assert evidence["visible_paths"] == []
    assert {method for method, _, _ in client.calls} == {"GET"}


def test_ont_service_poll_fails_immediately_when_session_loses_authorization():
    env_config = SimpleNamespace(dut=SimpleNamespace(ont_sn="DYNAMIC_SN"))
    client = FakeApiClient([api_response("Fail", "Not authorized.")])
    service = InventoryService(client, env_config)

    with pytest.raises(AssertionError, match="lost authorization"):
        service.wait_for_ont_service_state("session", {"Success"}, timeout=60, interval=0)

    assert len(client.calls) == 1


def test_upsert_ont_service_refuses_to_overwrite_other_template():
    env_config = SimpleNamespace(
        dut=SimpleNamespace(
            ont_sn="DYNAMIC_SN",
            ont_template="#Source",
            ont_password="placeholder",
            ont_description="dynamic_ont",
        )
    )
    existing = ApiResponse(
        200,
        {
            "retstatus": "Success",
            "retval": {
                "ontserviceinfo": {
                    "data": {"templateprof": "#Formal"},
                }
            },
        },
        "",
        0,
        "id",
        "GET",
        "url",
    )
    client = FakeApiClient([existing])
    service = InventoryService(client, env_config)

    with pytest.raises(AssertionError, match="Refusing to overwrite"):
        service.upsert_ont_service("session", "#Temporary")

    assert [(method, path) for method, path, _ in client.calls] == [
        ("GET", "/ontservice/DYNAMIC_SN")
    ]


def test_upsert_ont_service_reconciles_get_post_visibility_race():
    env_config = SimpleNamespace(
        dut=SimpleNamespace(
            ont_sn="DYNAMIC_SN",
            ont_template="#Source",
            ont_password="placeholder",
            ont_description="dynamic_ont",
        )
    )
    visible = ApiResponse(
        200,
        {
            "retstatus": "Success",
            "retval": {
                "ontserviceinfo": {
                    "data": {"templateprof": "#Temporary"},
                }
            },
        },
        "",
        0,
        "id",
        "GET",
        "url",
    )
    client = FakeApiClient(
        [
            api_response("Fail", "No data found"),
            api_response("Fail", "SN:DYNAMIC_SN already exists."),
            visible,
            api_response("Success"),
        ]
    )
    service = InventoryService(client, env_config)

    result = service.upsert_ont_service("session", "#Temporary")

    assert result.retstatus == "Success"
    assert [(method, path) for method, path, _ in client.calls] == [
        ("GET", "/ontservice/DYNAMIC_SN"),
        ("POST", "/ontservice/DYNAMIC_SN"),
        ("GET", "/ontservice/DYNAMIC_SN"),
        ("PUT", "/ontservice/DYNAMIC_SN"),
    ]


class FakeSessionManager:
    def __init__(self):
        self.events = []
        self.session_count = 0

    @contextmanager
    def credentials_session(self, credentials):
        self.session_count += 1
        session_id = f"session-{self.session_count}"
        self.events.append(("open", session_id))
        try:
            yield session_id
        finally:
            self.events.append(("close", session_id))


class FakeInventoryForPreparation:
    def __init__(
        self,
        existing,
        *,
        template="#Formal",
        service_states=None,
        visibility_response=None,
        diagnostic=None,
    ):
        self.existing = existing
        self.template = template
        self.service_states = list(service_states or [{"state": "Success"}])
        self.visibility_response = visibility_response or existing
        self.diagnostic = diagnostic or {
            "classification": "ems_node_inventory_not_visible"
        }
        self.calls = []

    def get_ont_service(self, session_id):
        self.calls.append(("get_service", session_id))
        return self.existing

    def ont_service_is_missing(self, response):
        return response.retstatus == "Fail" and "no data" in response.retresult.lower()

    def ont_service_template(self, response):
        self.calls.append(("service_template",))
        return self.template

    def wait_for_ont_service_visibility(self, session_id, initial_response, **kwargs):
        self.calls.append(("service_visibility", session_id, kwargs["attempts"], kwargs["interval"]))
        return self.visibility_response

    def collect_ont_consistency_diagnostic(self, session_id):
        self.calls.append(("consistency_diagnostic", session_id))
        return self.diagnostic

    def upsert_ont_service(self, session_id, ont_template):
        self.calls.append(("upsert", session_id, str(ont_template)))

    def wait_for_ont_service_state(self, session_id, expected_states, **kwargs):
        self.calls.append(("service_state", session_id, kwargs["timeout"]))
        return self.service_states.pop(0)

    def wait_for_ont_inventory(self, **kwargs):
        self.calls.append(
            (
                "inventory",
                kwargs["session_id"],
                kwargs["ont_template"],
                kwargs["timeout"],
            )
        )
        return True


class FakeProvisionForPreparation:
    def __init__(self):
        self.calls = []

    def delete_ont_service_if_uses_template(self, session_id, ont_template, **kwargs):
        self.calls.append((session_id, ont_template, kwargs))


def cli_status(state, source="test"):
    return SimpleNamespace(state=state, source=source)


def test_prepare_ont_inventory_reuses_existing_is_service_without_creating_profiles():
    session_manager = FakeSessionManager()
    inventory = FakeInventoryForPreparation(api_response("Success"), template="#Formal")
    services = SimpleNamespace(inventory=inventory, provision=FakeProvisionForPreparation())
    env_config = SimpleNamespace(readwrite=object())
    template_factory_calls = []

    result = prepare_ont_inventory_with_session_rotation(
        services,
        session_manager,
        env_config,
        lambda: template_factory_calls.append(True) or "#Temporary",
        cli_status_reader=lambda env: cli_status("IS"),
    )

    assert result == "#Formal"
    assert template_factory_calls == []
    assert not any(call[0] == "upsert" for call in inventory.calls)
    assert ("inventory", "session-2", "#Formal", 240) in inventory.calls
    assert session_manager.events == [
        ("open", "session-1"),
        ("close", "session-1"),
        ("open", "session-2"),
        ("close", "session-2"),
    ]


def test_prepare_ont_inventory_waits_for_cli_is_then_rest_sync_after_workflow_post():
    session_manager = FakeSessionManager()
    inventory = FakeInventoryForPreparation(api_response("Success"), template="#Temporary")
    services = SimpleNamespace(inventory=inventory, provision=FakeProvisionForPreparation())
    state = OntServiceWorkflowState()
    state.begin_post("#Temporary")
    state.complete_post()
    cli_wait_calls = []
    template_factory_calls = []

    result = prepare_ont_inventory_with_session_rotation(
        services,
        session_manager,
        SimpleNamespace(readwrite=object()),
        lambda: template_factory_calls.append(True) or "#Unexpected",
        cli_status_reader=lambda env: cli_status("UnReg"),
        cli_is_waiter=lambda env, **kwargs: cli_wait_calls.append(kwargs) or cli_status("IS"),
        workflow_state=state,
    )

    assert result == "#Temporary"
    assert template_factory_calls == []
    assert len(cli_wait_calls) == 1
    assert cli_wait_calls[0]["timeout"] == 180
    assert ("inventory", "session-2", "#Temporary", 240) in inventory.calls
    assert state.inventory_ready is True


def test_prepare_ont_inventory_stops_when_existing_service_is_not_is():
    session_manager = FakeSessionManager()
    inventory = FakeInventoryForPreparation(api_response("Success"), template="#Formal")
    services = SimpleNamespace(inventory=inventory, provision=FakeProvisionForPreparation())
    template_factory_calls = []

    with pytest.raises(AssertionError, match="already exists, but CLI is not IS"):
        prepare_ont_inventory_with_session_rotation(
            services,
            session_manager,
            SimpleNamespace(readwrite=object()),
            lambda: template_factory_calls.append(True) or "#Temporary",
            cli_status_reader=lambda env: cli_status("UnReg"),
            allow_provisioning=True,
        )

    assert template_factory_calls == []
    assert not any(call[0] == "upsert" for call in inventory.calls)


def test_prepare_ont_inventory_skips_existing_non_is_service_for_read_only_seed():
    inventory = FakeInventoryForPreparation(api_response("Success"), template="#Formal")
    services = SimpleNamespace(inventory=inventory, provision=FakeProvisionForPreparation())
    template_factory_calls = []

    with pytest.raises(OntInventoryPreconditionError, match="read-only inventory tests do not modify"):
        prepare_ont_inventory_with_session_rotation(
            services,
            FakeSessionManager(),
            SimpleNamespace(readwrite=object()),
            lambda: template_factory_calls.append(True) or "#Temporary",
            cli_status_reader=lambda env: cli_status("UnReg"),
        )

    assert template_factory_calls == []
    assert not any(call[0] == "upsert" for call in inventory.calls)


def test_prepare_ont_inventory_blocks_cli_only_ont_as_precondition():
    inventory = FakeInventoryForPreparation(
        api_response("Fail", "No data found"),
        diagnostic={
            "classification": "ontservice_missing_but_ont_inventory_visible",
            "visible_paths": ["ont_by_sn"],
        },
    )
    services = SimpleNamespace(inventory=inventory, provision=FakeProvisionForPreparation())
    template_factory_calls = []

    with pytest.raises(OntInventoryPreconditionError, match="CLI-only ONT is visible"):
        prepare_ont_inventory_with_session_rotation(
            services,
            FakeSessionManager(),
            SimpleNamespace(readwrite=object()),
            lambda: template_factory_calls.append(True) or "#Temporary",
            cli_status_reader=lambda env: cli_status("IS"),
        )

    assert template_factory_calls == []
    assert not any(call[0] == "upsert" for call in inventory.calls)
    assert ("service_visibility", "session-2", 3, 5) in inventory.calls
    assert ("consistency_diagnostic", "session-2") in inventory.calls


def test_prepare_ont_inventory_fails_when_cli_is_but_node_inventory_is_missing():
    inventory = FakeInventoryForPreparation(api_response("Fail", "No data found"))
    services = SimpleNamespace(inventory=inventory, provision=FakeProvisionForPreparation())

    with pytest.raises(AssertionError, match="classification=ems_node_inventory_not_visible") as raised:
        prepare_ont_inventory_with_session_rotation(
            services,
            FakeSessionManager(),
            SimpleNamespace(readwrite=object()),
            lambda: "#Temporary",
            cli_status_reader=lambda env: cli_status("IS"),
        )

    assert type(raised.value) is AssertionError
    assert not any(call[0] == "upsert" for call in inventory.calls)


def test_prepare_ont_inventory_continues_when_rest_visibility_recovers():
    inventory = FakeInventoryForPreparation(
        api_response("Fail", "No data found"),
        visibility_response=api_response("Success"),
        template="#Recovered",
    )
    services = SimpleNamespace(inventory=inventory, provision=FakeProvisionForPreparation())
    template_factory_calls = []

    result = prepare_ont_inventory_with_session_rotation(
        services,
        FakeSessionManager(),
        SimpleNamespace(readwrite=object()),
        lambda: template_factory_calls.append(True) or "#Temporary",
        cli_status_reader=lambda env: cli_status("IS"),
    )

    assert result == "#Recovered"
    assert template_factory_calls == []
    assert not any(call[0] == "upsert" for call in inventory.calls)
    assert not any(call[0] == "consistency_diagnostic" for call in inventory.calls)


def test_prepare_ont_inventory_does_not_provision_for_read_only_seed():
    session_manager = FakeSessionManager()
    inventory = FakeInventoryForPreparation(api_response("Fail", "No data found"))
    services = SimpleNamespace(inventory=inventory, provision=FakeProvisionForPreparation())
    template_factory_calls = []

    with pytest.raises(OntInventoryPreconditionError, match="read-only inventory tests do not provision"):
        prepare_ont_inventory_with_session_rotation(
            services,
            session_manager,
            SimpleNamespace(readwrite=object()),
            lambda: template_factory_calls.append(True) or "#Temporary",
            cli_status_reader=lambda env: cli_status("UnReg", "xpon-unreg"),
        )

    assert template_factory_calls == []
    assert not any(call[0] == "upsert" for call in inventory.calls)
    assert session_manager.events == [
        ("open", "session-1"),
        ("close", "session-1"),
    ]


def test_prepare_ont_inventory_creates_only_when_service_missing_and_cli_unregistered():
    session_manager = FakeSessionManager()
    inventory = FakeInventoryForPreparation(api_response("Fail", "No data found"))
    provision = FakeProvisionForPreparation()
    services = SimpleNamespace(inventory=inventory, provision=provision)
    cli_wait_calls = []
    template_factory_calls = []

    result = prepare_ont_inventory_with_session_rotation(
        services,
        session_manager,
        SimpleNamespace(readwrite=object()),
        lambda: template_factory_calls.append(True) or "#Temporary",
        cli_status_reader=lambda env: cli_status("UnReg", "xpon-unreg"),
        cli_is_waiter=lambda env, **kwargs: cli_wait_calls.append(kwargs) or cli_status("IS"),
        allow_provisioning=True,
    )

    assert result == "#Temporary"
    assert template_factory_calls == [True]
    assert provision.calls == []
    assert ("upsert", "session-2", "#Temporary") in inventory.calls
    assert ("inventory", "session-3", "#Temporary", 240) in inventory.calls
    assert len(cli_wait_calls) == 1
    assert session_manager.events == [
        ("open", "session-1"),
        ("close", "session-1"),
        ("open", "session-2"),
        ("close", "session-2"),
        ("open", "session-3"),
        ("close", "session-3"),
    ]


def test_prepare_ont_inventory_rebuilds_only_current_temporary_service_after_wait():
    session_manager = FakeSessionManager()
    inventory = FakeInventoryForPreparation(
        api_response("Fail", "No data found"),
        service_states=[None, {"state": "Success"}],
    )
    provision = FakeProvisionForPreparation()
    services = SimpleNamespace(inventory=inventory, provision=provision)

    prepare_ont_inventory_with_session_rotation(
        services,
        session_manager,
        SimpleNamespace(readwrite=object()),
        lambda: "#Temporary",
        cli_status_reader=lambda env: cli_status("UnReg"),
        cli_is_waiter=lambda env, **kwargs: cli_status("IS"),
        allow_provisioning=True,
    )

    assert provision.calls == [
        ("session-3", "#Temporary", {"timeout": 90, "interval": 5})
    ]
    assert [call for call in inventory.calls if call[0] == "upsert"] == [
        ("upsert", "session-2", "#Temporary"),
        ("upsert", "session-3", "#Temporary"),
    ]
    assert session_manager.events == [
        ("open", "session-1"),
        ("close", "session-1"),
        ("open", "session-2"),
        ("close", "session-2"),
        ("open", "session-3"),
        ("close", "session-3"),
        ("open", "session-4"),
        ("close", "session-4"),
    ]


def test_prepared_ge_service_does_not_create_seed_for_read_only_flow():
    with pytest.raises(pytest.skip.Exception, match="read-only tests do not create"):
        prepared_ge_service.__wrapped__(
            services=None,
            session_manager=None,
            env_config=None,
            request=None,
            ge_service_workflow_state=GeServiceWorkflowState(),
        )
