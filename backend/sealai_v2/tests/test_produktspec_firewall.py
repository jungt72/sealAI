"""§3.9 STRUCTURAL firewall (Konzept v2/v3) — proven, not promised: the produktspec package never
imports the capability dimension (so manufacturer data can NEVER reach the neutral
Kandidaten-Spezifikation), and the Kandidaten-Spezifikation has NO capability input at all (its only
parameter is a ``Fall``). The keystone is enforced STRUCTURALLY — by AST/regex scan + signature — so it
holds even though the capability store module no longer exists in the tree."""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import sealai_v2.knowledge.produktspec as produktspec
from sealai_v2.knowledge.produktspec.contracts import Fall, MediumSource
from sealai_v2.knowledge.produktspec.spec_service import kandidaten_spezifikation

# Matches ``import capability``/``from capability`` and any dotted form (e.g. ``knowledge.capability``).
_CAP_IMPORT = re.compile(r"^\s*(?:from|import)\s+\S*capability", re.MULTILINE)


def _produktspec_modules() -> list[Path]:
    pkg_dir = Path(produktspec.__path__[0])
    return sorted(pkg_dir.glob("*.py"))


def test_produktspec_never_imports_capability_textually():
    """Cheap textual guard: no produktspec source line may import a ``capability`` module."""
    offenders = [
        f.name
        for f in _produktspec_modules()
        if _CAP_IMPORT.search(f.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"produktspec must not import capability: {offenders}"


def test_produktspec_never_imports_capability_via_ast():
    """Authoritative AST guard — robust to formatting/aliasing/whitespace the regex could miss. Any
    ``import``/``from`` that names a ``capability`` module (bare or dotted, incl. ``knowledge.capability``)
    in ANY produktspec module is a firewall breach."""
    offenders: list[str] = []
    for f in _produktspec_modules():
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                # ``module`` is None for ``from . import x``; the imported names matter too.
                names = [node.module or ""] + [a.name for a in node.names]
            if any(
                n == "capability" or n.endswith(".capability") or ".capability." in n
                for n in names
            ):
                offenders.append(f"{f.name}:{getattr(node, 'lineno', '?')}")
    assert offenders == [], f"produktspec must not import capability (AST): {offenders}"


def test_spec_signature_takes_only_a_fall():
    """The Kandidaten-Spezifikation has NO capability (manufacturer-data) parameter — its ONLY input is a
    ``Fall``. Asserting the signature structurally means capability data has no channel into the spec."""
    params = list(inspect.signature(kandidaten_spezifikation).parameters)
    assert params == ["fall"]
    assert not any("capab" in p.lower() for p in params)


def test_spec_is_invariant_and_deterministic_on_the_same_fall():
    """No capability input → manufacturer data cannot influence the neutral spec; same Fall ⇒ same spec."""
    fall = Fall(
        medium="Mineralöl",
        medium_class="mineraloel",
        medium_source=MediumSource.EXACT,
        temperatur_c=90.0,
        druck_bar=0.0,
        geschwindigkeit_ms=11.0,
        verschmutzung=False,
        schmierung_ok=True,
        belueftet=True,
    )
    assert kandidaten_spezifikation(fall) == kandidaten_spezifikation(fall)
