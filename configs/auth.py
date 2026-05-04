from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from configs.simple_yaml import SimpleYamlError, load_simple_yaml


DEFAULT_AUTH_ACCOUNTS_FILE = Path(__file__).with_name("auth_accounts.yaml")
ROLE_NAMES = ("readwrite", "readonly", "noaccess")


class AuthConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedAccount:
    role: str
    account_name: str
    username: str
    password: str
    source: str


@dataclass(frozen=True)
class AuthConfig:
    path: Path
    raw: dict[str, Any]

    def resolve_profile(self, profile_name: str) -> dict[str, ResolvedAccount]:
        profiles = self.raw.get("profiles", {})
        accounts = self.raw.get("accounts", {})
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            raise AuthConfigError(f"Unknown auth profile {profile_name!r} in {self.path}")

        resolved: dict[str, ResolvedAccount] = {}
        for role in ROLE_NAMES:
            account_key = profile.get(f"{role}_account")
            if not isinstance(account_key, str) or not account_key:
                raise AuthConfigError(f"Auth profile {profile_name!r} must define {role}_account")
            role_accounts = accounts.get(role)
            if not isinstance(role_accounts, dict):
                raise AuthConfigError(f"{self.path} must define accounts.{role}")
            account = role_accounts.get(account_key)
            if not isinstance(account, dict):
                raise AuthConfigError(f"Auth account {role}.{account_key} is not defined in {self.path}")
            resolved[role] = _resolve_account(role, account_key, account)
        return resolved


def load_auth_config(path: str | Path | None = None) -> AuthConfig:
    config_path = Path(path or DEFAULT_AUTH_ACCOUNTS_FILE)
    try:
        raw = load_simple_yaml(config_path)
    except SimpleYamlError as error:
        raise AuthConfigError(str(error)) from error
    if not isinstance(raw, dict):
        raise AuthConfigError(f"{config_path} must contain a mapping")
    if raw.get("version") != 1:
        raise AuthConfigError(f"{config_path} must declare version: 1")
    if not isinstance(raw.get("profiles"), dict):
        raise AuthConfigError(f"{config_path} must contain profiles: mapping")
    if not isinstance(raw.get("accounts"), dict):
        raise AuthConfigError(f"{config_path} must contain accounts: mapping")
    return AuthConfig(path=config_path, raw=raw)


def _resolve_account(role: str, account_name: str, account: dict[str, Any]) -> ResolvedAccount:
    source = str(account.get("source", "unknown"))
    username = account.get("username")
    password = account.get("password")

    if not isinstance(username, str) or not username:
        raise AuthConfigError(f"Auth account {role}.{account_name} must resolve a non-empty username")
    if not isinstance(password, str) or not password:
        raise AuthConfigError(f"Auth account {role}.{account_name} must resolve a non-empty password")

    return ResolvedAccount(
        role=role,
        account_name=account_name,
        username=username,
        password=password,
        source=source,
    )
