"""NeoX parallel (xdist) settings shared by the pytest options and tools/run_multi_node.py."""

from __future__ import annotations

from config_loader.auth import AuthConfigError, load_auth_config


def neox_parallel_auth_profile_for_worker(
    selected_auth_profile: str | None,
    parallel_mode: str,
    auth_profiles: str,
    worker_id: str | None,
) -> str | None:
    if parallel_mode == "off" or not worker_id or not auth_profiles.strip():
        return selected_auth_profile
    profiles = [profile.strip() for profile in auth_profiles.split(",") if profile.strip()]
    if not profiles:
        return selected_auth_profile
    if not worker_id.startswith("gw") or not worker_id[2:].isdigit():
        return selected_auth_profile
    worker_index = int(worker_id[2:])

    if worker_index >= len(profiles):
        raise ValueError(
            f"--neox-parallel-auth-profiles defines {len(profiles)} profile(s), "
            f"but xdist worker {worker_id} needs index {worker_index}."
        )
    return profiles[worker_index]


def validate_neox_parallel_settings(
    worker_count: int,
    parallel_mode: str,
    dist_mode: str,
    auth_profiles: str,
) -> None:
    if worker_count <= 1:
        return
    if parallel_mode == "off":
        raise ValueError("xdist workers require --neox-parallel-mode conservative or resource.")
    if dist_mode != "loadgroup":
        raise ValueError("NeoX xdist requires --dist loadgroup so resource groups stay serial.")

    profiles = [profile.strip() for profile in auth_profiles.split(",") if profile.strip()]
    if len(profiles) < worker_count:
        raise ValueError(
            f"xdist requests {worker_count} workers but --neox-parallel-auth-profiles defines "
            f"only {len(profiles)} profile(s)."
        )
    if len(set(profiles)) != len(profiles):
        raise ValueError("--neox-parallel-auth-profiles must not contain duplicate profile names.")

    try:
        auth = load_auth_config()
        signatures = {
            profile: tuple(auth.resolve_profile(profile)[role].username for role in ("readwrite", "readonly", "noaccess"))
            for profile in profiles[:worker_count]
        }
    except AuthConfigError as error:
        raise ValueError(f"Cannot validate NeoX parallel auth profiles: {error}") from error
    if len(set(signatures.values())) != worker_count:
        raise ValueError("NeoX parallel auth profiles must resolve to distinct role usernames per worker.")


def xdist_worker_count(value) -> int:
    if value in {None, 0, "0", "no"}:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("NeoX parallel safety requires an explicit integer xdist worker count.") from error
