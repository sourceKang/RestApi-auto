from __future__ import annotations


def profile_read_path(path: str) -> str:
    parts = path.strip("/").split("/")
    if len(parts) != 5 or parts[:2] != ["configNeoXSeries", "profile"]:
        raise ValueError(f"Unsupported NeoX profile mutation path: {path}")
    _prefix, _resource, _device_name, profile_type, profile_name = parts
    return f"/profile/{profile_type}/{profile_name}"


def delete_profile_if_exists(api_client, path: str, session_id: str):
    response = api_client.request("GET", profile_read_path(path), session=session_id)
    if isinstance(response.json, dict) and response.json.get("retstatus") == "Success":
        return api_client.request("DELETE", path, session=session_id)
    return response
