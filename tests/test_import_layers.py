from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest


pytestmark = pytest.mark.offline

ROOT = Path(__file__).resolve().parents[1]

# Dependency direction from AGENTS.md "架構"; directory roles in docs/engineering-guidelines.md.
# A layer may import itself and the layers listed here. Lazy (in-function) imports count.
ALLOWED: dict[str, set[str]] = {
    "models": set(),
    "config_loader": {"models"},
    "utils": {"models"},
    # cases hold data-driven content and need profile definitions from config_loader.
    "cases": {"models", "config_loader"},
    "clients": {"models", "config_loader", "utils"},
    "services": {"clients", "cases", "models", "config_loader", "utils"},
    # pytest glue and test helpers; must not depend on CLI tools.
    "tests.support": {"services", "clients", "cases", "models", "config_loader", "utils"},
    # CLI orchestration; must not depend on tests or tests.support.
    "tools": {"services", "clients", "cases", "models", "config_loader", "utils"},
    "tests": {"tests.support", "services", "clients", "cases", "models", "config_loader", "utils", "tools"},
    "conftest": {"tests.support"},
}
PACKAGES = ("models", "config_loader", "utils", "cases", "clients", "services", "tools", "tests")
# Top-level directories that are not Python layers (data, docs, generated or machine-local).
NON_PACKAGE_DIRS = {
    ".claude", ".codex", ".codex-tools", ".codex-validation", ".git", ".github", ".pytest_cache", ".venv",
    "__pycache__", "configs", "docs", "local", "reports", "tmp",
}


@dataclass(frozen=True)
class Known:
    reason: str
    remove_when: str


# Existing violations, keyed by (importing file, imported module). Each entry must still
# match a real import; fixing the import without removing the entry fails the test.
KNOWN_VIOLATIONS: dict[tuple[str, str], Known] = {
    ("utils/reporting.py", "tools.generate_integrated_evidence_report"): Known(
        reason="the integrated evidence report writer lives in a CLI module",
        remove_when="the writer moves to utils and tools keeps a thin CLI wrapper (retro plan R-F)",
    ),
    ("utils/reporting.py", "cases.registry"): Known(
        reason="report rendering needs case names and order and shares the file with ReportState",
        remove_when="rendering moves out of utils, leaving only state recording (retro plan R-I)",
    ),
}


@dataclass(frozen=True)
class Edge:
    path: str
    line: int
    source: str
    module: str
    target: str
    lazy: bool


def layer_of_path(rel: str) -> str:
    if rel == "conftest.py":
        return "conftest"
    if rel.startswith("tests/support/"):
        return "tests.support"
    return rel.split("/", 1)[0]


def layer_of_module(module: str) -> str | None:
    if module == "tests.support" or module.startswith("tests.support."):
        return "tests.support"
    top = module.split(".", 1)[0]
    if top == "conftest":
        return "conftest"
    return top if top in PACKAGES else None


def python_sources() -> list[Path]:
    files = [ROOT / "conftest.py"]
    for package in PACKAGES:
        files.extend(path for path in (ROOT / package).rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(files)


class _ImportVisitor(ast.NodeVisitor):
    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.source = layer_of_path(rel)
        self.depth = 0
        self.edges: list[Edge] = []
        self.relative: list[int] = []

    def _function(self, node: ast.AST) -> None:
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function
    visit_Lambda = _function

    def visit_If(self, node: ast.If) -> None:
        test = node.test
        is_type_checking = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )
        if is_type_checking:
            for child in node.orelse:
                self.visit(child)
            return
        self.generic_visit(node)

    def _add(self, node: ast.AST, module: str) -> None:
        target = layer_of_module(module)
        if target is not None:
            self.edges.append(Edge(self.rel, node.lineno, self.source, module, target, self.depth > 0))

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._add(node, alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            self.relative.append(node.lineno)
            return
        module = node.module or ""
        self._add(node, module)
        # `from tests import support` names the tests.support layer.
        if module == "tests":
            for alias in node.names:
                if alias.name == "support":
                    self._add(node, "tests.support")


def scan(paths: list[Path] | None = None) -> tuple[list[Edge], list[str]]:
    edges: list[Edge] = []
    relative: list[str] = []
    for path in paths or python_sources():
        rel = path.relative_to(ROOT).as_posix()
        visitor = _ImportVisitor(rel)
        visitor.visit(ast.parse(path.read_bytes(), filename=rel))
        edges.extend(visitor.edges)
        relative.extend(f"{rel}:{line}" for line in visitor.relative)
    return edges, relative


def violations(edges: list[Edge]) -> list[Edge]:
    return [
        edge
        for edge in edges
        if edge.target != edge.source and edge.target not in ALLOWED[edge.source]
    ]


def _describe(edge: Edge) -> str:
    kind = "lazy " if edge.lazy else ""
    return f"{edge.path}:{edge.line} {edge.source} -> {edge.target} ({kind}import {edge.module})"


def test_every_python_layer_is_declared():
    # Skip non-package directories before walking: reports/ alone holds over a million files.
    top_dirs_with_python = {
        directory.name
        for directory in ROOT.iterdir()
        if directory.is_dir()
        and directory.name not in NON_PACKAGE_DIRS
        and next(directory.rglob("*.py"), None) is not None
    }
    assert top_dirs_with_python <= set(PACKAGES), (
        "Add new top-level Python packages to PACKAGES and ALLOWED: "
        f"{sorted(top_dirs_with_python - set(PACKAGES))}"
    )
    assert set(ALLOWED) == set(PACKAGES) | {"tests.support", "conftest"}


def test_imports_are_absolute():
    _, relative = scan()

    assert relative == [], f"Use absolute project imports: {relative}"


def test_imports_follow_layer_direction():
    found = violations(scan()[0])
    unexpected = [edge for edge in found if (edge.path, edge.module) not in KNOWN_VIOLATIONS]

    assert unexpected == [], "Import against the layer direction (AGENTS.md 架構):\n" + "\n".join(
        _describe(edge) for edge in unexpected
    )


def test_known_violations_are_still_present():
    found = {(edge.path, edge.module) for edge in violations(scan()[0])}
    stale = sorted(key for key in KNOWN_VIOLATIONS if key not in found)

    assert stale == [], f"Fixed violations: remove them from KNOWN_VIOLATIONS: {stale}"


def test_scanner_detects_lazy_and_ignores_type_checking(tmp_path):
    source = tmp_path / "utils" / "sample.py"
    source.parent.mkdir()
    source.write_text(
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from services.alarm import AlarmService\n"
        "def build():\n"
        "    from tools.archive_reports import main\n"
        "    return main\n",
        encoding="utf-8",
    )
    visitor = _ImportVisitor("utils/sample.py")
    visitor.visit(ast.parse(source.read_bytes()))

    assert [(edge.target, edge.lazy, edge.line) for edge in visitor.edges] == [("tools", True, 5)]
    assert [_describe(edge) for edge in violations(visitor.edges)] == [
        "utils/sample.py:5 utils -> tools (lazy import tools.archive_reports)"
    ]
