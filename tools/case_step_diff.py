"""Side-by-side step comparison of one TestLink case between two runs.

Reads the Allure results of both runs, aligns their step trees and diffs the
request/response JSON attachments of each aligned step. Fields that change on
every run are marked as volatile instead of being hidden, so a real change in
them is still visible.
"""

from __future__ import annotations

import html
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.generate_integrated_evidence_report import index_results_by_case, load_allure_results
from utils.redaction import redact, redact_text


VOLATILE_TOKEN_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|\d{4,}"
)
# Measured on two full NODE3 runs (6870 matched attachments): response.elapsed
# differed in 3433; alarm LogID/LogSubID/LogTime/AckTime, body timestamp and
# optical rx/txPower readings differ between runs without a product change.
VOLATILE_KEY_RE = re.compile(r"(?i)^(elapsed|timestamp|\w*time|logid|logsubid|rxpower|txpower)$")
URL_HOST_RE = re.compile(r"^https?://[^/]+", re.I)
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
PREVIEW_LIMIT = 20000
MAX_DIFFS = 200

_CASE_RESULTS: dict[Path, dict[str, list[dict[str, Any]]]] = {}


def load_case_results(allure_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Allure results of a run grouped by TestLink case ID (cached per directory)."""
    key = allure_dir.resolve()
    if key not in _CASE_RESULTS:
        _CASE_RESULTS[key] = dict(index_results_by_case(load_allure_results(allure_dir), allure_dir))
    return _CASE_RESULTS[key]


def normalize_step_name(name: str) -> str:
    return VOLATILE_TOKEN_RE.sub("#", name)


def step_entries(node: dict[str, Any], prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
    """Depth-first (path, step) pairs; repeated names get an occurrence suffix."""
    entries: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    occurrences: Counter[str] = Counter()
    for step in node.get("steps") or []:
        name = normalize_step_name(str(step.get("name") or "step"))
        occurrences[name] += 1
        label = name if occurrences[name] == 1 else f"{name} (#{occurrences[name]})"
        path = prefix + (label,)
        entries.append((path, step))
        entries.extend(step_entries(step, path))
    return entries


def pair_results(
    old: list[dict[str, Any]], new: list[dict[str, Any]]
) -> list[tuple[dict[str, Any] | None, dict[str, Any] | None]]:
    old_by_name = {str(result.get("name")): result for result in old}
    pairs = [(old_by_name.pop(str(result.get("name")), None), result) for result in new]
    pairs.extend((result, None) for result in old_by_name.values())
    return pairs


@dataclass
class FieldDiff:
    path: str
    before: Any
    after: Any
    volatile: bool


@dataclass
class AttachmentPair:
    kind: str
    before: Any
    after: Any
    diffs: list[FieldDiff] = field(default_factory=list)

    @property
    def substantive(self) -> list[FieldDiff]:
        return [diff for diff in self.diffs if not diff.volatile]


@dataclass
class StepPair:
    path: tuple[str, ...]
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    attachments: list[AttachmentPair] = field(default_factory=list)

    @property
    def before_status(self) -> str:
        return str(self.before.get("status")) if self.before else "missing"

    @property
    def after_status(self) -> str:
        return str(self.after.get("status")) if self.after else "missing"

    @property
    def changed(self) -> bool:
        return self.before_status != self.after_status or any(pair.substantive for pair in self.attachments)


def _attachment_kind(attachment: dict[str, Any]) -> str:
    return str(attachment.get("name") or "attachment").split(" ")[0].lower()


def _load_attachment(allure_dir: Path, attachment: dict[str, Any]) -> Any:
    source = attachment.get("source")
    if not source or not (allure_dir / str(source)).exists():
        return None
    text = (allure_dir / str(source)).read_text(encoding="utf-8", errors="replace")
    try:
        return json.loads(text)
    except ValueError:
        return text


def normalize_attachment(kind: str, value: Any) -> Any:
    """Drop the EMS scheme/host from request URLs so runs on different servers align."""
    if kind == "request" and isinstance(value, dict) and isinstance(value.get("url"), str):
        value = dict(value)
        value["url"] = URL_HOST_RE.sub("", value["url"])
    return value


def diff_values(before: Any, after: Any, path: str = "", out: list[FieldDiff] | None = None) -> list[FieldDiff]:
    out = [] if out is None else out
    if len(out) >= MAX_DIFFS:
        return out
    if isinstance(before, dict) and isinstance(after, dict):
        for key in list(dict.fromkeys([*before, *after])):
            diff_values(before.get(key, _MISSING), after.get(key, _MISSING), f"{path}.{key}" if path else str(key), out)
    elif isinstance(before, list) and isinstance(after, list):
        for position in range(max(len(before), len(after))):
            diff_values(
                before[position] if position < len(before) else _MISSING,
                after[position] if position < len(after) else _MISSING,
                f"{path}[{position}]",
                out,
            )
    elif before != after:
        last_key = re.split(r"[.\[]", path)[-1].rstrip("]") if path else ""
        out.append(FieldDiff(path or "(value)", before, after, bool(VOLATILE_KEY_RE.match(last_key))))
    return out


class _Missing:
    def __repr__(self) -> str:
        return "(missing)"


_MISSING = _Missing()


def _pair_attachments(
    before_step: dict[str, Any] | None, after_step: dict[str, Any] | None, before_dir: Path, after_dir: Path
) -> list[AttachmentPair]:
    grouped: dict[str, list[list[Any]]] = {}
    for side, (step, allure_dir) in enumerate(((before_step, before_dir), (after_step, after_dir))):
        for attachment in (step or {}).get("attachments") or []:
            kind = _attachment_kind(attachment)
            value = normalize_attachment(kind, _load_attachment(allure_dir, attachment))
            grouped.setdefault(kind, [[], []])[side].append(value)
    pairs: list[AttachmentPair] = []
    for kind, (old_values, new_values) in grouped.items():
        for position in range(max(len(old_values), len(new_values))):
            old = old_values[position] if position < len(old_values) else _MISSING
            new = new_values[position] if position < len(new_values) else _MISSING
            pairs.append(AttachmentPair(kind, old, new, diff_values(old, new)))
    return pairs


def compare_result_steps(
    before: dict[str, Any] | None, after: dict[str, Any] | None, before_dir: Path, after_dir: Path
) -> list[StepPair]:
    old_steps = dict(step_entries(before)) if before else {}
    new_steps = dict(step_entries(after)) if after else {}
    ordered = list(dict.fromkeys([*new_steps, *old_steps]))
    return [
        StepPair(path, old_steps.get(path), new_steps.get(path), _pair_attachments(old_steps.get(path), new_steps.get(path), before_dir, after_dir))
        for path in ordered
    ]


# ------------------------------------------------------------------ rendering


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _display(value: Any) -> str:
    """Redacted, IP-masked text for display; raw content stays in the linked reports."""
    if value is _MISSING or value is None:
        return "(missing)"
    if isinstance(value, (dict, list)):
        text = json.dumps(redact(value), indent=2, ensure_ascii=False)
    else:
        text = str(value)
    text = IPV4_RE.sub("<ip>", redact_text(text))
    if len(text) > PREVIEW_LIMIT:
        text = text[:PREVIEW_LIMIT] + "\n... (truncated; open the integrated report for full content)"
    return text


def _short(value: Any, limit: int = 160) -> str:
    if value is _MISSING:
        return "(無)"
    text = _display(value).replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


STYLE = """
.case-side{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:0 16px 12px}
.case-side pre{margin:0;max-height:420px;overflow:auto;padding:10px;background:#0f172a;color:#e5e7eb;border-radius:6px;font-size:12px;white-space:pre-wrap;word-break:break-word}
details.step{border-top:1px solid #d9e2ef}details.step>summary{display:grid;grid-template-columns:1fr 90px 90px 220px;gap:10px;padding:9px 16px;cursor:pointer;list-style:none}
details.step>summary::-webkit-details-marker{display:none}details.step.changed>summary{background:#fff7ed;border-left:4px solid #b45309}
.st{font-weight:700;font-size:12px}.st.passed{color:#15803d}.st.failed,.st.broken{color:#b91c1c}.st.missing,.st.skipped{color:#64748b}
table.diff{margin:4px 16px 10px;width:calc(100% - 32px)}tr.volatile td{color:#64748b;font-style:italic}.kind{margin:10px 16px 4px;font-weight:700;font-size:13px}
@media(max-width:900px){.case-side{grid-template-columns:1fr}details.step>summary{grid-template-columns:1fr}}
"""


def _status(value: str) -> str:
    return f'<span class="st {esc(value)}">{esc(value)}</span>'


def render_step_pair(pair: StepPair) -> str:
    substantive = sum(len(item.substantive) for item in pair.attachments)
    volatile = sum(len(item.diffs) - len(item.substantive) for item in pair.attachments)
    summary_note = f"{substantive} 項差異" + (f"（另 {volatile} 項可能為動態值）" if volatile else "")
    blocks = []
    for item in pair.attachments:
        if item.before is _MISSING or item.after is _MISSING:
            # Whole attachment on one side only: say so instead of dumping it twice.
            rows = (
                f'<tr class=""><td>(整個附件)</td><td>{"(無)" if item.before is _MISSING else "有，見下方"}</td>'
                f'<td>{"(無)" if item.after is _MISSING else "有，見下方"}</td><td></td></tr>'
            )
        else:
            rows = "".join(
                f'<tr class="{"volatile" if diff.volatile else ""}"><td>{esc(diff.path)}</td><td>{esc(_short(diff.before))}</td>'
                f'<td>{esc(_short(diff.after))}</td><td>{"可能為動態值" if diff.volatile else ""}</td></tr>'
                for diff in sorted(item.diffs, key=lambda diff: diff.volatile)
            )
        table = (
            f'<table class="diff"><thead><tr><th>欄位</th><th>基準</th><th>比對</th><th></th></tr></thead><tbody>{rows}</tbody></table>'
            if rows
            else '<p class="muted" style="margin:4px 16px">內容相同</p>'
        )
        blocks.append(
            f'<div class="kind">{esc(item.kind)}</div>{table}'
            f'<div class="case-side"><pre>{esc(_display(item.before))}</pre><pre>{esc(_display(item.after))}</pre></div>'
        )
    message_rows = []
    for label, step in (("基準", pair.before), ("比對", pair.after)):
        message = str(((step or {}).get("statusDetails") or {}).get("message") or "")
        if message:
            message_rows.append(f'<p style="margin:4px 16px"><strong>{label}失敗訊息：</strong>{esc(_short(message, 600))}</p>')
    open_attr = " open" if pair.changed else ""
    changed_class = " changed" if pair.changed else ""
    return (
        f'<details class="step{changed_class}"{open_attr}><summary><span>{esc(" › ".join(pair.path))}</span>'
        f"{_status(pair.before_status)}{_status(pair.after_status)}<span class=\"muted\">{esc(summary_note)}</span></summary>"
        f'{"".join(message_rows)}{"".join(blocks) or "<p class=\"muted\" style=\"margin:4px 16px\">沒有附件</p>"}</details>'
    )


def render_case_comparison(
    case_id: str,
    before_label: str,
    after_label: str,
    before_dir: Path | None,
    after_dir: Path | None,
    before_link: str,
    after_link: str,
) -> str:
    """Body HTML (panels) comparing every Allure result of one case."""
    head = (
        f'<p class="muted" style="margin:0 0 12px">基準：<a href="{esc(before_link)}">{esc(before_label)}</a>　'
        f'比對：<a href="{esc(after_link)}">{esc(after_label)}</a>。IP 已遮罩，完整原始內容請開 integrated 報表。'
        "標示「可能為動態值」的欄位（耗時、時間、告警流水號、光功率）不計入差異數。</p>"
    )
    if before_dir is None or after_dir is None:
        return head + '<section class="panel"><p class="muted" style="margin:12px 16px">其中一次沒有 Allure 原始資料，無法比對步驟。</p></section>'
    old_results = load_case_results(before_dir).get(case_id, [])
    new_results = load_case_results(after_dir).get(case_id, [])
    panels = []
    for old, new in pair_results(old_results, new_results):
        steps = compare_result_steps(old, new, before_dir, after_dir)
        changed = sum(1 for step in steps if step.changed)
        title = (new or old or {}).get("name") or case_id
        status = f"{(old or {}).get('status', 'missing')} → {(new or {}).get('status', 'missing')}"
        body = "".join(render_step_pair(step) for step in steps) or '<p class="muted" style="margin:12px 16px">沒有步驟</p>'
        panels.append(
            f'<section class="panel"><div class="panel-title"><h2>{esc(title)}</h2>'
            f'<span class="muted">{esc(status)}；{changed} 個步驟有差異</span></div>{body}</section>'
        )
    if not panels:
        panels.append('<section class="panel"><p class="muted" style="margin:12px 16px">兩次執行都沒有這個 case 的 Allure result。</p></section>')
    return head + "".join(panels)
