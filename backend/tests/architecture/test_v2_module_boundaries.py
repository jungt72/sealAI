"""Executable dependency rules for the V2 modular monolith."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[2] / "sealai_v2"

RULES = {
    "core": ("sealai_v2.api", "sealai_v2.db", "sealai_v2.eval"),
    "orchestration": ("sealai_v2.api", "sealai_v2.db", "sealai_v2.eval"),
    "render": (
        "sealai_v2.api",
        "sealai_v2.db",
        "sealai_v2.llm",
        "sealai_v2.pipeline",
    ),
}


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
        elif isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)


def test_v2_module_dependencies_point_inward():
    violations: list[str] = []
    for module, forbidden in RULES.items():
        for path in sorted((ROOT / module).rglob("*.py")):
            for imported in _imports(path):
                if imported.startswith(forbidden):
                    violations.append(
                        f"{path.relative_to(ROOT)} imports forbidden {imported}"
                    )
    assert not violations, "\n".join(violations)
