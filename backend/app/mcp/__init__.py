"""MCP tool registry modules."""

from .calc_engine import (
    CALC_GASKET_TOOL_NAME,
    CALC_GASKET_TOOL_SPEC,
    MCP_CALC_EXECUTE_SCOPES,
    mcp_calc_gasket,
)
from .calc_schemas import CalcInput, CalcOutput
from .knowledge_tool import (
    APPROVE_DISCOUNT_TOOL_NAME,
    GET_AVAILABLE_FILTERS_TOOL_NAME,
    MCP_ERP_READ_SCOPES,
    MCP_KNOWLEDGE_READ_SCOPES,
    MCP_SALES_ADMIN_SCOPES,
    MCP_TRANSPORT_PREFERENCE,
    PRICING_TOOL_NAME,
    STOCK_CHECK_TOOL_NAME,
    build_mcp_tool_result,
    discover_tools_for_scopes,
    get_permitted_tool_specs,
    get_permitted_tools,
    get_available_filters,
    has_knowledge_scope,
    search_technical_docs,
)

__all__ = [
    "CALC_GASKET_TOOL_NAME",
    "CALC_GASKET_TOOL_SPEC",
    "CalcInput",
    "CalcOutput",
    "MCP_CALC_EXECUTE_SCOPES",
    "mcp_calc_gasket",
    "APPROVE_DISCOUNT_TOOL_NAME",
    "GET_AVAILABLE_FILTERS_TOOL_NAME",
    "MCP_ERP_READ_SCOPES",
    "MCP_KNOWLEDGE_READ_SCOPES",
    "MCP_SALES_ADMIN_SCOPES",
    "MCP_TRANSPORT_PREFERENCE",
    "PRICING_TOOL_NAME",
    "STOCK_CHECK_TOOL_NAME",
    "build_mcp_tool_result",
    "discover_tools_for_scopes",
    "get_permitted_tool_specs",
    "get_permitted_tools",
    "get_available_filters",
    "has_knowledge_scope",
    "search_technical_docs",
]
