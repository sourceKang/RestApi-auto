from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config_loader import load_environment
from config_loader.settings import EnvironmentConfig


@dataclass(frozen=True)
class RunContext:
    """Resolved execution context for one pytest run."""

    env: EnvironmentConfig
    node: str | None
    auth_profile: str | None

    @property
    def node_key(self) -> str:
        return self.env.dut.node_key

    @property
    def selected_auth_profile(self) -> str:
        return self.env.auth_profile


def build_run_context(config: Any) -> RunContext:
    node = config.getoption("--ems-node")
    auth_profile = config.getoption("--auth-profile")
    return RunContext(
        env=load_environment(node=node, auth_profile=auth_profile),
        node=node,
        auth_profile=auth_profile,
    )
