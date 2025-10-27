"""
LangGraph-inspired multi-agent supervisor stack.

This module mirrors the LangGraph tutorial at
https://langchain-ai.github.io/langgraph/tutorials/multi_agent/agent_supervisor/#4-create-delegation-tasks
by wiring together a supervisor that delegates explicit tasks to
specialised research and math agents. The implementation uses the local
StateGraph stub but follows the same architectural concepts: the
supervisor formulates task descriptions, hands them off to dedicated
agents, and then synthesises a final response for the user.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Dict, List, Optional, TypedDict

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, add_messages
from langgraph.constants import END
from langgraph.types import Send
from langchain_community.tools.tavily_search import TavilySearchResults

log = logging.getLogger(__name__)


class SupervisorState(TypedDict, total=False):
    """State object carried through the supervisor graph."""

    messages: Annotated[List[Dict[str, str]], add_messages]
    user_request: str
    pending_task: Optional[Dict[str, str]]
    tasks_completed: List[str]
    agent_results: Dict[str, str]
    next_node: str
    final_response: str


def _build_llm(model_env_var: str, default_model: str, temperature: float = 0.0) -> ChatOpenAI:
    model_name = os.getenv(model_env_var, default_model)
    return ChatOpenAI(model=model_name, temperature=temperature)


SUPERVISOR_LLM = _build_llm("OPENAI_SUPERVISOR_MODEL", "gpt-4o-mini", temperature=0.1)
MATH_LLM = _build_llm("OPENAI_MATH_MODEL", "gpt-4o-mini", temperature=0.0)

try:
    _tavily_max_results = int(os.getenv("TAVILY_MAX_RESULTS", "3"))
except ValueError:
    _tavily_max_results = 3



def _append_message(state: SupervisorState, *, role: str, name: str, content: str) -> List[Dict[str, str]]:
    messages = list(state.get("messages", []))
    messages.append({"role": role, "name": name, "content": content})
    return messages


def _create_research_task_description(state: SupervisorState) -> str:
    user_request = state.get("user_request", "")
    prompt = (
        "You are a supervisor coordinating specialised agents.\n"
        "Create a clear, concise task description for the research agent. The agent can ONLY perform web research\n"
        "via Tavily and expects unambiguous instructions. Include the concrete topic and any context the agent needs.\n\n"
        f"User request: {user_request}\n"
    )
    try:
        response = SUPERVISOR_LLM.invoke(prompt)
        return response.content.strip()
    except Exception as exc:  # pragma: no cover
        log.exception("Failed to create research task description")
        return f"Investigate the following question using reliable sources: {user_request} (error: {exc})"


def _create_math_task_description(state: SupervisorState) -> str:
    user_request = state.get("user_request", "")
    research_summary = state.get("agent_results", {}).get("research_agent", "")
    prompt = (
        "You are a supervisor coordinating specialised agents.\n"
        "Draft instructions for the math agent. The agent can ONLY perform numerical reasoning and basic arithmetic.\n"
        "Provide the values it should work with based on the research summary. The agent must output only the result.\n\n"
        f"User request: {user_request}\n"
        f"Research summary:\n{research_summary}\n"
    )
    try:
        response = SUPERVISOR_LLM.invoke(prompt)
        return response.content.strip()
    except Exception as exc:  # pragma: no cover
        log.exception("Failed to create math task description")
        return (
            "Compute the percentage share requested by the user using the GDP figures mentioned in the research summary."
            f" ({exc})"
        )


def _compose_final_response(state: SupervisorState) -> str:
    user_request = state.get("user_request", "")
    research_summary = state.get("agent_results", {}).get("research_agent", "")
    math_result = state.get("agent_results", {}).get("math_agent", "")
    prompt = (
        "You are the supervising agent. Combine the research findings and math calculation into a final answer for the user.\n"
        "Be explicit about the numbers used, cite sources if present in the research summary, and keep the tone professional.\n\n"
        f"User request: {user_request}\n"
        f"Research summary:\n{research_summary}\n\n"
        f"Math result:\n{math_result}\n"
    )
    try:
        response = SUPERVISOR_LLM.invoke(prompt)
        return response.content.strip()
    except Exception:  # pragma: no cover
        log.exception("Failed to compose final supervisor response")
        return math_result or research_summary or "Unable to produce a final response."


def _format_tavily_results(results: List[Dict[str, str]]) -> str:
    snippets = []
    for item in results[: _tavily_max_results]:
        title = item.get("title") or item.get("url") or "Source"
        content = item.get("content") or ""
        url = item.get("url", "")
        snippets.append(f"- {title}: {content[:400]} ({url})")
    return "\n".join(snippets) or "No search results were returned."


def _run_tavily_search(query: str) -> str:
    if not os.getenv("TAVILY_API_KEY"):
        return "Tavily API key not configured. Cannot perform web research."
    tavily_tool = TavilySearchResults(max_results=_tavily_max_results)
    if not query.strip():
        return "No research task description provided."
    try:
        result = tavily_tool.invoke({"query": query})
    except Exception as exc:
        log.warning("Tavily invocation failed: %s", exc)
        return f"Could not complete web research due to an error: {exc}"

    if isinstance(result, dict) and "results" in result:
        results_list = result.get("results") or []
    elif isinstance(result, list):
        results_list = result
    else:  # pragma: no cover - defensive
        results_list = []

    return _format_tavily_results(results_list)


def _run_math_solver(task_description: str, research_summary: str) -> str:
    prompt = (
        "You are a dedicated math agent. Use the instructions below to perform the required calculation.\n"
        "You may rely on the referenced research summary for numeric values but MUST show the computed result.\n"
        "Respond with the numeric answer and short explanation; do not include unrelated text.\n\n"
        f"Task: {task_description}\n\n"
        f"Research summary:\n{research_summary}\n"
    )
    try:
        response = MATH_LLM.invoke(prompt)
        return response.content.strip()
    except Exception as exc:  # pragma: no cover
        log.exception("Math agent failed to complete task")
        return f"Math agent encountered an error: {exc}"


def supervisor_node(state: SupervisorState) -> SupervisorState:
    tasks_completed = list(state.get("tasks_completed", []))
    pending_task = state.get("pending_task")

    if pending_task:
        return {"next_node": pending_task.get("agent", "__finish__")}

    if "research_agent" not in tasks_completed:
        task_description = _create_research_task_description(state)
        messages = _append_message(
            state,
            role="assistant",
            name="supervisor",
            content=f"Delegating to research agent with task: {task_description}",
        )
        return {
            "messages": messages,
            "pending_task": {"agent": "research_agent", "description": task_description},
            "next_node": "research_agent",
        }

    if "math_agent" not in tasks_completed:
        task_description = _create_math_task_description(state)
        messages = _append_message(
            state,
            role="assistant",
            name="supervisor",
            content=f"Delegating to math agent with task: {task_description}",
        )
        return {
            "messages": messages,
            "pending_task": {"agent": "math_agent", "description": task_description},
            "next_node": "math_agent",
        }

    final_response = _compose_final_response(state)
    messages = _append_message(state, role="assistant", name="supervisor", content=final_response)
    return {"messages": messages, "final_response": final_response, "next_node": "__finish__"}


def research_agent_node(state: SupervisorState) -> SupervisorState:
    task = state.get("pending_task") or {}
    task_description = task.get("description", "")
    research_summary = _run_tavily_search(task_description)
    messages = _append_message(state, role="assistant", name="research_agent", content=research_summary)

    agent_results = dict(state.get("agent_results", {}))
    agent_results["research_agent"] = research_summary

    tasks_completed = list(state.get("tasks_completed", []))
    if "research_agent" not in tasks_completed:
        tasks_completed.append("research_agent")

    return {
        "messages": messages,
        "agent_results": agent_results,
        "tasks_completed": tasks_completed,
        "pending_task": None,
        "next_node": "supervisor",
    }


@tool
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


@tool
def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b


@tool
def divide(a: float, b: float) -> float:
    """Divide two numbers."""
    if b == 0:
        raise ValueError("Division by zero is not allowed.")
    return a / b


def math_agent_node(state: SupervisorState) -> SupervisorState:
    task = state.get("pending_task") or {}
    task_description = task.get("description", "")
    research_summary = state.get("agent_results", {}).get("research_agent", "")

    math_result = _run_math_solver(task_description, research_summary)
    messages = _append_message(state, role="assistant", name="math_agent", content=math_result)

    agent_results = dict(state.get("agent_results", {}))
    agent_results["math_agent"] = math_result

    tasks_completed = list(state.get("tasks_completed", []))
    if "math_agent" not in tasks_completed:
        tasks_completed.append("math_agent")

    return {
        "messages": messages,
        "agent_results": agent_results,
        "tasks_completed": tasks_completed,
        "pending_task": None,
        "next_node": "supervisor",
    }


def supervisor_condition(state: SupervisorState) -> str:
    next_node = state.get("next_node")
    if not next_node:
        return "__finish__"
    return next_node


def _build_supervisor_app():
    graph = StateGraph(SupervisorState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("research_agent", research_agent_node)
    graph.add_node("math_agent", math_agent_node)

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        supervisor_condition,
        {
            "research_agent": "research_agent",
            "math_agent": "math_agent",
            "__finish__": END,
        },
    )
    graph.add_edge("research_agent", "supervisor")
    graph.add_edge("math_agent", "supervisor")

    return graph.compile()


SUPERVISOR_APP = _build_supervisor_app()


def run_supervisor_stack(initial_message: str) -> List[str]:
    """Entry point used by the FastAPI endpoint."""
    state: SupervisorState = {
        "messages": [{"role": "user", "name": "user", "content": initial_message}],
        "user_request": initial_message,
        "tasks_completed": [],
        "agent_results": {},
        "pending_task": None,
        "next_node": "supervisor",
    }
    result = SUPERVISOR_APP.invoke(state)
    final_response = result.get("final_response") or ""
    return [final_response] if final_response else [msg["content"] for msg in result.get("messages", []) if msg.get("name") == "supervisor"]
