import re
from app.langgraph_v2.state.sealai_state import SealAIState

EXPERT_PATTERNS = [
    r"\bdp/dt\b", r"\bdruckaufbaurate\b", r"\baed\b", r"\brgd\b",
    r"\bcompound\b", r"\ba7[0-9]\b", r"\bextrusion\b", r"\bshore\b",
    r"\bhnbr\b", r"\bffkm\b", r"\bblistering\b", r"\bgalling\b",
    r"\bside.?load\b", r"\bseitenzug\b", r"\bnorsok\b",
]
BEGINNER_PATTERNS = [
    r"\bwas ist\b", r"\bwas bedeutet\b", r"\bwie funktioniert\b",
    r"\bich wei(ss|ß) nicht\b", r"\bkeine ahnung\b",
    r"\bwelche dichtung\b", r"\bwas.*nehme ich\b",
]
DECIDER_PATTERNS = [
    r"\banlage steht\b", r"\bdringend\b", r"\bsofort\b",
    r"\bwas nehmen wir\b", r"\bnotfall\b", r"\bschnellste\b",
    r"\bkeine zeit\b",
]

def detect_persona(messages: list[str]) -> tuple[str, float]:
    combined = " ".join(messages).lower()
    scores = {
        "erfahrener":  sum(1 for p in EXPERT_PATTERNS   if re.search(p, combined)),
        "einsteiger":  sum(1 for p in BEGINNER_PATTERNS  if re.search(p, combined)),
        "entscheider": sum(1 for p in DECIDER_PATTERNS   if re.search(p, combined)),
    }
    total = sum(scores.values())
    if total == 0:
        return "unknown", 0.0
    best = max(scores, key=lambda k: scores[k])
    return best, round(scores[best] / total, 2)

def update_persona_in_state(state: SealAIState) -> dict:
    """Nach jedem Turn aufrufen. Gibt State-Patch zurück."""
    extracted_texts = []
    for m in (state.messages or []):
        if not hasattr(m, "content") or not m.content:
            continue

        content = m.content
        if isinstance(content, str):
            extracted_texts.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, str):
                    extracted_texts.append(part)
                elif isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text")
                    if text:
                        extracted_texts.append(text)

    if not extracted_texts:
        return {}

    persona, _ = detect_persona(extracted_texts)
    if persona == "unknown":
        return {}
    return {"user_persona": persona}
