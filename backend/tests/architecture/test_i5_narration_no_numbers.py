"""I5-Enforcer: kein Narrations-Pfad erfindet eine Zahl.

Kernel-Doktrin: numerische Werte (Drücke, Limits, Toleranzen, Selektionen) entstehen
im Kernel (core/calc/, knowledge/) — nie in der Narration. Heuristik: FLOAT-Literale
im Narrations-Layer sind ein starkes Signal fuer eine erfundene Engineering-Zahl.
Integer werden ignoriert (meist strukturell). Bewusste Nicht-Engineering-Floats
(LLM-temperature, Timeouts) mit '# i5-ok' in derselben Zeile freigeben.
Grenze: .jinja-Prompts werden (noch) nicht gescannt.
"""

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[3]

NARRATION_FILES = [
    "backend/sealai_v2/core/l1_generator.py",
    "backend/sealai_v2/core/l3_verifier.py",
    "backend/sealai_v2/prompts/assembler.py",
    "backend/sealai_v2/llm/factory.py",
    "backend/sealai_v2/llm/client.py",
]


def _float_hits(path):
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    hits = []
    for node in ast.walk(ast.parse(src, filename=str(path))):
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            line = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else ""
            if "i5-ok" in line:
                continue
            hits.append((node.lineno, node.value, line.strip()))
    return hits


def test_no_float_literals_in_narration():
    problems = []
    for rel in NARRATION_FILES:
        p = REPO / rel
        if not p.exists():
            continue
        for ln, val, line in _float_hits(p):
            problems.append(f"{rel}:{ln}  float {val!r}  ->  {line}")
    assert not problems, (
        "I5-Verstoss — Narration erfindet Zahl(en). Wert in den Kernel verschieben "
        "oder bewussten Nicht-Engineering-Float mit '# i5-ok' markieren:\n  "
        + "\n  ".join(problems)
    )
