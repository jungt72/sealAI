# backend/app/services/langgraph/graph/consult/domain_router.py
from __future__ import annotations
import json
from typing import List
from langchain_openai import ChatOpenAI
from app.services.langgraph.llm_router import get_router_llm, get_router_fallback_llm
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from app.services.langgraph.prompting import render_template, messages_for_template, strip_json_fence
from .config import ENABLED_DOMAINS

def detect_domain(llm: ChatOpenAI, msgs: List[AnyMessage], params: dict) -> str:
    router = llm or get_router_llm()
    prompt = render_template(
        "domain_router.jinja2",
        messages=messages_for_template(msgs),
        params_json=json.dumps(params, ensure_ascii=False),
        enabled_domains=ENABLED_DOMAINS,
    )
    # 1st pass
    resp = router.invoke([HumanMessage(content=prompt)])
    domain, conf = None, 0.0
    try:
        data = json.loads(strip_json_fence(resp.content or ""))
        domain = str((data.get("domain") or "")).strip().lower()
        conf = float(data.get("confidence") or 0.0)
    except Exception:
        domain, conf = None, 0.0

    # Fallback, wenn unsicher
    if (domain not in ENABLED_DOMAINS) or (conf < 0.70):
        fb = get_router_fallback_llm()
        try:
            resp2 = fb.invoke([HumanMessage(content=prompt)])
            data2 = json.loads(strip_json_fence(resp2.content or ""))
            d2 = str((data2.get("domain") or "")).strip().lower()
            c2 = float(data2.get("confidence") or 0.0)
            if (d2 in ENABLED_DOMAINS) and (c2 >= conf):
                domain, conf = d2, c2
        except Exception:
            pass

    # Heuristische Fallbacks – nur Nutzertext
    if (domain not in ENABLED_DOMAINS) or (conf < 0.40):
        utter = ""
        for m in reversed(msgs or []):
            if hasattr(m, "content") and getattr(m, "content"):
                if isinstance(m, HumanMessage):
                    utter = (m.content or "").lower().strip()
                    break
        if "wellendichtring" in utter or "rwdr" in utter:
            domain = "rwdr"
        elif "stangendichtung" in utter or "kolbenstange" in utter or "hydraulik" in utter:
            domain = "hydraulics_rod"
        elif (params.get("bauform") or "").upper().startswith("BA"):
            domain = "rwdr"
        elif ENABLED_DOMAINS:
            domain = ENABLED_DOMAINS[0]
        else:
            domain = "rwdr"
    return domain
