from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.neox_config.profile_api import delete_profile_if_exists, profile_read_path


class FakeApiClient:
    def __init__(self, get_status: str = "Fail") -> None:
        self.get_status = get_status
        self.calls = []

    def request(self, method, path, *, session):
        self.calls.append((method, path, session))
        if method == "GET":
            return SimpleNamespace(json={"retstatus": self.get_status})
        return SimpleNamespace(json={"retstatus": "Success"})


def test_profile_read_path_maps_neox_mutation_path_to_generic_profile_get() -> None:
    assert profile_read_path(
        "/configNeoXSeries/profile/NODE3/WeightProfile/RestApi_NeoX_Weight"
    ) == "/profile/WeightProfile/RestApi_NeoX_Weight"


def test_profile_read_path_rejects_unrelated_path() -> None:
    with pytest.raises(ValueError, match="Unsupported NeoX profile mutation path"):
        profile_read_path("/profile/WeightProfile/RestApi_NeoX_Weight")


def test_delete_profile_if_exists_reads_generic_path_then_deletes_mutation_path() -> None:
    client = FakeApiClient(get_status="Success")
    mutation_path = "/configNeoXSeries/profile/NODE3/WeightProfile/RestApi_NeoX_Weight"

    delete_profile_if_exists(client, mutation_path, "session")

    assert client.calls == [
        ("GET", "/profile/WeightProfile/RestApi_NeoX_Weight", "session"),
        ("DELETE", mutation_path, "session"),
    ]


def test_delete_profile_if_exists_does_not_delete_missing_profile() -> None:
    client = FakeApiClient(get_status="Fail")
    mutation_path = "/configNeoXSeries/profile/NODE3/WeightProfile/RestApi_NeoX_Weight"

    delete_profile_if_exists(client, mutation_path, "session")

    assert client.calls == [
        ("GET", "/profile/WeightProfile/RestApi_NeoX_Weight", "session"),
    ]