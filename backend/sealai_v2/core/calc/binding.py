"""M8-A — deterministic provenance binding: remembered case facts → calc-registry inputs.

DETERMINISTIC + DECLARED (owner-confirmed mapping table, 2026-06-10): the agent never decides
which fact feeds which input. v1 binds exactly two facts:

- ``wellendurchmesser`` → ``d1_mm`` — shaft Ø at the running surface, standard direct-on-shaft
  case (sleeve/Laufbuchse parked); unit ``mm``.
- ``drehzahl`` → ``rpm`` — accepted unit spellings via the curated synonym table below.

Unit recognition = **normalize → exact synonym lookup** (NOT regex alternation, NOT fuzzy match,
NOT typo correction). Normalization is a fixed, deterministic transform: strip ALL whitespace,
casefold, canonicalize a small fixed glyph set (``⁻¹``/``^-1`` → ``-1``). Then a token is bound
ONLY if it is in the curated, provably-equivalent ``_UNIT_SYNONYMS`` set for that input's unit.

FAIL-CLOSED everywhere (the kern stays honest): any token outside the synonym set stays UNBOUND.
A mapped feld that does not bind emits a structured ``BindClarification`` (+ a visible note) so the
UX can recover WITHOUT guessing — never an auto-bind. Recovery classes:
  - ``no_value``         — no number → re-enter guidance (no one-click).
  - ``unit_missing``     — number, no unit → one-click append the canonical (SAFE).
  - ``unit_known_other`` — a REAL but non-accepted unit (cm/grad/…) → NO one-click; appending the
    canonical to a known unit of different scale/dimension is a silent wrong-bind (e.g. cm→mm = 10×).
    The user must re-enter explicitly (unit conversion is a deferred enhancement).
  - ``unit_unrecognized``— garbage/typo (``u/mon``) → one-click "meintest du <canonical>?" (appending
    the canonical to a meaningless token introduces no scale error, so the reported case recovers).

German number conventions: decimal comma; a thousands-dot form ("4.000") counts only WITH an
adjoining unit (so unitless "4.000" → unit_missing, never silently 4000). Origins are preserved per
bound input so the render/citation stays honest (the V1 "provenance loss on user values" lesson).

schnurstaerke/nuttiefe stay PARKED (owner decision 3). druck→p_bar was UNPARKED in Phase 2a
(owner-gated): pressure feeds the PV kern, binding ONLY in bar (fail-closed on any other unit).
Pure core: no I/O, no LLM.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from sealai_v2.core.contracts import RememberedFact

# German number: thousands-dot groups (only meaningful with a unit) or a plain integer/decimal-comma.
_NUM = r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)"

# Split grammar: a leading number + the REST as a single trailing unit token (may be empty). Anchored
# full-match so a number must lead; the token is normalized + looked up (not regex-matched) below.
_VALUE_RE = re.compile(rf"^\s*{_NUM}\s*(?P<unit>.*?)\s*$")


def _to_float(num: str) -> float:
    return float(num.replace(".", "").replace(",", "."))


def _normalize_unit(tok: str) -> str:
    """Deterministic, fixed: strip ALL whitespace, casefold, canonicalize a small glyph set. The
    result feeds an EXACT set lookup — never fuzzy, never typo-correcting."""
    s = "".join(tok.split())
    s = s.casefold()
    s = s.replace("⁻¹", "-1").replace("^-1", "-1")
    return s


# Per-canonical-unit synonym sets (NORMALIZED forms). Curated, provably-equivalent ONLY — extending
# this is an owner decision, never an agent judgment call. rpm coverage equals the prior grammar plus
# the owner-approved archaic ``UpM``/``Upm`` (→ "upm"); mm adds the spelled-out ``Millimeter``.
_UNIT_SYNONYMS: dict[str, frozenset[str]] = {
    "mm": frozenset({"mm", "millimeter"}),
    "rpm": frozenset({"u/min", "1/min", "min-1", "rpm", "upm"}),
    # Phase 2a (owner-gated unpark): pressure binds ONLY in bar — EXACT, no other spelling. mbar/
    # kPa/MPa/Pa/psi are real pressure units of a different scale → _KNOWN_UNITS (clarify, no rescale).
    "bar": frozenset({"bar"}),
}

# Known OTHER units (NORMALIZED → dimension). Membership here means a REAL unit that is NOT the
# accepted one → classify ``unit_known_other`` and NEVER offer a one-click canonical append (a
# same-dimension/different-scale append, e.g. cm→mm, is a 10× silent wrong-bind; a different-dimension
# token is nonsense). Explicit conversion is a deferred enhancement. Dimension is carried for honest
# messaging + that future conversion.
_KNOWN_UNITS: dict[str, str] = {
    # length
    "cm": "length",
    "dm": "length",
    "m": "length",
    "inch": "length",
    "zoll": "length",
    # speed / frequency
    "hz": "frequency",
    "/s": "frequency",
    "/sec": "frequency",
    # angle
    "grad": "angle",
    "°": "angle",
    "deg": "angle",
    # pressure (Phase 2a) — real units of a DIFFERENT scale than the accepted bar: never rescaled
    # (appending "bar" to "500 mbar"/"0.5 MPa" would be a silent ×1000/×10 wrong-bind).
    "mbar": "pressure",
    "kpa": "pressure",
    "mpa": "pressure",
    "pa": "pressure",
    "psi": "pressure",
}

# Reasons whose one-click recovery (append the canonical to the raw number) introduces NO scale error.
_ONE_CLICK_REASONS = frozenset({"unit_missing", "unit_unrecognized"})


def _known_dimension(unit_tok: str) -> str:
    """The physical dimension if ``unit_tok`` is a KNOWN (real but unaccepted) unit, else "". Tries
    the normalized token, then its trailing letter run — so an English-decimal artifact (the German
    number grammar reads "0.5 MPa" as number "0" + unit ".5 MPa") still resolves to the known pressure
    unit and classifies ``unit_known_other`` (no silent one-click rescale to bar), never the
    one-click ``unit_unrecognized``. Never affects the BIND decision — only the clarify classification."""
    norm = _normalize_unit(unit_tok)
    if norm in _KNOWN_UNITS:
        return _KNOWN_UNITS[norm]
    m = re.search(r"[a-z]+$", norm)
    return _KNOWN_UNITS.get(m.group(), "") if m else ""


@dataclass(frozen=True)
class _Bind:
    input_name: str  # calc-registry input (e.g. "d1_mm")
    unit_key: str  # → _UNIT_SYNONYMS
    suggested: str  # canonical DISPLAY unit shown to the user (e.g. "U/min")
    dimension: str  # the field's physical dimension (length|frequency|…) — drives clarify wording
    #               (scale mismatch vs wrong-kind-of-quantity)


# feld (lowercased) → binding. The DECLARED mapping table — extending it is an owner decision.
_BINDINGS: dict[str, _Bind] = {
    "wellendurchmesser": _Bind("d1_mm", "mm", "mm", "length"),
    "drehzahl": _Bind("rpm", "rpm", "U/min", "frequency"),
    # Phase 2a (owner-gated): pressure feeds the PV kern; binds only in bar (fail-closed otherwise).
    "druck": _Bind("p_bar", "bar", "bar", "pressure"),
}


@dataclass(frozen=True)
class BindClarification:
    """A structured, fail-closed recovery hint for a MAPPED feld that did not bind. The binder owns
    the suggestion (kernel channel); the panel renders the confirm. ``one_click`` is the BACKEND-OWNED
    'append the canonical is safe' policy — the never-silently-rescale rule lives here, not in the UI."""

    feld: str  # case-state field the user re-settles (e.g. "drehzahl")
    input_name: str  # calc input it would feed (e.g. "rpm")
    raw_value: str  # the number as typed ("5000"); the full stripped wert when no number (no_value)
    raw_unit: str  # the trailing token as typed ("u/mon"); "" when missing
    reason: str  # no_value | unit_missing | unit_known_other | unit_unrecognized
    suggested_unit: str  # the param's expected canonical display unit (e.g. "U/min")
    known_dimension: str = ""  # the TYPED unit's dimension, set for unit_known_other (length|frequency|angle)
    expected_dimension: str = (
        ""  # the FIELD's dimension — compare to known_dimension: equal ⇒ scale
    )
    #                               mismatch ("give it in mm"); differ ⇒ wrong kind of quantity
    one_click: bool = (
        False  # True ⇒ appending suggested_unit to raw_value is a SAFE recovery
    )


@dataclass(frozen=True)
class BindingResult:
    params: dict[str, float] = field(default_factory=dict)
    origins: dict[str, str] = field(
        default_factory=dict
    )  # input name → human-readable origin
    sources: dict[str, str] = field(
        default_factory=dict
    )  # input name → source case-state feld (M8: derived-fact parent-refs)
    notes: tuple[str, ...] = ()  # surfaced drops — fail-closed is visible, never silent
    clarifications: tuple[
        BindClarification, ...
    ] = ()  # structured recovery hints (mapped felder only)


def _origin(f: RememberedFact) -> str:
    if f.provenance == "user-form":
        return f"vom Nutzer im Formular eingegeben ({f.feld}: »{f.wert}«, user-form)"
    if f.provenance == "user-edited":
        return f"vom Nutzer bestätigt/bearbeitet ({f.feld}: »{f.wert}«, user-edited)"
    return f"vom Nutzer genannt ({f.feld}: »{f.wert}«)"


def _classify(
    bind: _Bind, feld: str, number: str | None, unit_tok: str, raw_wert: str
) -> BindClarification:
    """Classify an unbindable MAPPED value into a fail-closed recovery class. Never binds."""
    if number is None:
        reason, raw_value, raw_unit, dim = "no_value", raw_wert, "", ""
    elif not unit_tok:
        reason, raw_value, raw_unit, dim = "unit_missing", number, "", ""
    else:
        dim = _known_dimension(unit_tok)
        reason = "unit_known_other" if dim else "unit_unrecognized"
        raw_value, raw_unit = number, unit_tok
    return BindClarification(
        feld=feld,
        input_name=bind.input_name,
        raw_value=raw_value,
        raw_unit=raw_unit,
        reason=reason,
        suggested_unit=bind.suggested,
        known_dimension=dim,
        expected_dimension=bind.dimension,
        one_click=reason in _ONE_CLICK_REASONS,
    )


def _clar_note(raw_wert: str, c: BindClarification) -> str:
    """A visible, reason-aware drop note (so L1 prose can mention 'Einheit unklar' honestly). Always
    names the feld + 'nicht gebunden'."""
    if c.reason == "no_value":
        return (
            f"{c.feld}: kein Wert erkannt (Zahl + Einheit »{c.suggested_unit}« erforderlich) "
            f"— nicht gebunden"
        )
    if c.reason == "unit_missing":
        return (
            f"{c.feld}: Einheit fehlt — »{c.suggested_unit}« erwartet (»{raw_wert}«) "
            f"— nicht gebunden"
        )
    if c.reason == "unit_known_other":
        return (
            f"{c.feld}: »{c.raw_unit}« ({c.known_dimension}) wird hier nicht unterstützt — "
            f"bitte in »{c.suggested_unit}« angeben — nicht gebunden"
        )
    return (
        f"{c.feld}: Einheit »{c.raw_unit}« unklar — meintest du »{c.suggested_unit}«? "
        f"(»{raw_wert}«) — nicht gebunden"
    )


def bind_params(facts: Iterable[RememberedFact]) -> BindingResult:
    """Bind remembered facts to calc inputs per the declared table. Deterministic; fail-closed.
    A mapped feld that does not bind yields a structured ``BindClarification`` + a visible note —
    never an auto-bind, never a guess."""
    params: dict[str, float] = {}
    origins: dict[str, str] = {}
    sources: dict[str, str] = {}
    notes: list[str] = []
    clarifications: list[BindClarification] = []
    seen: dict[str, str] = {}  # feld → first wert (conflict detection)
    conflicted: set[str] = set()

    for f in facts:
        # M8 boundary: a kernel-computed value is an OUTPUT, never an input — never bind it back.
        if f.provenance == "kernel_computed":
            continue
        feld = f.feld.strip().lower()
        bind = _BINDINGS.get(feld)
        if bind is None:
            continue  # unmapped felder are simply not calc inputs — no noise

        if feld in seen:
            if f.wert.strip() != seen[feld] and feld not in conflicted:
                conflicted.add(feld)
                params.pop(bind.input_name, None)
                origins.pop(bind.input_name, None)
                sources.pop(bind.input_name, None)
                notes.append(
                    f"{feld}: widersprüchliche Werte (»{seen[feld]}« vs »{f.wert.strip()}«) — "
                    f"nicht gebunden (bitte bestätigen)"
                )
            continue
        seen[feld] = f.wert.strip()

        m = _VALUE_RE.match(f.wert)
        number = m.group(1) if m else None
        unit_tok = (m.group("unit") if m else "").strip()

        if number is not None and unit_tok:
            if _normalize_unit(unit_tok) in _UNIT_SYNONYMS[bind.unit_key]:
                params[bind.input_name] = _to_float(number)
                origins[bind.input_name] = _origin(f)
                sources[bind.input_name] = feld  # parent-ref for the derived fact
                continue

        # Did not bind → fail-closed: classify, clarify, surface a note. Never guessed, never bound.
        clar = _classify(bind, feld, number, unit_tok, f.wert.strip())
        clarifications.append(clar)
        notes.append(_clar_note(f.wert.strip(), clar))

    return BindingResult(
        params=params,
        origins=origins,
        sources=sources,
        notes=tuple(notes),
        clarifications=tuple(clarifications),
    )
