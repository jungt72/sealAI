"""I5-Enforcer: kein Narrations-Pfad erfindet eine Zahl.

Kernel-Doktrin: numerische Werte (Drücke, Limits, Toleranzen, Selektionen) entstehen
im Kernel (core/calc/, knowledge/) — nie in der Narration. Heuristik: FLOAT-Literale
im Narrations-Layer sind ein starkes Signal fuer eine erfundene Engineering-Zahl.
Integer werden ignoriert (meist strukturell). Bewusste Nicht-Engineering-Floats
(LLM-temperature, Timeouts) mit '# i5-ok' in derselben Zeile freigeben.

Jinja-Scan (I5b): Zeilen mit <Zahl><Engineering-Einheit> in .jinja-Prompts.
Bewusste Beispiele/Escapes mit '{# i5-ok #}' in derselben Zeile freigeben.
"""

import ast
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[3]

NARRATION_FILES = [
    "backend/sealai_v2/core/l1_generator.py",
    "backend/sealai_v2/core/l3_verifier.py",
    "backend/sealai_v2/prompts/assembler.py",
    "backend/sealai_v2/llm/factory.py",
    "backend/sealai_v2/llm/client.py",
]


# ---------------------------------------------------------------------------
# Jinja-Scanner (I5b)
# ---------------------------------------------------------------------------

# Units (längere/spezifischere Alternativen zuerst, damit die Alternation
# nie eine kürzere Variante bevorzugt; z. B. mbar > bar, MPa > Pa, mm > m).
_JINJA_UNIT_RE = re.compile(
    r"(?<![A-Za-z\d])"  # nicht Ziffer/Buchstabe davor
    r"\d+(?:[.,]\d+)?"  # Zahl (int oder Dezimal)
    r"\s{0,2}"  # optionaler kleiner Whitespace
    r"(?:mbar|kPa|MPa|bar|psi|Pa|mm|cm|m/s|m|°[CF]|[Gg]rad\s+[CF]|rpm|U/min|1/min)"
    r"(?![A-Za-z\d/])",  # kein alphanumerisches Zeichen danach
    re.UNICODE,
)


def _jinja_engineering_hits(text: str) -> list:
    """Gibt (zeile_nr, treffer) für Zeilen mit <Zahl><Engineering-Einheit> zurück.
    Zeilen mit dem Marker 'i5-ok' werden übersprungen.
    """
    hits = []
    for i, line in enumerate(text.splitlines(), start=1):
        if "i5-ok" in line:
            continue
        for m in _JINJA_UNIT_RE.finditer(line):
            hits.append((i, m.group()))
    return hits


# ---------------------------------------------------------------------------
# Python-Float-Scanner (I5a — unverändert)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Jinja-Scanner Akzeptanz-Tests (POSITIV / NEGATIV / ESCAPE)
# ---------------------------------------------------------------------------


def test_jinja_hits_positiv():
    assert _jinja_engineering_hits("bei 16 bar")
    assert _jinja_engineering_hits("200 Grad C")
    assert _jinja_engineering_hits("8 m/s")


def test_jinja_hits_negativ():
    assert not _jinja_engineering_hits("L1 und L3")
    assert not _jinja_engineering_hits("3 Achsen, Schritt 1")


def test_jinja_hits_escape():
    assert not _jinja_engineering_hits("16 bar {# i5-ok #}")
    assert not _jinja_engineering_hits("120 °C {# i5-ok: NBR-Limit #}")


# ---------------------------------------------------------------------------
# Enforcement: keine unannotirten Engineering-Zahlen in den echten Prompts
# ---------------------------------------------------------------------------


def test_no_engineering_numbers_in_jinja_prompts():
    jinja_files = sorted((REPO / "backend" / "sealai_v2").glob("**/*.jinja"))
    problems = []
    for p in jinja_files:
        text = p.read_text(encoding="utf-8")
        rel = str(p.relative_to(REPO))
        for ln, match in _jinja_engineering_hits(text):
            problems.append(f"{rel}:{ln}  {match!r}")
    assert not problems, (
        "I5b-Verstoss — Jinja-Prompt enthält Engineering-Zahl ohne '{# i5-ok #}'.\n"
        "Zahl in den Kernel verschieben oder Zeile mit '{# i5-ok: Begründung #}' freigeben:\n  "
        + "\n  ".join(problems)
    )
