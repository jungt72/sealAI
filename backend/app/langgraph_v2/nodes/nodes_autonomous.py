from typing import Any, Dict, List, Optional
import json
import logging
import uuid
from langchain_core.messages import BaseMessage

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state.sealai_state import SealAIState, TaskItem, WorkingMemory
from app.langgraph_v2.utils.jinja_renderer import render_template
from app.langgraph_v2.utils.json_sanitizer import extract_json_obj
from app.langgraph_v2.utils.llm_factory import run_llm, get_model_tier
from app.langgraph_v2.utils.messages import latest_user_text

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are the Lead Technical Supervisor for SealAI. 
Your goal is to solve the user's request by delegating tasks to specialized agents.

CURRENT STATE:
Tasks: {task_list}

CONVERSATION HISTORY:
{history}

Latest User Input: {user_text}

AVAILABLE WORKERS:
- 'knowledge_worker': SEARCH HERE for specific products, chemical compatibility, norms, manufacturers (e.g. 'Kyrolon', 'Simmerring').
- 'design_worker': Can validate technical parameters and suggest seal designs.
- 'calc_worker': Can perform physical calculations (PV-values, friction, etc.).
- 'product_worker': Can find specific products matching a design.

YOUR JOB:
1. Examine the current task list and the results of completed tasks.
2. If all objectives are met, output 'FINALIZE'.
3. If more work is needed, pick the next BEST worker.
4. Output your decision as a JSON object:
{{
  "thought": "Briefly explain your reasoning",
  "action": "WORKER_NAME or FINALIZE",
  "new_tasks": ["Optional: add tasks to the list if you discovered new needs"]
}}

STRICT RULES:
- DO NOT answer from your own internal knowledge if a worker can check it.
- If the user asks about a specific term (e.g. 'Kyrolon'), ALWAYS run 'knowledge_worker' first.
- Only one worker at a time.
"""

_ACTION_ALIASES = {
    "knowledge_worker": "RUN_KNOWLEDGE",
    "product_worker": "PRODUCT",
    "calc_worker": "CALC",
    "design_worker": "DESIGN",
}


def _normalize_supervisor_action(action: Optional[str]) -> str:
    if not action:
        return "FINALIZE"
    normalized = str(action).strip()
    mapped = _ACTION_ALIASES.get(normalized.lower())
    return mapped or normalized


def _format_history(messages: List[BaseMessage], limit: int = 15) -> str:
    """Format the last N messages for the prompt."""
    if not messages:
        return "No history."
    
    # Take last N, excluding the very last one if it replicates user_text
    relevant = messages[-limit:-1] if len(messages) > 1 else []
    
    formatted = []
    for msg in relevant:
        role = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", "")
        formatted.append(f"[{role.upper()}]: {content}")
        
    return "\n".join(formatted)

def autonomous_supervisor_node(state: SealAIState) -> Dict[str, Any]:
    """
    The autonomous brain of the system. 
    It reads the state, updates the task list, and decides the next node.
    """
    # Debug logging
    msg_count = len(state.messages) if state.messages else 0
    print(f"DEBUG: Entering autonomous_supervisor_node. Message count: {msg_count}")
    
    model_name = get_model_tier("pro") # Use GPT-5.2 equivalent
    user_text = latest_user_text(state.get("messages") or [])
    history_str = _format_history(state.get("messages") or [])
    
    # Logic to mark tasks as done based on last_node
    last_node = state.get("last_node")
    new_tasks = list(state.task_list or [])
    
    # Simple check if a worker just finished
    if last_node and "worker" in last_node:
        # Mark the most recent planned task for this worker as done
        for t in reversed(new_tasks):
            if t.assigned_to == last_node and t.status == "planned":
                t.status = "done"
                break

    # Format task list for prompt
    tasks_str = "\n".join([f"- [{t.status}] {t.description} (Assigned: {t.assigned_to})" for t in new_tasks])
    
    prompt = PLANNER_SYSTEM_PROMPT.format(
        task_list=tasks_str or "No tasks yet.",
        history=history_str,
        user_text=user_text
    )
    
    # Smalltalk / Greeting Pre-check
    # Smalltalk / Greeting Pre-check
    # REMOVED: Aggressive length check was skipping valid short questions like 'Wer ist Kyrolon?'
    # The Planner LLM is now fast enough to handle this.
    
    # Planning Call
    try:
        response = run_llm(
            model=model_name,
            prompt=prompt,
            system="You are an expert sealing engineer supervisor.",
            temperature=0.0
        )
        
        if "```json" in response:
            clean_res = response.split("```json")[1].split("```")[0]
        else:
            clean_res = response
        decision = json.loads(clean_res)
    except Exception as e:
        logger.error(f"Planner LLM failed: {e}")
        decision = {"action": "FINALIZE", "thought": "Planer parsing failed, emergency exit.", "new_tasks": []}

    print(f"DEBUG: Supervisor decision: {decision}")
    
    # Update State
    monologue = list(state.internal_monologue or [])
    monologue.append(decision.get("thought", "Generic iteration"))
    raw_action = decision.get("action")
    normalized_action = _normalize_supervisor_action(raw_action)
    
    # Add new tasks if any
    for task_desc in decision.get("new_tasks", []):
        new_tasks.append(TaskItem(
            description=task_desc,
            status="planned",
            assigned_to=(raw_action or normalized_action or "unknown").lower()
        ))

    return {
        "next_action": normalized_action,
        "internal_monologue": monologue,
        "task_list": new_tasks,
        "last_node": "autonomous_supervisor_node",
        "parameters": state.parameters,
    }

def autonomous_router(state: SealAIState) -> str:
    """Routes based on supervisor's next_action."""
    action = (state.next_action or "FINALIZE").upper()
    
    if "FINALIZE" in action:
        return "finalize"
    if "KNOWLEDGE" in action:
        return "knowledge"
    if "DESIGN" in action:
        return "design"
    if "CALC" in action:
        return "calc"
    if "PRODUCT" in action:
        return "product"
        
    return "finalize"


def challenger_feedback_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """
    Adversarial review of material/profile proposals.

    Uses the senior policy prompt as a physical-constraints checklist.
    """
    rec = state.recommendation
    material = (state.material_choice or {}).get("material") or (
        rec.get("material") if isinstance(rec, dict) else getattr(rec, "material", None)
    )
    profile = (state.profile_choice or {}).get("profile") or (
        rec.get("profile") if isinstance(rec, dict) else getattr(rec, "profile", None)
    )
    if not material and not profile:
        return {
            "challenger_feedback": None,
            "challenger_issues": [],
            "challenger_status": "skipped",
            "phase": PHASE.VALIDATION,
            "last_node": "challenger_feedback_node",
        }

    params = state.parameters.as_dict() if state.parameters else {}
    policy_text = render_template("senior_policy_de.j2", {})
    prompt = render_template(
        "challenger_feedback.j2",
        {
            "policy_text": policy_text,
            "material": material,
            "profile": profile,
            "parameters": params,
            "application": state.application_category or state.use_case_raw or params.get("application_type"),
        },
    )
    try:
        response = run_llm(
            model=get_model_tier("mini"),
            prompt=prompt,
            system="Du bist ein skeptischer Prüfer für Dichtungsauslegung. Antworte strikt als JSON.",
            temperature=0.2,
            max_tokens=320,
            metadata={
                "run_id": state.run_id,
                "thread_id": state.thread_id,
                "user_id": state.user_id,
                "node": "challenger_feedback_node",
            },
        )
        payload, _ = extract_json_obj(response, default={})
    except Exception as exc:
        logger.error("challenger_feedback_failed", error=str(exc))
        payload = {}
        response = ""

    issues_raw = payload.get("issues") or []
    if isinstance(issues_raw, str):
        issues = [issues_raw]
    elif isinstance(issues_raw, list):
        issues = [str(item) for item in issues_raw if str(item).strip()]
    else:
        issues = []

    status = payload.get("status") or ("needs_revision" if issues else "ok")
    feedback = payload.get("feedback") or response or "Challenger: keine weiteren Einwände."

    wm = state.working_memory or WorkingMemory()
    try:
        wm = wm.model_copy(update={"challenger_feedback": feedback})
    except Exception:
        pass

    return {
        "challenger_feedback": feedback,
        "challenger_issues": issues,
        "challenger_status": status,
        "working_memory": wm,
        "phase": PHASE.VALIDATION,
        "last_node": "challenger_feedback_node",
    }
