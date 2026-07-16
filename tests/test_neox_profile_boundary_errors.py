from __future__ import annotations

import pytest

from cases.boundary_cases import numeric_boundary_negative_cases
from services.neox_config.profile_api import delete_profile_if_exists
from services.neox_config.service import NEOX_PROFILE_READWRITE_TYPES
from tests.test_neox_profile import (
    assert_invalid_profile_post_did_not_succeed,
    assert_neox_profile_error_response,
    delete_neox_profile,
    neox_profile_connectivity_guard,
    neox_profile_delay_seconds,
    post_neox_profile,
)
from utils.assertions import assert_api_failure


pytestmark = [
    pytest.mark.neox_config,
    pytest.mark.neox_profile,
    pytest.mark.destructive,
]


@pytest.mark.mutating
@pytest.mark.readwrite
@pytest.mark.parametrize("profile_type", NEOX_PROFILE_READWRITE_TYPES, ids=NEOX_PROFILE_READWRITE_TYPES)
def test_neox_profile_declared_numeric_boundaries_are_rejected(
    neox_config_service,
    api_client,
    env_config,
    session_manager,
    readwrite_session,
    cleanup_registry,
    profile_type,
    request,
):
    """Verify every declared numeric range rejects N(min)-1 and N(max)+1."""

    with neox_profile_connectivity_guard(
        env_config,
        profile_type,
        "numeric_boundary_error",
        neox_profile_delay_seconds(request),
    ):
        neox_config_service.verify_node3_target()
        minimum = neox_config_service.neox_profile_boundary_payload(profile_type, "min")
        maximum = neox_config_service.neox_profile_boundary_payload(profile_type, "max")
        negative_cases = numeric_boundary_negative_cases(minimum, maximum)
        if not negative_cases:
            pytest.skip(f"{profile_type} has no declared numeric min/max range shared by both payloads.")

        path = neox_config_service.neox_profile_path(profile_type)
        cleanup_registry.add(
            lambda: delete_neox_profile(api_client, session_manager, profile_type, path, readwrite_session)
        )

        for negative_case in negative_cases:
            payload = negative_case["payload"]
            neox_config_service.ensure_neox_profile_dependencies(
                readwrite_session,
                cleanup_registry,
                profile_type,
                payload,
            )
            delete_profile_if_exists(api_client, path, readwrite_session)
            response = post_neox_profile(
                api_client,
                profile_type,
                path,
                readwrite_session,
                payload,
                phase=negative_case["name"],
            )
            assert_invalid_profile_post_did_not_succeed(profile_type, negative_case, response)
            assert_neox_profile_error_response(negative_case, response)

            residual = api_client.request("GET", path, session=readwrite_session)
            assert_api_failure(
                residual,
                accepted_messages=("no data", "not found", "does not exist", "invalid parameter"),
            )
