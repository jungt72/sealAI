from __future__ import annotations

"""
LangGraph-CLI Entry für Dev-/Debug.

Beispiele:
  langgraph dev backend.app.cli.langgraph_entry:get_consult_graph
  langgraph dev backend.app.cli.langgraph_entry:get_supervisor_graph
"""

def get_consult_graph():
    from app.services.langgraph.graph.consult.build import build_consult_graph
    return build_consult_graph()

def get_supervisor_graph():
    from app.services.langgraph.graph.supervisor_graph import build_supervisor_graph
    return build_supervisor_graph()
