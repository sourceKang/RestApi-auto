from __future__ import annotations

from typing import Any

from models.api import EndpointCase
from utils.allure_helpers import allure_step
from utils.assertions import assert_api_failure
from utils.case_metadata import attach_case_id
from utils.names import unique_name


PERMISSION_REJECTION_MESSAGES = ("not authorized", "no access", "permission", "privilege")


def request_endpoint_case(
    api_client: Any,
    env_config: Any,
    session_id: str,
    case: EndpointCase,
    *,
    step: str,
    payload: bool = False,
):
    attach_case_id(case.case_id, case.name)
    name = unique_name(case.name)
    kwargs = {
        "session": session_id,
        "params": case.build_params(env_config, name),
    }
    if payload:
        kwargs["json"] = case.build_payload(env_config, name)
    with allure_step(step):
        return api_client.request(case.method, case.build_path(env_config), **kwargs)


def assert_permission_rejected(response) -> None:
    assert_api_failure(response, accepted_messages=PERMISSION_REJECTION_MESSAGES)
