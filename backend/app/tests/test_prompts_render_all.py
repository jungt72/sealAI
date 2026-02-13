
import pytest
import os
import glob
from app.prompts.registry import PromptRegistry
from jinja2 import UndefinedError

# Define known contexts for templates
DEFAULT_CONTEXT = {
    "organization_name": "SealAI",
    "is_first_visit": True,
    "session_id": "test_session",
    "language": "de",
    "user_message": "Test Message",
    "missing_info_list": "['pressure', 'temp']",
    "trace_id": "test_trace",
    "agent_name": "SealAgent",
    "user_name": "Customer",
    "current_date": "2026-01-01",
    
    # Common vars
    "latest_user_text": "I need a seal.",
    "user_text": "I need a seal.",
    "intent_goal": "design_recommendation",
    "policy_text": "Policy content...",
    "summary": "Conversation summary...",
    "pattern": "Leakage pattern...",
    "ask_missing_request": "Please provide pressure.",
    "is_micro_smalltalk": False,
    "parameters": {"pressure": 10},
    "draft": "Draft content...",
    "troubleshooting": {"symptoms": ["leak"]},
    "material": {"name": "NBR"},
    "coverage": 0.8,
    "symptoms": ["leak"],
    "response_text": "Response...",
    "confidence": 0.95,
    "coverage_score": 0.5,
    
    # Vars from Fix 3/4/5/6 failures
    "discovery_summary": "Summary...",
    "recommendation": {
        "summary": "Rec Summary", 
        "profile": "Profile A", 
        "material": "Mat A", 
        "seal_family": "Family A",
        "rationale": "Reason...",
        "risk_hints": [],
        "notes": [] 
    },
    "profile": {"name": "Profile A"},
    "missing_text": "Missing info...",
    "application": "Application X",
    "user_text_norm": "Normalized text",
    "coverage_gaps_text": "Gaps...",
    "calc_results": {
        "safety_factor": 1.5,
        "notes": [] 
    },

    # NEW VARS for Middle Game
    "missing_params_grouped": "Pressure, Temp",
    "known_params_summary": "Medium=Water",
    "questions_asked_count": 1,
    "critical_issues": [{"type": "hydrogen", "description": "Hydrogen requires specific material"}],
    "urgency_level": "critical",
    "application_type": "Hydrogen Storage",
}

TEMPLATE_SPECIFIC_CONTEXT = {
    "greeting/reply_v1": {"is_first_visit": False}, 
    "response_router": {"ask_missing_request": None}, 
}

def get_all_templates():
    base_dir = os.path.expanduser("~/sealai/backend/app/prompts")
    files = glob.glob(os.path.join(base_dir, "**", "*.j2"), recursive=True)
    rel_names = [os.path.relpath(f, base_dir) for f in files]
    return [n[:-3] if n.endswith(".j2") else n for n in rel_names]

def test_render_all_templates():
    base_dir = os.path.expanduser("~/sealai/backend/app/prompts")
    registry = PromptRegistry(base_dir=base_dir)
    templates = get_all_templates()
    
    print(f"\nFound {len(templates)} templates to test.")
    
    failures = []
    
    for tmpl in templates:
        # Skip test infra
        if "test_infra" in tmpl:
            continue
            
        ctx = DEFAULT_CONTEXT.copy()
        if tmpl in TEMPLATE_SPECIFIC_CONTEXT:
            ctx.update(TEMPLATE_SPECIFIC_CONTEXT[tmpl])
            
        try:
            content, fp, ver = registry.render(tmpl, ctx)
            assert content, f"Template {tmpl} rendered empty content"
            assert fp, f"Template {tmpl} has no fingerprint"
        except UndefinedError as e:
            failures.append(f"{tmpl}: Missing var {e}")
        except Exception as e:
            failures.append(f"{tmpl}: Error {e}")
            
    if failures:
        pytest.fail("\n".join(failures))
