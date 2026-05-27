from __future__ import annotations


def delete_profile_if_exists(api_client, path: str, session_id: str):
    response = api_client.request("GET", path, session=session_id)
    if isinstance(response.json, dict) and response.json.get("retstatus") == "Success":
        return api_client.request("DELETE", path, session=session_id)
    return response
