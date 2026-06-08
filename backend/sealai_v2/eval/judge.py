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
from sealai_v2.pipeline.stages import _extract_json

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
        data = json.loads(_extract_json(raw))
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
