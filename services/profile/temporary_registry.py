from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_ROOT = PROJECT_ROOT / "local" / "temporary_resources"
REGISTRY_SCHEMA_VERSION = 1
TEMPORARY_PROFILE_NAME_PATTERN = re.compile(
    r"^#RestApi_[A-Z0-9_]+_\d+b\d+_N\d+_R[A-Z0-9]{1,3}$"
)


@dataclass(frozen=True)
class TemporaryProfileRecord:
    profiletype: str
    profilename: str

    def definition(self) -> dict[str, str]:
        return {
            "profiletype": self.profiletype,
            "profilename": self.profilename,
        }


@dataclass(frozen=True)
class TemporaryServiceTarget:
    resource: str
    path: str


@dataclass(frozen=True)
class TemporaryGraphRecord:
    path: Path
    created_at: datetime
    environment_id: str
    ems_version: str
    node_key: str
    source_profilename: str
    root_name: str
    profiles: tuple[TemporaryProfileRecord, ...]
    service_targets: tuple[TemporaryServiceTarget, ...]


@dataclass(frozen=True)
class TemporaryRegistryScan:
    records: tuple[TemporaryGraphRecord, ...]
    invalid_files: tuple[dict[str, str], ...]


def registry_root(path: str | Path | None = None) -> Path:
    configured = path or os.environ.get("EMS_TEMP_RESOURCE_REGISTRY_DIR")
    return Path(configured) if configured else DEFAULT_REGISTRY_ROOT


def environment_identity(base_url: str) -> str:
    normalized = str(base_url).strip().rstrip("/").lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def create_temporary_graph_record(
    *,
    base_url: str,
    ems_version: str,
    node_key: str,
    source_profilename: str,
    root_name: str,
    profiles: Iterable[dict],
    service_targets: Iterable[dict],
    created_at: datetime | None = None,
    root: str | Path | None = None,
) -> Path:
    timestamp = _utc(created_at or datetime.now(timezone.utc))
    profile_records = tuple(_profile_record(item) for item in profiles)
    target_records = tuple(_service_target(item) for item in service_targets)
    if not profile_records:
        raise ValueError("Temporary graph record must contain at least one profile.")
    if profile_records[-1].profilename != root_name:
        raise ValueError("Temporary graph root must be the last profile in creation order.")
    if not target_records:
        raise ValueError("Temporary graph record must contain its original service target.")

    environment_id = environment_identity(base_url)
    node = _safe_node_key(node_key)
    destination = registry_root(root) / environment_id / node
    destination.mkdir(parents=True, exist_ok=True)
    filename = f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{secrets.token_hex(4)}.json"
    path = destination / filename
    payload = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "created_at": timestamp.isoformat().replace("+00:00", "Z"),
        "environment_id": environment_id,
        "ems_version": str(ems_version),
        "node_key": node,
        "source_profilename": str(source_profilename),
        "root_name": str(root_name),
        "profiles": [
            {"profiletype": item.profiletype, "profilename": item.profilename}
            for item in profile_records
        ],
        "service_targets": [
            {"resource": item.resource, "path": item.path}
            for item in target_records
        ],
    }
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    return path


def remove_temporary_graph_record(path: str | Path | None) -> None:
    if not path:
        return
    Path(path).unlink(missing_ok=True)


def scan_temporary_graph_records(
    *,
    base_url: str,
    node_key: str,
    min_age_hours: float = 24,
    now: datetime | None = None,
    root: str | Path | None = None,
) -> TemporaryRegistryScan:
    if min_age_hours < 0:
        raise ValueError("min_age_hours must be greater than or equal to 0")
    environment_id = environment_identity(base_url)
    node = _safe_node_key(node_key)
    directory = registry_root(root) / environment_id / node
    if not directory.exists():
        return TemporaryRegistryScan(records=(), invalid_files=())

    cutoff = _utc(now or datetime.now(timezone.utc)) - timedelta(hours=min_age_hours)
    records: list[TemporaryGraphRecord] = []
    invalid_files: list[dict[str, str]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            record = _load_record(path)
            if record.environment_id != environment_id or record.node_key != node:
                raise ValueError("record environment or node does not match its registry directory")
            if record.created_at <= cutoff:
                records.append(record)
        except Exception as error:
            invalid_files.append({"path": str(path), "error": str(error)})
    return TemporaryRegistryScan(records=tuple(records), invalid_files=tuple(invalid_files))


def _load_record(path: Path) -> TemporaryGraphRecord:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version={data.get('schema_version')!r}")
    profiles = tuple(_profile_record(item) for item in data.get("profiles") or [])
    service_targets = tuple(_service_target(item) for item in data.get("service_targets") or [])
    if not profiles:
        raise ValueError("record contains no profiles")
    root_name = str(data.get("root_name") or "")
    if profiles[-1].profilename != root_name:
        raise ValueError("record root does not match the last profile")
    if not service_targets:
        raise ValueError("record contains no original service target")
    created_at = datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))
    return TemporaryGraphRecord(
        path=path,
        created_at=_utc(created_at),
        environment_id=str(data["environment_id"]),
        ems_version=str(data.get("ems_version") or ""),
        node_key=_safe_node_key(str(data["node_key"])),
        source_profilename=str(data.get("source_profilename") or ""),
        root_name=root_name,
        profiles=profiles,
        service_targets=service_targets,
    )


def _profile_record(data: dict) -> TemporaryProfileRecord:
    if not isinstance(data, dict):
        raise ValueError("profile record must be an object")
    profiletype = str(data.get("profiletype") or "").strip()
    profilename = str(data.get("profilename") or "").strip()
    if not profiletype or not re.fullmatch(r"[A-Za-z0-9]+Profile", profiletype):
        raise ValueError(f"invalid temporary profile type: {profiletype!r}")
    if not TEMPORARY_PROFILE_NAME_PATTERN.fullmatch(profilename):
        raise ValueError(f"invalid temporary profile name: {profilename!r}")
    return TemporaryProfileRecord(profiletype=profiletype, profilename=profilename)


def _service_target(data: dict) -> TemporaryServiceTarget:
    if not isinstance(data, dict):
        raise ValueError("service target must be an object")
    resource = str(data.get("resource") or "").strip().lower()
    path = str(data.get("path") or "").strip()
    expected_prefix = {"ont": "/ontservice/", "ge": "/geservice/"}.get(resource)
    if expected_prefix is None or not path.startswith(expected_prefix) or ".." in path:
        raise ValueError(f"invalid temporary service target: resource={resource!r}, path={path!r}")
    return TemporaryServiceTarget(resource=resource, path=path)


def _safe_node_key(node_key: str) -> str:
    normalized = str(node_key).strip().upper()
    if not re.fullmatch(r"NODE\d+", normalized):
        raise ValueError(f"invalid node key: {node_key!r}")
    return normalized


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
