from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class SessionRole(str, Enum):
    READWRITE = "readwrite"
    READONLY = "readonly"
    NOACCESS = "noaccess"


@dataclass(frozen=True)
class ApiResponse:
    status_code: int
    json: Any
    text: str
    elapsed: float
    request_id: str
    method: str
    url: str

    @property
    def retstatus(self) -> str | None:
        if isinstance(self.json, dict):
            value = self.json.get("retstatus")
            return str(value) if value is not None else None
        return None

    @property
    def retresult(self) -> str:
        if isinstance(self.json, dict):
            return str(self.json.get("retresult", ""))
        return self.text


PayloadFactory = Callable[[Any, str], dict[str, Any]]
PathFactory = Callable[[Any], str]
ParamsFactory = Callable[[Any, str], dict[str, Any]]
CleanupFactory = Callable[[Any, str, ApiResponse], None]


@dataclass(frozen=True)
class EndpointCase:
    name: str
    method: str
    domain: str
    path: str | PathFactory
    case_id: str | None = None
    expected_success: bool = True
    payload_factory: PayloadFactory | None = None
    params_factory: ParamsFactory | None = None
    cleanup: CleanupFactory | None = None

    def build_path(self, env: Any) -> str:
        if callable(self.path):
            return self.path(env)
        return self.path

    def build_payload(self, env: Any, unique_name: str) -> dict[str, Any] | None:
        if self.payload_factory is None:
            return None
        return self.payload_factory(env, unique_name)

    def build_params(self, env: Any, unique_name: str) -> dict[str, Any] | None:
        if self.params_factory is None:
            return None
        return self.params_factory(env, unique_name)
