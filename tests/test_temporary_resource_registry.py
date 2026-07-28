from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import services.profile.service as profile_module
from models.api import ApiResponse
from services.profile import ProfileService
from services.profile.temporary_registry import (
    create_temporary_graph_record,
    environment_identity,
    scan_temporary_graph_records,
)


TEMPORARY_NAME = "#RestApi_GE_3011b10_N1_R7F"


class FakeApiClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        assert self.responses, f"No fake response left for {method} {path}"
        return self.responses.pop(0)


def response(retstatus, *, payload=None, retresult=""):
    body = payload or {"retstatus": retstatus, "retresult": retresult}
    return ApiResponse(200, body, "", 0, "request-id", "GET", "https://ems/api")


def environment():
    return SimpleNamespace(
        base_url="https://ems.example/netatlasemsapi",
        ems_version="03.00.11 (AAVV.221) b10",
        dut=SimpleNamespace(
            node_key="NODE1",
            ont_sn="TEST_SN",
            ge_slot_id="1",
            ge_port_id="1",
            device_name="NODE1_DEVICE",
        ),
    )


def create_old_record(tmp_path, *, age_hours=48):
    env = environment()
    return create_temporary_graph_record(
        base_url=env.base_url,
        ems_version=env.ems_version,
        node_key=env.dut.node_key,
        source_profilename="#RestApi_getemp_ge1",
        root_name=TEMPORARY_NAME,
        profiles=[{"profiletype": "GETemplateProfile", "profilename": TEMPORARY_NAME}],
        service_targets=[
            {"resource": "ont", "path": "/ontservice/ORIGINAL_TEST_SN"}
        ],
        created_at=datetime.now(timezone.utc) - timedelta(hours=age_hours),
        root=tmp_path,
    )


def test_registry_filters_by_verified_environment_node_and_age(tmp_path):
    create_old_record(tmp_path, age_hours=48)
    create_old_record(tmp_path, age_hours=1)
    env = environment()

    scan = scan_temporary_graph_records(
        base_url=env.base_url,
        node_key="NODE1",
        min_age_hours=24,
        root=tmp_path,
    )

    assert len(scan.records) == 1
    assert scan.records[0].root_name == TEMPORARY_NAME
    assert scan.invalid_files == ()
    assert environment_identity(env.base_url) != environment_identity("https://other.example/api")
    assert scan_temporary_graph_records(
        base_url="https://other.example/api",
        node_key="NODE1",
        min_age_hours=0,
        root=tmp_path,
    ).records == ()


def test_stale_audit_is_read_only_and_keeps_manifest(tmp_path):
    manifest = create_old_record(tmp_path)
    client = FakeApiClient(
        [
            response("Success", payload={"retstatus": "Success", "retval": {"Name": TEMPORARY_NAME}}),
            response("Fail", retresult="No data found"),
        ]
    )
    service = ProfileService(client, env_config=environment(), registry_root=tmp_path)

    report = service.reconcile_stale_temporary_graphs("session", min_age_hours=24, delete=False)

    assert report["records"][0]["status"] == "audit_candidate"
    assert manifest.exists()
    assert all(method == "GET" for method, _, _ in client.calls)


def test_stale_cleanup_deletes_unreferenced_graph_and_manifest(tmp_path):
    manifest = create_old_record(tmp_path)
    client = FakeApiClient(
        [
            response("Success", payload={"retstatus": "Success", "retval": {"Name": TEMPORARY_NAME}}),
            response("Fail", retresult="No data found"),
            response("Success", payload={"retstatus": "Success", "retval": {"Name": TEMPORARY_NAME}}),
            response("Success"),
            response("Fail", retresult="The profile does not exist."),
        ]
    )
    service = ProfileService(client, env_config=environment(), registry_root=tmp_path)

    report = service.reconcile_stale_temporary_graphs("session", min_age_hours=24, delete=True)

    assert report["records"][0]["status"] == "removed"
    assert not manifest.exists()
    assert [method for method, _, _ in client.calls] == ["GET", "GET", "GET", "DELETE", "GET"]


def test_stale_cleanup_refuses_referenced_or_unknown_service_state(tmp_path):
    manifest = create_old_record(tmp_path)
    referenced_client = FakeApiClient(
        [
            response("Success", payload={"retstatus": "Success", "retval": {"Name": TEMPORARY_NAME}}),
            response(
                "Success",
                payload={
                    "retstatus": "Success",
                    "retval": {"ontserviceinfo": {"ontTemplate": TEMPORARY_NAME}},
                },
            ),
        ]
    )
    referenced = ProfileService(
        referenced_client,
        env_config=environment(),
        registry_root=tmp_path,
    ).reconcile_stale_temporary_graphs("session", min_age_hours=24, delete=True)

    assert referenced["records"][0]["status"] == "skipped_referenced"
    assert manifest.exists()
    assert all(method == "GET" for method, _, _ in referenced_client.calls)

    unknown_client = FakeApiClient(
        [
            response("Success", payload={"retstatus": "Success", "retval": {"Name": TEMPORARY_NAME}}),
            response("Fail", retresult="Not authorized."),
        ]
    )
    unknown = ProfileService(
        unknown_client,
        env_config=environment(),
        registry_root=tmp_path,
    ).reconcile_stale_temporary_graphs("session", min_age_hours=24, delete=True)

    assert unknown["records"][0]["status"] == "skipped_reference_unknown"
    assert manifest.exists()
    assert all(method == "GET" for method, _, _ in unknown_client.calls)


def test_created_graph_manifest_is_removed_only_after_completed_cleanup(monkeypatch, tmp_path):
    source_name = "#RestApi_Source"
    source = {
        "_config_ref": "source_profile_data",
        "profiletype": "GETemplateProfile",
        "profilename": source_name,
        "post_profile_info": {},
    }
    monkeypatch.setattr(profile_module, "profile_definition_by_name", lambda name: source if name == source_name else None)
    monkeypatch.setattr(profile_module, "profile_dependency_order", lambda name: [source_name])
    client = FakeApiClient(
        [
            response("Fail", retresult="No data found"),
            response("Fail", retresult="No data found"),
            response("Success"),
            response("Success", payload={"retstatus": "Success", "retval": {"Name": TEMPORARY_NAME}}),
        ]
    )
    service = ProfileService(client, env_config=environment(), registry_root=tmp_path)

    graph = service.create_temporary_profile_graph(
        "session",
        source_name,
        environment().ems_version,
        "NODE1",
        run_token="7F",
        timeout=1,
        interval=0,
    )

    assert graph.registry_path is not None
    assert Path(graph.registry_path).exists()
    manifest = next(tmp_path.rglob("*.json"))
    service.complete_temporary_graph_cleanup(graph)
    assert not manifest.exists()
