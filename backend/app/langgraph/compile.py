# backend/app/langgraph/compile.py
# MIGRATION: Phase-2 - Hauptgraph kompilieren, Checkpointer setzen
from __future__ import annotations
import json
from typing import Any, AsyncIterator, Dict, Optional
from uuid import uuid4
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from .checkpointer import make_checkpointer
from .constants import CHECKPOINTER_NAMESPACE_MAIN
from .nodes.confirm_gate import confirm_gate
from .nodes.discovery_intake import discovery_intake
from .nodes.entry_frontend import entry_frontend
from .nodes.exit_response import exit_response
from .nodes.intent_projector import intent_projector
from .nodes.resolver import resolver
from .nodes.supervisor import supervisor
from .state import MetaInfo, Routing, SealAIState
_CHECKPOINTER = make_checkpointer()
_ASYNC_CHECKPOINTER = make_checkpointer(require_async=True)
