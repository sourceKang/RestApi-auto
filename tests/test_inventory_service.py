from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from models.api import ApiResponse
from services.inventory.service import InventoryService, _assert_port_fields
from tests.support.fixtures import prepare_ont_inventory_with_session_rotation
from tests.support.ont_workflow import OntServiceWorkflowState


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

class FakeApiClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.responses.pop(0)


def api_response(retstatus, retresult=""):
    return ApiResponse(200, {"retstatus": retstatus, "retresult": retresult}, "", 0, "id", "GET", "url")


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
    def __init__(self, existing, *, template="#Formal", service_states=None):
        self.existing = existing
        self.template = template
        self.service_states = list(service_states or [{"state": "Success"}])
        self.calls = []

    def get_ont_service(self, session_id):
        self.calls.append(("get_service", session_id))
        return self.existing

    def ont_service_is_missing(self, response):
        return response.retstatus == "Fail" and "no data" in response.retresult.lower()

    def ont_service_template(self, response):
        self.calls.append(("service_template",))
        return self.template

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
        )

    assert template_factory_calls == []
    assert not any(call[0] == "upsert" for call in inventory.calls)


def test_prepare_ont_inventory_stops_when_service_is_missing_but_cli_is_is():
    inventory = FakeInventoryForPreparation(api_response("Fail", "No data found"))
    services = SimpleNamespace(inventory=inventory, provision=FakeProvisionForPreparation())
    template_factory_calls = []

    with pytest.raises(AssertionError, match="refusing to create a duplicate"):
        prepare_ont_inventory_with_session_rotation(
            services,
            FakeSessionManager(),
            SimpleNamespace(readwrite=object()),
            lambda: template_factory_calls.append(True) or "#Temporary",
            cli_status_reader=lambda env: cli_status("IS"),
        )

    assert template_factory_calls == []
    assert not any(call[0] == "upsert" for call in inventory.calls)


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
