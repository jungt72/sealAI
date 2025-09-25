from __future__ import annotations
from typing import Dict, Any
from app.services.langgraph.policies.model_routing import RoutingContext, llm_params_for, should_use_llm
from app.services.langgraph.llm_factory import get_llm

def explain(state: Dict[str, Any]) -> Dict[str, Any]:
    if not should_use_llm("explain"):
        return state
    ctx = RoutingContext(
        node="explain",
        confidence=state.get("confidence"),
        red_flags=bool(state.get("red_flags")),
        regulatory=bool(state.get("regulatory")),
    )
    llm_cfg = llm_params_for("explain", ctx)
    # sanitize unsupported kwargs
    llm_cfg.pop("top_p", None)
    llm = get_llm(**llm_cfg)

    params = state.get("params", {})
    derived = state.get("derived", {})
    sources = state.get("sources", [])
    prompt = (
        "Erkläre die Auswahlkriterien kurz und sachlich. Nutze nur PARAMS, abgeleitete Werte und Quellen. "
        "Keine Produkte, keine Entscheidungen. Quellen benennen.\n"
        f"PARAMS: {params}\nDERIVED: {derived}\nSOURCES: {sources}\n"
        "Gib 3–6 Sätze."
    )
    msg = llm.invoke([{"role": "user", "content": prompt}])
    state.setdefault("messages", []).append({"role": "assistant", "content": msg.content})
    return state
