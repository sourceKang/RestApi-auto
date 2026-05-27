from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from config_loader.profile import load_profile_definitions
from services.neox_config.profile_api import delete_profile_if_exists
from services.neox_config.profiles import (
    NEOX_CONTENT_OVERRIDES,
    NEOX_PREFIXES,
    NEOX_PROFILE_CONFIG_REFS,
    NEOX_PROFILE_DEPENDENCIES,
    NEOX_PROFILE_NAMES,
    NEOX_PROFILE_READWRITE_TYPES,
    NEOX_PROFILE_TYPES,
)
from utils.assertions import assert_api_failure, assert_api_success
from utils.cleanup import CleanupRegistry


CONFIGS_DIR = Path(__file__).resolve().parents[2] / "configs"
NEOX_CONFIG_DIR = CONFIGS_DIR / "neox_config"
NEOX_GE_CONFIG_DIR = NEOX_CONFIG_DIR / "ge"
NEOX_NNI_CONFIG_DIR = NEOX_CONFIG_DIR / "nni"
NEOX_VLAN_CONFIG_DIR = NEOX_CONFIG_DIR / "vlan"
NEOX_ONT_CONFIG_DIR = NEOX_CONFIG_DIR / "ont"
NEOX_PROFILE_CONFIG_DIR = NEOX_CONFIG_DIR / "profiles"
NEOX_REFERENCE_CONFIG_DIR = NEOX_CONFIG_DIR / "reference"
GE_ACCEPTED_INCREMENTAL_PAYLOAD_FILE = NEOX_GE_CONFIG_DIR / "neox_ge_accepted_incremental_payload.json"
GE_ACL_RETRY_CONFIG_FILE = NEOX_GE_CONFIG_DIR / "neox_ge_acl_retry_probe.json"
GE_ENABLE_ACCEPTED_PAYLOAD_FILE = NEOX_GE_CONFIG_DIR / "neox_ge_enable_accepted_payload.json"
GE_ENABLE_PROBE_FILE = NEOX_GE_CONFIG_DIR / "neox_ge_enable_probe.json"
GE_FULL_ACCEPTED_PAYLOAD_FILE = NEOX_GE_CONFIG_DIR / "neox_ge_full_accepted_payload.json"
GE_INCREMENTAL_PROBE_FILE = NEOX_GE_CONFIG_DIR / "neox_ge_incremental_probe.json"
GE_NEGATIVE_CASES_FILE = NEOX_GE_CONFIG_DIR / "neox_ge_negative_cases.json"
GE_PAIRED_RETRY_CONFIG_FILE = NEOX_GE_CONFIG_DIR / "neox_ge_paired_retry_probe.json"
GE_PDF_RETRY_CONFIG_FILE = NEOX_GE_CONFIG_DIR / "neox_ge_pdf_retry_probe.json"
GE_SHOW_COMMANDS_FILE = NEOX_GE_CONFIG_DIR / "neox_ge_show_commands.json"
GE_SWAGGER_PAYLOAD_FILE = NEOX_GE_CONFIG_DIR / "neox_ge_swagger_payload.json"
NNI_MIN_PAYLOAD_FILE = NEOX_NNI_CONFIG_DIR / "neox_nni_min_accepted_payload.json"
NNI_MAX_PAYLOAD_FILE = NEOX_NNI_CONFIG_DIR / "neox_nni_full_accepted_payload.json"
VLAN_MINMAX_PAYLOAD_FILE = NEOX_VLAN_CONFIG_DIR / "neox_vlan_minmax_payloads.json"
ONT_MINMAX_PAYLOAD_FILE = NEOX_ONT_CONFIG_DIR / "neox_ont_minmax_payloads.json"
PROFILE_BASIC_CASES_FILE = NEOX_PROFILE_CONFIG_DIR / "neox_profile_basic_cases.json"
PROFILE_QOS_MINMAX_CASES_FILE = NEOX_PROFILE_CONFIG_DIR / "neox_profile_qos_minmax_cases.json"
PROFILE_MINMAX_PAYLOAD_DIR = NEOX_PROFILE_CONFIG_DIR / "minmax"
PROFILE_OBSERVED_FAILURES_FILE = NEOX_PROFILE_CONFIG_DIR / "observed" / "neox_profile_observed_failures.json"
IGMP_GROUP_PRIVILEGE_PROBE_CASES_FILE = NEOX_PROFILE_CONFIG_DIR / "observed" / "neox_igmp_group_privilege_probe_cases.json"
PROFILE_CLI_VERIFY_FILE = NEOX_PROFILE_CONFIG_DIR / "neox_profile_cli_verify.json"
NEOX_FEATURE_TEST_DATA_FILE = NEOX_REFERENCE_CONFIG_DIR / "neox_feature_test_data.yaml"
NEOX_SWAGGER_DATA_FILE = NEOX_REFERENCE_CONFIG_DIR / "neox_swagger_data.yaml"
NEOX_UG_PARAMETER_REFERENCE_FILE = NEOX_REFERENCE_CONFIG_DIR / "neox_ug_parameter_reference.yaml"
NEOX_CONFIG_DATA_FILES = (
    GE_ACCEPTED_INCREMENTAL_PAYLOAD_FILE,
    GE_ACL_RETRY_CONFIG_FILE,
    GE_ENABLE_ACCEPTED_PAYLOAD_FILE,
    GE_ENABLE_PROBE_FILE,
    GE_FULL_ACCEPTED_PAYLOAD_FILE,
    GE_INCREMENTAL_PROBE_FILE,
    GE_NEGATIVE_CASES_FILE,
    GE_PAIRED_RETRY_CONFIG_FILE,
    GE_PDF_RETRY_CONFIG_FILE,
    GE_SHOW_COMMANDS_FILE,
    GE_SWAGGER_PAYLOAD_FILE,
    NNI_MIN_PAYLOAD_FILE,
    NNI_MAX_PAYLOAD_FILE,
    VLAN_MINMAX_PAYLOAD_FILE,
    ONT_MINMAX_PAYLOAD_FILE,
    PROFILE_BASIC_CASES_FILE,
    PROFILE_QOS_MINMAX_CASES_FILE,
    PROFILE_OBSERVED_FAILURES_FILE,
    IGMP_GROUP_PRIVILEGE_PROBE_CASES_FILE,
    PROFILE_CLI_VERIFY_FILE,
    NEOX_FEATURE_TEST_DATA_FILE,
    NEOX_SWAGGER_DATA_FILE,
    NEOX_UG_PARAMETER_REFERENCE_FILE,
)


class NeoXConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class NeoXTarget:
    device_name: str
    ge_slot_id: str
    ge_port_id: str
    nni_slot_id: str
    nni_port_id: str
    ont_slot_id: str
    ont_port_id: str
    ont_id: str
    ont_sn: str
    ont_password: str
    vlan_id: str


class NeoXConfigService:
    def __init__(self, api_client, env_config) -> None:
        self.api_client = api_client
        self.env_config = env_config
        self._profiles = load_profile_definitions()

    def verify_node3_target(self) -> None:
        if not str(self.env_config.dut.chassis).startswith("NeoX"):
            pytest.skip("NeoX configuration tests require a NeoX chassis.")

    def verify_required_target_data(self) -> None:
        self.verify_node3_target()
        target = self.target()
        missing = [
            name
            for name, value in {
                "device_name": target.device_name,
                "ge_slot_id": target.ge_slot_id,
                "ge_port_id": target.ge_port_id,
                "nni_slot_id": target.nni_slot_id,
                "nni_port_id": target.nni_port_id,
                "ont_slot_id": target.ont_slot_id,
                "ont_port_id": target.ont_port_id,
                "ont_id": target.ont_id,
                "ont_sn": target.ont_sn,
                "vlan_id": target.vlan_id,
            }.items()
            if value in (None, "")
        ]
        if missing:
            raise NeoXConfigError(f"Missing NeoX target data: {', '.join(missing)}")
        for profile_type in NEOX_PROFILE_TYPES:
            self.profile_definition(profile_type)
            self.neox_profile_name(profile_type)

    def verify_ge_config_rejected(self, session_id: str) -> None:
        self.verify_node3_target()
        self._verify_mutation_rejected(session_id, self.ge_path(), ge_port_payload())

    def verify_nni_config_rejected(self, session_id: str) -> None:
        self.verify_node3_target()
        self._verify_mutation_rejected(session_id, self.nni_path(), nni_port_payload())

    def verify_vlan_config_rejected(self, session_id: str) -> None:
        self.verify_node3_target()
        self._verify_mutation_rejected(session_id, self.vlan_path(), vlan_payload())

    def verify_ont_config_rejected(self, session_id: str) -> None:
        self.verify_node3_target()
        self._verify_mutation_rejected(session_id, self.ont_path(), ont_config_payload(self.target()))

    def verify_neox_profile_rejected(self, session_id: str, profile_type: str) -> None:
        self.verify_node3_target()
        path = self.neox_profile_path(profile_type)
        payload = self.neox_profile_payload(profile_type)
        response = self.api_client.request("POST", path, session=session_id, json=payload)
        assert_api_failure(response)
        response = self.api_client.request("DELETE", path, session=session_id)
        assert_api_failure(response)

    def verify_ge_config_set_and_clear(self, session_id: str, cleanup_registry: CleanupRegistry) -> None:
        self.verify_node3_target()
        self._verify_set_and_clear(session_id, cleanup_registry, self.ge_path(), ge_port_payload())

    def verify_ge_config_invalid_payload(self, session_id: str) -> None:
        self.verify_node3_target()
        self._verify_invalid_payload(
            session_id,
            self.ge_path(),
            {"Content": {"portenable": "invalid"}},
        )

    def verify_nni_config_set_and_clear(self, session_id: str, cleanup_registry: CleanupRegistry) -> None:
        self.verify_node3_target()
        self._verify_set_and_clear(session_id, cleanup_registry, self.nni_path(), nni_min_payload())

    def verify_nni_config_invalid_payload(self, session_id: str) -> None:
        self.verify_node3_target()
        self._verify_invalid_payload(
            session_id,
            self.nni_path(),
            {"Content": {"portenable": "invalid"}},
        )

    def verify_vlan_create_and_delete(self, session_id: str, cleanup_registry: CleanupRegistry) -> None:
        self.verify_node3_target()
        self._verify_set_and_clear(session_id, cleanup_registry, self.vlan_path(), vlan_payload())

    def verify_vlan_case_created(self, session_id: str, cleanup_registry: CleanupRegistry, case_name: str) -> None:
        self.verify_node3_target()
        vid, payload = vlan_case(case_name)
        path = self.vlan_path_for_vid(vid)
        cleanup_registry.add(lambda: self.api_client.request("DELETE", path, session=session_id))
        response = self.api_client.request("POST", path, session=session_id, json=payload)
        assert_api_success(response)

    def verify_vlan_case_set_and_clear(self, session_id: str, cleanup_registry: CleanupRegistry, case_name: str) -> None:
        self.verify_node3_target()
        vid, payload = vlan_case(case_name)
        self._verify_set_and_clear(session_id, cleanup_registry, self.vlan_path_for_vid(vid), payload)

    def verify_vlan_config_invalid_payload(self, session_id: str) -> None:
        self.verify_node3_target()
        self._verify_invalid_payload(
            session_id,
            self.vlan_path_for_vid("4094"),
            {"vlanname": "REST_API_BAD_VLAN", "tpid": "invalid-tpid"},
        )

    def verify_ont_create_and_delete(self, session_id: str, cleanup_registry: CleanupRegistry) -> None:
        self.verify_node3_target()
        self._verify_set_and_clear(session_id, cleanup_registry, self.ont_path(), ont_config_payload(self.target()))

    def verify_ont_case_created(self, session_id: str, cleanup_registry: CleanupRegistry, case_name: str) -> None:
        self.verify_node3_target()
        payload = materialize_ont_payload(case_name, self.target())
        cleanup_registry.add(lambda: self.api_client.request("DELETE", self.ont_path(), session=session_id))
        response = self.api_client.request("POST", self.ont_path(), session=session_id, json=payload)
        assert_api_success(response)

    def verify_ont_config_set_and_clear(self, session_id: str, cleanup_registry: CleanupRegistry) -> None:
        self.verify_node3_target()
        self._verify_set_and_clear(session_id, cleanup_registry, self.ont_path(), ont_config_payload(self.target()))

    def verify_ont_config_invalid_payload(self, session_id: str) -> None:
        self.verify_node3_target()
        payload = ont_config_payload(self.target())
        payload["Content"]["registmethod"] = "invalid"
        self._verify_invalid_payload(session_id, self.ont_path(), payload)

    def verify_neox_profile_create_and_delete(
        self,
        session_id: str,
        cleanup_registry: CleanupRegistry,
        profile_type: str,
    ) -> None:
        self.verify_node3_target()
        self.ensure_neox_profile_dependencies(session_id, cleanup_registry, profile_type)
        path = self.neox_profile_path(profile_type)
        payload = self.neox_profile_payload(profile_type)
        cleanup_registry.add(lambda: self.api_client.request("DELETE", path, session=session_id))
        self.delete_neox_profile_if_exists(path, session_id)
        response = self.api_client.request("POST", path, session=session_id, json=payload)
        assert_api_success(response)
        response = self.api_client.request("DELETE", path, session=session_id)
        assert_api_success(response)

    def ensure_neox_profile_dependencies(
        self,
        session_id: str,
        cleanup_registry: CleanupRegistry,
        profile_type: str,
    ) -> None:
        for dependency_type in NEOX_PROFILE_DEPENDENCIES.get(profile_type, []):
            path = self.neox_profile_path(dependency_type)
            cleanup_registry.add(lambda p=path: self.api_client.request("DELETE", p, session=session_id))
            self.delete_neox_profile_if_exists(path, session_id)
            response = self.api_client.request(
                "POST",
                path,
                session=session_id,
                json=self.neox_profile_payload(dependency_type),
            )
            assert_api_success(response)

    def delete_neox_profile_if_exists(self, path: str, session_id: str):
        return delete_profile_if_exists(self.api_client, path, session_id)

    def _verify_mutation_rejected(self, session_id: str, path: str, payload: dict[str, Any]) -> None:
        response = self.api_client.request("POST", path, session=session_id, json=payload)
        assert_api_failure(response)
        response = self.api_client.request("DELETE", path, session=session_id)
        assert_api_failure(response)

    def _verify_set_and_clear(
        self,
        session_id: str,
        cleanup_registry: CleanupRegistry,
        path: str,
        payload: dict[str, Any],
    ) -> None:
        cleanup_registry.add(lambda: self.api_client.request("DELETE", path, session=session_id))
        response = self.api_client.request("POST", path, session=session_id, json=payload)
        assert_api_success(response)
        response = self.api_client.request("DELETE", path, session=session_id)
        assert_api_success(response)

    def _verify_invalid_payload(self, session_id: str, path: str, payload: dict[str, Any]) -> None:
        response = self.api_client.request("POST", path, session=session_id, json=payload)
        assert_api_failure(response, accepted_messages=("invalid json input",))

    def ge_path(self) -> str:
        target = self.target()
        return f"/configNeoXSeries/interface/ge/{target.device_name}/{target.ge_slot_id}/{target.ge_port_id}"

    def nni_path(self) -> str:
        target = self.target()
        return f"/configNeoXSeries/interface/nni/{target.device_name}/{target.nni_slot_id}/{target.nni_port_id}"

    def ont_path(self) -> str:
        target = self.target()
        return (
            f"/configNeoXSeries/interface/remote/{target.device_name}/"
            f"{target.ont_slot_id}/{target.ont_port_id}/{target.ont_id}"
        )

    def vlan_path(self) -> str:
        target = self.target()
        return f"/configNeoxSeries/vlan/{target.device_name}/{target.vlan_id}"

    def vlan_path_for_vid(self, vid: str) -> str:
        target = self.target()
        return f"/configNeoxSeries/vlan/{target.device_name}/{vid}"

    def neox_profile_path(self, profile_type: str) -> str:
        target = self.target()
        return f"/configNeoXSeries/profile/{target.device_name}/{profile_type}/{self.neox_profile_name(profile_type)}"

    def neox_profile_payload(self, profile_type: str) -> dict[str, Any]:
        definition = self.profile_definition(profile_type)
        content = normalize_neox_profile_content(profile_type, definition.get("post_profile_info", {}))
        if profile_type == "ONTTemplateProfile":
            content.update(self.neox_template_refs())
        return {"Content": content}

    def neox_profile_boundary_payload(self, profile_type: str, boundary: str) -> dict[str, Any]:
        payload = neox_profile_minmax_payload(profile_type, boundary)
        if profile_type == "ONTTemplateProfile":
            payload.setdefault("Content", {}).update(self.neox_template_refs())
        return payload

    def neox_template_refs(self) -> dict[str, str]:
        return {
            "alarmprof": self.neox_profile_name("ONTAlarmProfile"),
            "secprof": self.neox_profile_name("ONTSecurityProfile"),
            "ontprof": self.neox_profile_name("ONTONTProfile"),
            "mprof1": self.neox_profile_name("ONTMulticastProfile"),
            "sprof1": self.neox_profile_name("ONTServiceProfile"),
            "susbwproftemplateprof1": self.neox_profile_name("ONTBandwidthProfile"),
            "sdsbwproftemplateprof1": self.neox_profile_name("ONTBandwidthProfile"),
        }

    def neox_profile_name(self, profile_type: str) -> str:
        return NEOX_PROFILE_NAMES[profile_type]

    def profile_definition(self, profile_type: str) -> dict[str, Any]:
        ref = NEOX_PROFILE_CONFIG_REFS[profile_type]
        try:
            return self._profiles[ref]
        except KeyError as error:
            raise NeoXConfigError(f"Missing profile fixture {ref!r} for {profile_type}") from error

    def target(self) -> NeoXTarget:
        dut = self.env_config.dut
        nni = self.env_config.node_target.get("nni", {})
        if not isinstance(nni, dict):
            nni = {}
        return NeoXTarget(
            device_name=dut.device_name,
            ge_slot_id=dut.ge_slot_id,
            ge_port_id=dut.ge_port_id,
            nni_slot_id=required_target_value(nni, "slot_id", "test_targets.nni.slot"),
            nni_port_id=required_target_value(nni, "port_id", "test_targets.nni.port"),
            ont_slot_id=dut.slot_id,
            ont_port_id=dut.port_id,
            ont_id=dut.ont_id,
            ont_sn=dut.ont_sn,
            ont_password=dut.ont_password,
            vlan_id="1314",
        )


def required_target_value(data: dict[str, Any], key: str, source: str) -> str:
    value = data.get(key)
    if value in (None, ""):
        raise NeoXConfigError(f"Missing NeoX target data from YAML: {source}")
    return str(value)


def card_slot_id(node_target: dict[str, Any], card_key: str | None) -> str | None:
    cards = node_target.get("cards", {})
    if not isinstance(cards, dict) or not card_key:
        return None
    card = cards.get(card_key, {})
    if not isinstance(card, dict):
        return None
    value = card.get("slot_id")
    return str(value) if value not in (None, "") else None


def ge_port_payload() -> dict[str, Any]:
    return {
        "Content": {
            "portenable": "enable",
            "auto_nego": "enable",
            "flow": "disable",
            "portspeed": "auto",
            "frametype": "all",
            "portname": "REST_GE_39",
        }
    }


def nni_port_payload() -> dict[str, Any]:
    return {"Content": {"portenable": "enable", "auto_nego": "disable", "flow": "disable", "mode": "uplink"}}


def nni_min_payload() -> dict[str, Any]:
    return load_json_payload(NNI_MIN_PAYLOAD_FILE)


def nni_max_payload() -> dict[str, Any]:
    return load_json_payload(NNI_MAX_PAYLOAD_FILE)


def vlan_payload() -> dict[str, Any]:
    return {"vlanname": "REST_API_VLAN", "fixedport": "*", "untaggedport": "", "forbiddenport": "", "tpid": "default-tpid"}


def vlan_case(case_name: str) -> tuple[str, dict[str, Any]]:
    data = json.loads(VLAN_MINMAX_PAYLOAD_FILE.read_text(encoding="utf-8"))
    case = data["cases"][case_name]
    return str(case["vid"]), copy.deepcopy(case["payload"])


def ont_config_payload(target: NeoXTarget) -> dict[str, Any]:
    return {
        "Content": {
            "sn": target.ont_sn,
            "registmethod": "A",
            "registid": target.ont_password,
            "onttype": "auto",
            "ontenable": "enable",
            "adminstate": "enable",
            "ontdescription": "REST_API_NEOX_ONT",
        }
    }


def ont_min_payload(target: NeoXTarget) -> dict[str, Any]:
    return materialize_ont_payload("min", target)


def ont_max_payload(target: NeoXTarget) -> dict[str, Any]:
    return materialize_ont_payload("max", target)


def neox_profile_minmax_payload(profile_type: str, boundary: str) -> dict[str, Any]:
    split_path = PROFILE_MINMAX_PAYLOAD_DIR / f"{profile_type}.json"
    data = json.loads(split_path.read_text(encoding="utf-8"))
    return copy.deepcopy(data[boundary])


def neox_profile_cli_verify_case(profile_type: str, boundary: str) -> dict[str, Any]:
    data = json.loads(PROFILE_CLI_VERIFY_FILE.read_text(encoding="utf-8"))
    case = data["profiles"][profile_type][boundary]
    return copy.deepcopy(case)


def materialize_ont_payload(case_name: str, target: NeoXTarget) -> dict[str, Any]:
    data = json.loads(ONT_MINMAX_PAYLOAD_FILE.read_text(encoding="utf-8"))
    payload = copy.deepcopy(data["cases"][case_name]["payload"])
    content = payload["Content"]
    for key, value in list(content.items()):
        if isinstance(value, str):
            content[key] = value.format(ont_sn=target.ont_sn, ont_password=target.ont_password)
    return payload


def load_json_payload(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return copy.deepcopy(data["payload"])


def normalize_neox_profile_content(profile_type: str, content: dict[str, Any]) -> dict[str, Any]:
    if profile_type in NEOX_CONTENT_OVERRIDES:
        return dict(NEOX_CONTENT_OVERRIDES[profile_type])
    prefix = NEOX_PREFIXES.get(profile_type)
    if not prefix:
        return dict(content)
    normalized = {}
    for key, value in content.items():
        if key.startswith(prefix):
            normalized[key[len(prefix) :]] = value
        else:
            normalized[key] = value
    return normalized
