"""Pipeline stages. M1 implements `understand` (soft, annotate-only) and the L1 `answer`
(in ``pipeline.py``); `ground`/`verify`/`cite` are inert stubs (M2/M3) so the
verstehen→grounden→antworten→verifizieren→zitieren chain is visible but does nothing yet.
"""

from __future__ import annotations

import json

from sealai_v2.core.contracts import (
    Answer,
    GroundingFact,
    Intent,
    LlmClient,
    ModelConfig,
    Understanding,
)

_UNDERSTAND_SYSTEM = (
    "Du klassifizierst eine Nutzer-Nachricht an einen Dichtungstechnik-Assistenten GROB nach "
    'Absicht. Antworte NUR mit einem JSON-Objekt {"intent": <label>, "rationale": <kurz>}. '
    "labels: wissensfrage (allgemeine Erklärung/Eigenschaften), fallarbeit (konkrete "
    "Dichtungssituation/Auswahl), faktfrage (kurze Einzelfrage), gespraech "
    "(Begrüßung/Smalltalk/Off-Topic), unklar. Dies ist eine WEICHE Annotation; sie steuert nichts."
)


def _extract_json(raw: str) -> str:
    """Best-effort: pull the first {...} block, tolerating code fences."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if "\n" in s:
            s = s.split("\n", 1)[1]
    start, end = s.find("{"), s.rfind("}")
    return s[start : end + 1] if start != -1 and end > start else s


async def understand(
    client: LlmClient, model_config: ModelConfig, question: str
) -> Understanding:
    """Stage 1 — soft LLM intent. Annotation only; NEVER gates or routes (build-spec §5.1)."""
    res = await client.generate(
        system=_UNDERSTAND_SYSTEM, user=question, model_config=model_config
    )
    raw = res.text.strip()
    try:
        data = json.loads(_extract_json(raw))
        intent = Intent(str(data.get("intent", "unklar")).strip().lower())
        rationale = str(data.get("rationale", ""))[:300]
    except (ValueError, KeyError, TypeError):
        intent, rationale = Intent.UNKLAR, ""
    return Understanding(intent=intent, rationale=rationale, raw=raw[:500])


# --- inert stubs (M2/M3) ---


async def ground(question: str) -> tuple[GroundingFact, ...]:
    """Stage 2 — L2 grounding. STUB (M3): no retrieval yet → empty grounding facts, so L1's
    prompt takes its else-branch ("Allgemeinwissen — verifizieren")."""
    return ()


async def verify(answer: Answer) -> Answer:
    """Stage 4 — L3 verifier. STUB (M2): returns the draft unchanged."""
    return answer


async def cite(answer: Answer) -> Answer:
    """Stage 5 — provenance/citation. STUB: passthrough (L1 self-marks Allgemeinwissen at M1)."""
    return answer
