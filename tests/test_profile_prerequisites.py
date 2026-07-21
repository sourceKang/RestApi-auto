from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

import services.profile.service as profile_module
from models.api import ApiResponse
from services.profile import ProfileService, ProfileWorkspace, temporary_ont_template_name
from services.provision.service import ProvisionService, recorded_ont_service_payload


class FakeApiClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        assert self.responses, f"No fake response left for {method} {path}"
        return self.responses.pop(0)


def api_response(retstatus, *, name=None, content=None, retresult=""):
    payload = {"retstatus": retstatus, "retresult": retresult}
    if name is not None:
        payload["retval"] = {"Name": name, "Content": content or {}}
    return ApiResponse(200, payload, "", 0, "request-id", "GET", "https://ems/profile")


def install_definitions(monkeypatch, definitions):
    monkeypatch.setattr(profile_module, "profile_definition_by_name", lambda name: definitions.get(name))


def test_existing_prerequisite_profile_must_match_yaml(monkeypatch):
    definition = {
        "_config_ref": "root_profile_data",
        "profiletype": "TemplateProfile",
        "profilename": "#RestApi_Root",
        "post_profile_info": {"Mode": "aes128"},
    }
    install_definitions(monkeypatch, {"#RestApi_Root": definition})
    client = FakeApiClient([api_response("Success", name="#RestApi_Root", content={"Mode": "aes128", "ServerField": "ok"})])

    ProfileService(client).ensure_prerequisite_profile("session", "#RestApi_Root")

    assert [call[:2] for call in client.calls] == [("GET", "/profile/TemplateProfile/#RestApi_Root")]


def test_ont_ont_acl_slots_map_to_profiles_1_through_16():
    catalog = profile_module.catalog_profile_data()
    ont_profile = next(
        data
        for data in catalog.values()
        if data.get("profiletype") == "ONTONTProfile"
        and data.get("profilename") == "#RestApi_OntOnt"
    )
    expected = {
        f"ontprofile_aclaclprofile{slot}": f"#RestApi_ontAclProfile_{slot}"
        for slot in range(1, 17)
    }
    actual = {
        key: value
        for key, value in ont_profile["patch_profile_info"].items()
        if key.startswith("ontprofile_aclaclprofile")
    }

    assert actual == expected
    assert profile_module.profile_definition_by_name("#RestApi_ontAclProfile_0") is None
    for profilename in expected.values():
        definition = profile_module.profile_definition_by_name(profilename)
        assert definition is not None
        assert definition["profiletype"] == "ONTAclProfile"


def test_existing_prerequisite_profile_mismatch_fails_without_overwrite(monkeypatch):
    definition = {
        "_config_ref": "root_profile_data",
        "profiletype": "TemplateProfile",
        "profilename": "#RestApi_Root",
        "post_profile_info": {"Mode": "aes128"},
    }
    install_definitions(monkeypatch, {"#RestApi_Root": definition})
    client = FakeApiClient([api_response("Success", name="#RestApi_Root", content={"Mode": "none"})])

    with pytest.raises(AssertionError, match="content mismatch.*Mode"):
        ProfileService(client).ensure_prerequisite_profile("session", "#RestApi_Root")

    assert all(method != "POST" for method, _, _ in client.calls)


def test_missing_profiles_are_created_in_dependency_order_and_polled(monkeypatch):
    definitions = {
        "#RestApi_Root": {
            "_config_ref": "root_profile_data",
            "profiletype": "TemplateProfile",
            "profilename": "#RestApi_Root",
            "post_profile_info": {"Dependency": "#RestApi_Dependency"},
        },
        "#RestApi_Dependency": {
            "_config_ref": "dependency_profile_data",
            "profiletype": "ChildProfile",
            "profilename": "#RestApi_Dependency",
            "post_profile_info": {"Value": "1"},
        },
    }
    install_definitions(monkeypatch, definitions)
    client = FakeApiClient(
        [
            api_response("Fail", retresult="No data"),
            api_response("Success"),
            api_response("Success", name="#RestApi_Dependency", content={"Value": "1"}),
            api_response("Fail", retresult="No data"),
            api_response("Success"),
            api_response("Fail", retresult="Not ready"),
            api_response("Success", name="#RestApi_Root", content={"Dependency": "#RestApi_Dependency"}),
        ]
    )

    ProfileService(client).ensure_prerequisite_profile("session", "#RestApi_Root", timeout=1, interval=0)

    assert [(method, path) for method, path, _ in client.calls] == [
        ("GET", "/profile/ChildProfile/#RestApi_Dependency"),
        ("POST", "/profile/ChildProfile/#RestApi_Dependency"),
        ("GET", "/profile/ChildProfile/#RestApi_Dependency"),
        ("GET", "/profile/TemplateProfile/#RestApi_Root"),
        ("POST", "/profile/TemplateProfile/#RestApi_Root"),
        ("GET", "/profile/TemplateProfile/#RestApi_Root"),
        ("GET", "/profile/TemplateProfile/#RestApi_Root"),
    ]


def test_missing_profile_definition_and_create_failure_are_errors(monkeypatch):
    install_definitions(monkeypatch, {})
    with pytest.raises(AssertionError, match="No profile definition"):
        ProfileService(FakeApiClient([])).ensure_prerequisite_profile("session", "#Missing")

    definition = {
        "_config_ref": "root_profile_data",
        "profiletype": "TemplateProfile",
        "profilename": "#RestApi_Root",
        "post_profile_info": {},
    }
    install_definitions(monkeypatch, {"#RestApi_Root": definition})
    client = FakeApiClient([api_response("Fail", retresult="No data"), api_response("Fail", retresult="Create rejected")])
    with pytest.raises(AssertionError, match="Cannot create prerequisite profile"):
        ProfileService(client).ensure_prerequisite_profile("session", "#RestApi_Root")


def test_workspace_cleanup_deletes_only_planned_and_created_profiles():
    calls = []

    class CleanupService:
        def delete_temporary_profile(self, session_id, definition, **kwargs):
            calls.append((session_id, definition["profilename"], kwargs))

    workspace = ProfileWorkspace(CleanupService(), "session")
    planned = {"profiletype": "RateLimitProfile", "profilename": "#RestApi_Planned"}
    created = {"profiletype": "ONTTemplateProfile", "profilename": "#RestApi_Created"}
    borrowed = {"profiletype": "ONTAclProfile", "profilename": "#RestApi_Borrowed"}
    workspace.plan(planned)
    workspace.add(created)
    workspace.borrow(borrowed)

    workspace.cleanup()

    assert [name for _, name, _ in calls] == ["#RestApi_Created", "#RestApi_Planned"]


def test_workspace_cleanup_reports_and_raises_delete_failure(monkeypatch):
    diagnostics = []

    class CleanupService:
        def delete_temporary_profile(self, session_id, definition, **kwargs):
            raise AssertionError("still referenced")

    monkeypatch.setattr(profile_module, "attach_json", lambda name, payload: diagnostics.append((name, payload)))
    workspace = ProfileWorkspace(CleanupService(), "session")
    definition = {"profiletype": "ONTTemplateProfile", "profilename": "#RestApi_Created"}
    workspace.add(definition)

    with pytest.raises(AssertionError, match="Profile workspace cleanup failed.*still referenced"):
        workspace.cleanup()

    assert diagnostics[0][0] == "Profile workspace cleanup"
    assert diagnostics[0][1]["errors"]


def test_profile_post_cleans_owned_workspace_and_retries_once_at_capacity(monkeypatch):
    definition = {
        "_config_ref": "capacity_profile_data",
        "profiletype": "GETemplateProfile",
        "profilename": "#RestApi_Capacity",
        "post_profile_info": {},
    }
    monkeypatch.setattr(profile_module, "profile_definitions_for", lambda case: [definition])
    client = FakeApiClient(
        [
            api_response("Fail", retresult="No data"),
            api_response("Fail", retresult="Reach the maximum number of profiles 3000 in database."),
            api_response("Fail", retresult="No data"),
            api_response("Success"),
        ]
    )
    service = ProfileService(client)
    cleanup_calls = []

    class Workspace:
        def plan(self, item):
            pass

        def add(self, item):
            pass

        def cleanup(self):
            cleanup_calls.append(True)

    service.verify_post_case("session", Workspace(), {"name": "capacity profile", "case_ids": []})

    assert cleanup_calls == [True]
    assert [method for method, _, _ in client.calls] == ["GET", "POST", "GET", "POST"]


def test_profile_post_does_not_cleanup_or_retry_other_failures(monkeypatch):
    definition = {
        "_config_ref": "invalid_profile_data",
        "profiletype": "GETemplateProfile",
        "profilename": "#RestApi_Invalid",
        "post_profile_info": {},
    }
    monkeypatch.setattr(profile_module, "profile_definitions_for", lambda case: [definition])
    client = FakeApiClient(
        [
            api_response("Fail", retresult="No data"),
            api_response("Fail", retresult="Invalid parameter"),
        ]
    )
    service = ProfileService(client)
    cleanup_calls = []

    class Workspace:
        def plan(self, item):
            pass

        def add(self, item):
            pass

        def cleanup(self):
            cleanup_calls.append(True)

    with pytest.raises(AssertionError):
        service.verify_post_case("session", Workspace(), {"name": "invalid profile", "case_ids": []})

    assert cleanup_calls == []
    assert [method for method, _, _ in client.calls] == ["GET", "POST"]



def test_workspace_reconciles_mismatched_test_prerequisite_by_exact_delete(monkeypatch):
    definition = {
        "_config_ref": "root_profile_data",
        "profiletype": "TemplateProfile",
        "profilename": "#RestApi_Root",
        "post_profile_info": {"Mode": "aes128"},
    }
    install_definitions(monkeypatch, {"#RestApi_Root": definition})
    client = FakeApiClient(
        [
            api_response("Success", name="#RestApi_Root", content={"Mode": "none"}),
            api_response("Success"),
            api_response("Fail", retresult="No data"),
            api_response("Success"),
            api_response("Success", name="#RestApi_Root", content={"Mode": "aes128"}),
        ]
    )
    service = ProfileService(client)
    workspace = ProfileWorkspace(service, "session")

    service.ensure_prerequisite_profile(
        "session",
        "#RestApi_Root",
        workspace=workspace,
        timeout=1,
        interval=0,
    )

    assert [method for method, _, _ in client.calls] == ["GET", "DELETE", "GET", "POST", "GET"]
    assert workspace.owns(definition)


def test_workspace_refuses_to_reconcile_referenced_prerequisite(monkeypatch):
    definition = {
        "_config_ref": "root_profile_data",
        "profiletype": "TemplateProfile",
        "profilename": "#RestApi_Root",
        "post_profile_info": {"Mode": "aes128"},
    }
    install_definitions(monkeypatch, {"#RestApi_Root": definition})
    client = FakeApiClient(
        [
            api_response("Success", name="#RestApi_Root", content={"Mode": "none"}),
            api_response("Fail", retresult="Profile has been used by other Profile"),
        ]
    )
    service = ProfileService(client)
    workspace = ProfileWorkspace(service, "session")

    with pytest.raises(AssertionError, match="exact DELETE failed; no dependent profiles were deleted"):
        service.ensure_prerequisite_profile("session", "#RestApi_Root", workspace=workspace)

    assert [method for method, _, _ in client.calls] == ["GET", "DELETE"]


def test_patch_case_restores_baseline_after_validating_patch(monkeypatch):
    definition = {
        "_config_ref": "root_profile_data",
        "profiletype": "TemplateProfile",
        "profilename": "#RestApi_Root",
        "post_profile_info": {"Mode": "preview"},
        "patch_profile_info": {"Mode": "permit"},
    }
    monkeypatch.setattr(profile_module, "first_isolated_profile_definition_for", lambda case: definition)
    client = FakeApiClient(
        [
            api_response("Success", name="#RestApi_Root", content={"Mode": "preview"}),
            api_response("Success", name="#RestApi_Root", content={"Mode": "preview"}),
            api_response("Success"),
            api_response("Success", name="#RestApi_Root", content={"Mode": "permit"}),
            api_response("Success"),
            api_response("Success", name="#RestApi_Root", content={"Mode": "preview"}),
        ]
    )
    service = ProfileService(client)
    workspace = ProfileWorkspace(service, "session")

    service.verify_patch_case("session", workspace, {"name": "patch profile", "case_ids": []})

    patch_payloads = [kwargs["json"] for method, _, kwargs in client.calls if method == "PATCH"]
    assert patch_payloads == [
        {"Content": {"Mode": "permit"}},
        {"Content": {"Mode": "preview"}},
    ]


def test_patch_case_restores_baseline_when_patch_api_fails(monkeypatch):
    definition = {
        "_config_ref": "root_profile_data",
        "profiletype": "TemplateProfile",
        "profilename": "#RestApi_Root",
        "post_profile_info": {"Mode": "preview"},
        "patch_profile_info": {"Mode": "permit"},
    }
    monkeypatch.setattr(profile_module, "first_isolated_profile_definition_for", lambda case: definition)
    client = FakeApiClient(
        [
            api_response("Success", name="#RestApi_Root", content={"Mode": "preview"}),
            api_response("Success", name="#RestApi_Root", content={"Mode": "preview"}),
            api_response("Fail", retresult="Patch rejected"),
            api_response("Success"),
            api_response("Success", name="#RestApi_Root", content={"Mode": "preview"}),
        ]
    )
    service = ProfileService(client)
    workspace = ProfileWorkspace(service, "session")

    with pytest.raises(AssertionError, match="Patch rejected"):
        service.verify_patch_case("session", workspace, {"name": "patch profile", "case_ids": []})

    patch_payloads = [kwargs["json"] for method, _, kwargs in client.calls if method == "PATCH"]
    assert patch_payloads == [
        {"Content": {"Mode": "permit"}},
        {"Content": {"Mode": "preview"}},
    ]


def test_invalid_post_confirms_no_residual_profile(monkeypatch):
    definition = {
        "_config_ref": "root_profile_data",
        "profiletype": "TemplateProfile",
        "profilename": "#RestApi_Root",
        "post_profile_info": {"Mode": "preview"},
        "invalid_params_to_test": [{"Mode": "invalid", "expected_error": "Invalid Mode"}],
    }
    monkeypatch.setattr(profile_module, "first_isolated_profile_definition_for", lambda case: definition)
    client = FakeApiClient(
        [
            api_response("Fail", retresult="No data"),
            api_response("Fail", retresult="Invalid Mode"),
            api_response("Fail", retresult="No data"),
        ]
    )
    service = ProfileService(client)
    workspace = ProfileWorkspace(service, "session")

    service.verify_post_invalid_param_case("session", workspace, {"name": "invalid post"})

    assert [method for method, _, _ in client.calls] == ["GET", "POST", "GET"]
    assert not workspace.owns(definition)


def test_invalid_post_removes_unexpected_residual_before_failing(monkeypatch):
    definition = {
        "_config_ref": "root_profile_data",
        "profiletype": "TemplateProfile",
        "profilename": "#RestApi_Root",
        "post_profile_info": {"Mode": "preview"},
        "invalid_params_to_test": [{"Mode": "invalid", "expected_error": "Invalid Mode"}],
    }
    monkeypatch.setattr(profile_module, "first_isolated_profile_definition_for", lambda case: definition)
    client = FakeApiClient(
        [
            api_response("Fail", retresult="No data"),
            api_response("Success"),
            api_response("Success", name="#RestApi_Root", content={"Mode": "invalid"}),
            api_response("Success", name="#RestApi_Root", content={"Mode": "invalid"}),
            api_response("Success"),
            api_response("Fail", retresult="No data"),
        ]
    )
    service = ProfileService(client)
    workspace = ProfileWorkspace(service, "session")

    with pytest.raises(AssertionError, match="Invalid POST created residual profile"):
        service.verify_post_invalid_param_case("session", workspace, {"name": "invalid post"})

    assert [method for method, _, _ in client.calls] == ["GET", "POST", "GET", "GET", "DELETE", "GET"]
    assert not workspace.owns(definition)


def test_invalid_patch_restores_changed_content_before_failing(monkeypatch):
    definition = {
        "_config_ref": "root_profile_data",
        "profiletype": "TemplateProfile",
        "profilename": "#RestApi_Root",
        "post_profile_info": {"Mode": "preview"},
        "patch_profile_info": {"Mode": "permit"},
        "invalid_params_to_test": [{"Mode": "invalid", "expected_error": "Invalid Mode"}],
    }
    monkeypatch.setattr(profile_module, "first_isolated_profile_definition_for", lambda case: definition)
    client = FakeApiClient(
        [
            api_response("Success", name="#RestApi_Root", content={"Mode": "preview"}),
            api_response("Success", name="#RestApi_Root", content={"Mode": "preview"}),
            api_response("Fail", retresult="Invalid Mode"),
            api_response("Success", name="#RestApi_Root", content={"Mode": "invalid"}),
            api_response("Success"),
            api_response("Success", name="#RestApi_Root", content={"Mode": "preview"}),
        ]
    )
    service = ProfileService(client)
    workspace = ProfileWorkspace(service, "session")

    with pytest.raises(AssertionError, match="Invalid PATCH changed profile.*baseline was restored"):
        service.verify_patch_invalid_param_case("session", workspace, {"name": "invalid patch"})

    assert [method for method, _, _ in client.calls] == ["GET", "GET", "PATCH", "GET", "PATCH", "GET"]


def test_temporary_ont_template_name_is_versioned_and_readable():
    name = temporary_ont_template_name("03.00.11 (AAVV.221) b10", "NODE1", run_token="7F")

    assert name == "#RestApi_ONT_SFU_3011b10_N1_R7F"
    assert len(name) <= 31


def test_temporary_profile_create_and_delete_preserve_expected_payload(monkeypatch):
    source_name = "#RestApi_Source"
    temporary_name = "#RestApi_ONT_SFU_3011b10_N1_R7F"
    content = {
        "templateprofile_encryption_algorithm": "aes128",
        "templateprofile_encryption_scope_service": "1",
        "templateprofile_encryption_scope_omci": "2",
        "templateprofile_encryption_scope_iphost": "2",
    }
    source = {
        "_config_ref": "source_profile_data",
        "profiletype": "ONTTemplateProfile",
        "profilename": source_name,
        "post_profile_info": content,
    }
    install_definitions(monkeypatch, {source_name: source})
    create_client = FakeApiClient(
        [
            api_response("Fail", retresult="No data found"),
            api_response("Success"),
            api_response("Success", name=temporary_name, content=content),
        ]
    )

    definition = ProfileService(create_client).create_temporary_profile(
        "session",
        source_name,
        temporary_name,
        timeout=1,
        interval=0,
    )

    assert definition["profilename"] == temporary_name
    assert create_client.calls[1][0:2] == ("POST", f"/profile/ONTTemplateProfile/{temporary_name}")
    assert create_client.calls[1][2]["json"] == {"Content": content}

    delete_client = FakeApiClient(
        [
            api_response("Success", name=temporary_name, content=content),
            api_response("Success"),
            api_response("Fail", retresult="No data found"),
        ]
    )
    ProfileService(delete_client).delete_temporary_profile(
        "session",
        definition,
        timeout=1,
        interval=0,
    )
    assert [call[0] for call in delete_client.calls] == ["GET", "DELETE", "GET"]


def test_temporary_profile_graph_clones_dependency_and_rewrites_reference(monkeypatch):
    source_name = "#RestApi_Source"
    security_name = "#RestApi_Security"
    definitions = {
        source_name: {
            "_config_ref": "source_profile_data",
            "profiletype": "ONTTemplateProfile",
            "profilename": source_name,
            "post_profile_info": {"templateprofile_secprof": security_name},
        },
        security_name: {
            "_config_ref": "security_profile_data",
            "profiletype": "ONTSecurityProfile",
            "profilename": security_name,
            "post_profile_info": {"securityprofile_fdb": "1023"},
        },
    }
    install_definitions(monkeypatch, definitions)
    temporary_security = "#RestApi_SEC_3011b10_N1_R7F"
    temporary_template = "#RestApi_ONT_SFU_3011b10_N1_R7F"
    client = FakeApiClient(
        [
            api_response("Fail", retresult="No data found"),
            api_response("Success"),
            api_response("Success", name=temporary_security, content={"securityprofile_fdb": "1023"}),
            api_response("Fail", retresult="No data found"),
            api_response("Success"),
            api_response(
                "Success",
                name=temporary_template,
                content={"templateprofile_secprof": temporary_security},
            ),
        ]
    )

    graph = ProfileService(client).create_temporary_profile_graph(
        "session",
        source_name,
        "03.00.11 (AAVV.221) b10",
        "NODE1",
        run_token="7F",
        timeout=1,
        interval=0,
    )

    assert graph.root_name == temporary_template
    assert [definition["profilename"] for definition in graph.definitions] == [
        temporary_security,
        temporary_template,
    ]
    assert graph.definitions[-1]["post_profile_info"]["templateprofile_secprof"] == temporary_security
    assert [path for method, path, _ in client.calls if method == "POST"] == [
        f"/profile/ONTSecurityProfile/{temporary_security}",
        f"/profile/ONTTemplateProfile/{temporary_template}",
    ]


def test_temporary_profile_graph_rejects_formal_profile_name_collision(monkeypatch):
    source_name = "#RestApi_Source"
    definition = {
        "_config_ref": "source_profile_data",
        "profiletype": "ONTTemplateProfile",
        "profilename": source_name,
        "post_profile_info": {},
    }
    install_definitions(monkeypatch, {source_name: definition})
    monkeypatch.setattr(profile_module, "temporary_profile_name", lambda *args: "#RestApi_Formal")
    monkeypatch.setattr(
        profile_module,
        "catalog_profile_data",
        lambda: {"formal_profile_data": {"profilename": "#RestApi_Formal"}},
    )
    client = FakeApiClient([])

    with pytest.raises(AssertionError, match="overlap formal profile cases"):
        ProfileService(client).create_temporary_profile_graph(
            "session",
            source_name,
            "03.00.11 (AAVV.221) b10",
            "NODE1",
            run_token="7F",
        )

    assert client.calls == []


def test_temporary_profile_cleanup_retries_until_reference_is_released():
    temporary_name = "#RestApi_ONT_SFU_3011b10_N1_R7F"
    definition = {
        "profiletype": "ONTTemplateProfile",
        "profilename": temporary_name,
        "post_profile_info": {},
    }
    client = FakeApiClient(
        [
            api_response("Success", name=temporary_name),
            api_response("Fail", retresult="Some profile has be used by other Profile, can't delete it."),
            api_response("Success"),
            api_response("Fail", retresult="The profile does not exist."),
        ]
    )

    ProfileService(client).delete_temporary_profile("session", definition, timeout=1, interval=0)

    assert [call[0] for call in client.calls] == ["GET", "DELETE", "DELETE", "GET"]


def test_recorded_ont_service_payload_uses_same_run_template_and_bandwidth():
    env = SimpleNamespace(
        dut=SimpleNamespace(
            ont_template="#RestApi_Source",
            ont_password="placeholder",
            ont_description="temporary_ont_test",
        )
    )
    template_name = "#RestApi_ONT_SFU_3011b10_N1_R7F"
    bandwidth_name = "#RestApi_BW_3011b10_N1_R7F"
    graph = profile_module.TemporaryProfileGraph(
        root_name=template_name,
        definitions=(),
        names_by_source={"#RestApi_1G": bandwidth_name},
    )
    temporary_template = profile_module.TemporaryOntTemplate(graph)

    payload = recorded_ont_service_payload(env, ont_template=temporary_template)

    data = payload["ontservice"]["data"]
    assert data["templateprof"] == template_name
    assert type(data["templateprof"]) is str
    assert data["qoss"] == [
        {"qostcont": "service1", "qosds": bandwidth_name, "qosus": bandwidth_name}
    ]

    assert copy.deepcopy(payload) == payload


def ont_service_response(template_name: str):
    return ApiResponse(
        200,
        {
            "retstatus": "Success",
            "retval": {"ontserviceinfo": {"ontTemplate": template_name, "data": {}}},
        },
        "",
        0,
        "request-id",
        "GET",
        "https://ems/ontservice/SN",
    )


def test_temporary_profile_cleanup_only_deletes_service_using_exact_template():
    env = SimpleNamespace(dut=SimpleNamespace(ont_sn="SN"))
    other_client = FakeApiClient([ont_service_response("#RestApi_Other")])
    ProvisionService(other_client, env).delete_ont_service_if_uses_template(
        "session",
        "#RestApi_ONT_SFU_3011b10_N1_R7F",
        timeout=1,
        interval=0,
    )
    assert [call[0] for call in other_client.calls] == ["GET"]

    temporary_name = "#RestApi_ONT_SFU_3011b10_N1_R7F"
    matching_client = FakeApiClient(
        [
            ont_service_response(temporary_name),
            api_response("Success"),
            api_response("Fail", retresult="No data found"),
        ]
    )
    ProvisionService(matching_client, env).delete_ont_service_if_uses_template(
        "session",
        temporary_name,
        timeout=1,
        interval=0,
    )
    assert [call[0] for call in matching_client.calls] == ["GET", "DELETE", "GET"]


def test_temporary_ge_profile_name_is_versioned_and_separate_from_formal_case():
    definition = {
        "profiletype": "GETemplateProfile",
        "profilename": "#RestApi_getemp_ge1",
    }

    name = profile_module.temporary_profile_name(definition, "03.00.11 (AAVV.221) b10", "NODE1", "7F")

    assert name == "#RestApi_GE_3011b10_N1_R7F"
    assert name != definition["profilename"]
    assert len(name) <= profile_module.TEMPORARY_PROFILE_NAME_MAX_LENGTH


def test_profile_delete_case_verifies_repeated_delete_is_rejected(monkeypatch):
    definition = {
        "_config_ref": "delete_profile_data",
        "profiletype": "RateLimitProfile",
        "profilename": "#RestApi_Delete",
        "post_profile_info": {},
    }
    monkeypatch.setattr(profile_module, "profile_definitions_for", lambda case: [definition])
    monkeypatch.setattr(profile_module, "isolated_profile_definitions", lambda definitions: definitions)
    monkeypatch.setattr(profile_module, "definitions_delete_order", lambda definitions: definitions)

    service = ProfileService(FakeApiClient([]))
    delete_calls = []
    discarded = []
    monkeypatch.setattr(service, "ensure_profile_exists_or_skip", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "ensure_profile_deleted", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        service,
        "get_profile",
        lambda *args, **kwargs: api_response("Fail", retresult="No data found"),
    )

    def delete_missing(item, session_id):
        delete_calls.append((item["profilename"], session_id))
        return api_response("Fail", retresult="The profile does not exist")

    monkeypatch.setattr(service, "delete_profile", delete_missing)
    workspace = SimpleNamespace(discard=lambda item: discarded.append(item["profilename"]))

    service.verify_delete_case("session", workspace, {"name": "delete profile", "case_ids": []})

    assert delete_calls == [("#RestApi_Delete", "session")]
    assert discarded == ["#RestApi_Delete"]
