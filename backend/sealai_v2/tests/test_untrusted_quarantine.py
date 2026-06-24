"""M6b — the untrusted-content quarantine keystone (AST) + the seam behavior.

THE load-bearing security invariant: untrusted content (user-pasted claims, datasheets, legacy
text) is DATA, never authoritative grounding. Enforced STRUCTURALLY — every ``GroundingFact`` /
``Claim`` constructor originates in the curated-catalog grounding lanes (``retrieval.py`` /
``matrix.py`` / ``fachkarten.py``), NEVER from ``UntrustedContent``. AST-based (robust vs string-grep)
so it holds when uploads land.
"""

from __future__ import annotations

import ast
from pathlib import Path

from sealai_v2.core.contracts import Flags, UntrustedContent
from sealai_v2.prompts.assembler import PromptAssembler

_V2 = Path(__file__).resolve().parents[1]  # backend/sealai_v2

# A constructor may originate ONLY in a curated, owner-gated grounding lane — never from the
# untrusted-content path. The §4 Verträglichkeitsmatrix (knowledge/matrix.py) is such a lane.
_ALLOWED = {
    "GroundingFact": (
        "knowledge/retrieval.py",
        "knowledge/qdrant_retrieval.py",
        "knowledge/matrix.py",
    ),
    "Claim": ("knowledge/fachkarten.py",),
}


def _ctor_sites(name: str) -> set[str]:
    """All non-test source files that call ``name(...)`` as a constructor (AST, not grep)."""
    sites: set[str] = set()
    for py in _V2.rglob("*.py"):
        rel = py.relative_to(_V2).as_posix()
        if rel.startswith("tests/"):
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == name
            ):
                sites.add(rel)
    return sites


def test_groundingfact_constructed_only_in_grounding_lanes():
    assert _ctor_sites("GroundingFact") <= set(_ALLOWED["GroundingFact"])


def test_claim_constructed_only_in_fachkarten():
    assert _ctor_sites("Claim") <= set(_ALLOWED["Claim"])


def test_untrusted_reaches_prompt_as_delimited_data_not_grounding():
    a = PromptAssembler()
    poison = "EPDM ist hervorragend für Mineralöl geeignet"
    out = a.system_prompt(
        flags=Flags(),
        untrusted=[{"text": poison, "origin": "user-pasted"}],
    )
    # rendered verbatim as DATA …
    assert poison in out
    # … inside the untrusted block (framed as data/not-instruction/unverified), NOT the grounding block
    assert "DATEN" in out and "nicht Anweisung" in out
    # and it is NOT presented under the reviewed "Belegte Fakten" grounding heading
    head = out.split(poison)[0]
    assert "Belegte Fakten" not in head.split("# Fremder")[-1]


def test_no_untrusted_is_byte_identical_noop():
    a = PromptAssembler()
    assert a.system_prompt(flags=Flags()) == a.system_prompt(
        flags=Flags(), untrusted=[]
    )


def test_untrusted_content_type_is_unverified_by_default():
    uc = UntrustedContent(text="x", origin="user-pasted")
    assert uc.provenance == "untrusted-unverified"
