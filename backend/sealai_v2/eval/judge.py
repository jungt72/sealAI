"""LLM-as-judge — RUBRIC-ADHERENCE ONLY (owner-fixed scoring split).

The judge checks whether the rubric is *addressed*: are the must_contain points present, was
the central trap/insight (must_catch) named, was each must_avoid error committed. It does NOT
independently judge factual correctness (same hallucination risk) — axis 1 (Faktische
Korrektheit) is marked ``human_required`` and the 3 hard gates are advisory-only here; the human
oracle (owner) is final on both. Runs on the cheaper judge tier (decision #1).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sealai_v2.core.contracts import AXES, LlmClient, ModelConfig
from sealai_v2.eval.cases import Case
from sealai_v2.llm.structured import extract_json_object

_JUDGE_SYSTEM = (
    "Du bist ein STRIKTER Rubrik-Prüfer für Antworten eines Dichtungstechnik-Assistenten. "
    "Du prüfst AUSSCHLIESSLICH RUBRIK-ADHÄRENZ — NICHT, ob die Antwort fachlich/faktisch korrekt "
    "ist (das entscheidet ein menschliches Orakel). Für Achse 1 (Faktische Korrektheit) gibst du "
    "IMMER 'human_required' aus, niemals ein eigenes Urteil. Für die übrigen genannten Achsen "
    "bewertest du, ob die Antwort den Achsen-Aspekt laut Rubrik ADRESSIERT (pass/partial/fail). "
    "Gib NUR ein JSON-Objekt zurück, ohne Prosa davor/danach:\n"
    "{\n"
    '  "must_contain": [{"point": <text>, "status": "met|partial|unmet"}],\n'
    '  "must_catch": {"named": true|false, "evidence": <kurz>},\n'
    '  "must_avoid": [{"point": <text>, "violated": true|false}],\n'
    '  "axes": {"<nr>": "pass|partial|fail|human_required"},\n'
    '  "notes": <kurz>\n'
    "}\n"
    "Sei konservativ: 'met' nur, wenn der Punkt KLAR adressiert ist. 'must_catch.named' = wurde "
    "die zentrale Falle/Einsicht explizit benannt? 'must_avoid[].violated' = hat die Antwort den "
    "Fehler tatsächlich begangen?"
)


@dataclass(frozen=True)
class JudgeResult:
    case_id: str
    column: str
    must_contain: list[dict] = field(default_factory=list)
    must_catch: dict = field(default_factory=dict)
    must_avoid: list[dict] = field(default_factory=list)
    axes: dict = field(default_factory=dict)
    notes: str = ""
    raw: str = ""
    parse_ok: bool = True


def _build_user(case: Case, answer_text: str) -> str:
    axes_desc = "; ".join(f"{a}={AXES[a]}" for a in case.primary_axes)
    mc = "\n".join(f"- {p}" for p in case.must_contain)
    ma = "\n".join(f"- {p}" for p in case.must_avoid)
    return (
        f"FALL {case.id} ({case.klass})\n"
        f"EINGABE: {case.input}\n\n"
        f"RUBRIK — muss enthalten/adressieren:\n{mc}\n\n"
        f"RUBRIK — zentrale Falle/Einsicht (must_catch): {case.must_catch}\n\n"
        f"RUBRIK — darf NICHT (must_avoid):\n{ma}\n\n"
        f"ZU BEWERTENDE ACHSEN: {axes_desc}\n"
        f"(Achse 1 immer 'human_required'.)\n\n"
        f'KANDIDATEN-ANTWORT:\n"""\n{answer_text}\n"""\n\n'
        "Prüfe NUR Rubrik-Adhärenz und gib das JSON zurück."
    )


_REASK_SYSTEM = (
    "Du prüfst die RE-ASK-Disziplin einer Assistenten-Antwort: fragt die Antwort den Nutzer ERNEUT "
    "nach einer Angabe, die BEREITS bekannt ist (zuvor im Gespräch genannt)? Das ist ein "
    "Rubrik-Verstoß (must_avoid: 'Bekanntes erneut fragen'). Du urteilst NICHT über fachliche "
    "Korrektheit. Gib NUR ein JSON-Objekt zurück, ohne Prosa:\n"
    '{"reasked": [{"topic": <text>, "violated": true|false}]}\n'
    "violated=true NUR, wenn die Antwort die bereits bekannte Angabe AUSDRÜCKLICH erneut erfragt "
    "(eine bloße Erwähnung ist KEIN Verstoß). Sei konservativ."
)


async def judge_no_reask(
    client: LlmClient,
    model_config: ModelConfig,
    answer_text: str,
    already_known: tuple[str, ...],
) -> dict[str, bool]:
    """Re-ask judge-half (owner clarification: keep BOTH re-ask halves). Reuses the ``must_avoid``
    framing — each already-known topic is a must-avoid point ('Bekanntes erneut fragen'). Returns
    ``{topic: reasked?}``. Behavioral rubric-adherence (judge-final, like axes 2–7); fail-safe on a
    parse error = no violation asserted (conservative against false positives — the deterministic
    must_carry half independently proves the fact is present in the prompt)."""
    if not already_known:
        return {}
    topics = "\n".join(f"- {t}" for t in already_known)
    user = (
        f"BEREITS BEKANNT (darf nicht erneut erfragt werden):\n{topics}\n\n"
        f'ANTWORT:\n"""\n{answer_text}\n"""\n\n'
        "Prüfe NUR die Re-Ask-Disziplin und gib das JSON zurück."
    )
    res = await client.generate(
        system=_REASK_SYSTEM, user=user, model_config=model_config
    )
    out = {t: False for t in already_known}
    try:
        data = json.loads(extract_json_object(res.text.strip()))
        for item in data.get("reasked", []):
            topic = str(item.get("topic", "")).strip()
            if topic in out:
                out[topic] = bool(item.get("violated") is True)
    except (ValueError, TypeError, AttributeError):
        return {t: False for t in already_known}  # fail-safe: no violation asserted
    return out


async def judge_answer(
    client: LlmClient,
    model_config: ModelConfig,
    case: Case,
    answer_text: str,
    column: str,
) -> JudgeResult:
    res = await client.generate(
        system=_JUDGE_SYSTEM,
        user=_build_user(case, answer_text),
        model_config=model_config,
    )
    raw = res.text.strip()
    try:
        data = json.loads(extract_json_object(raw))
        return JudgeResult(
            case_id=case.id,
            column=column,
            must_contain=list(data.get("must_contain", [])),
            must_catch=dict(data.get("must_catch", {})),
            must_avoid=list(data.get("must_avoid", [])),
            axes={str(k): str(v) for k, v in dict(data.get("axes", {})).items()},
            notes=str(data.get("notes", ""))[:500],
            raw=raw[:6000],
            parse_ok=True,
        )
    except (ValueError, TypeError):
        return JudgeResult(
            case_id=case.id, column=column, raw=raw[:6000], parse_ok=False
        )
