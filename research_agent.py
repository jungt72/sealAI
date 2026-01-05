"""
LangGraph Workflow for LLM-based Research Agent
This script creates a stateful LangGraph workflow that performs web research,
extracts relevant information, and generates structured summaries.
"""

import os
import asyncio
from typing import TypedDict, List, Optional, Dict, Any

from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langchain_community.tools.tavily_search import TavilySearchResults
import structlog

# Initialize logger
logger = structlog.get_logger()

# Define the state using TypedDict for type safety
class ResearchState(TypedDict):
    query: str  # The user's research query
    search_results: List[Dict[str, Any]]  # List of search result dictionaries
    summary: Optional[str]  # Final generated summary
    needs_more_research: bool  # Flag to decide if more research is needed
    attempts: int  # Number of research attempts (for error handling and limits)

# Initialize tools and LLM with environment variables (placeholders)
tavily_tool = TavilySearchResults(
    api_key=os.getenv("TAVILY_API_KEY"),  # Set your Tavily API key
    max_results=5  # Limit results for efficiency
)
llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),  # Set your OpenAI API key
    model="gpt-4o-mini",  # Use a cost-effective model
    temperature=0.1  # Low temperature for consistent summaries
)

# Async node for performing web research using Tavily
async def research_node(state: ResearchState) -> ResearchState:
    """Node to perform web search and collect results."""
    try:
        logger.info("Starting research", query=state["query"], attempts=state["attempts"])
        # Invoke the search tool asynchronously
        results = await tavily_tool.ainvoke({"query": state["query"]})
        # Extend the search results list
        state["search_results"].extend(results)
        state["attempts"] += 1
        logger.info("Research completed", results_count=len(results))
    except Exception as e:
        # Log errors and increment attempts to prevent infinite loops
        logger.error("Research failed", error=str(e))
        state["attempts"] += 1
    return state

# Async node for decision logic: whether more research is needed
async def decide_node(state: ResearchState) -> ResearchState:
    """Node to decide if additional research is required."""
    # Simple logic: if fewer than 3 results and attempts < 3, do more research
    if len(state["search_results"]) < 3 and state["attempts"] < 3:
        state["needs_more_research"] = True
    else:
        state["needs_more_research"] = False
    logger.info("Decision made", needs_more=state["needs_more_research"])
    return state

# Async node for generating the final summary using LLM
async def generate_summary_node(state: ResearchState) -> ResearchState:
    """Node to generate a structured summary from search results."""
    try:
        # Create a prompt with the query and results
        prompt = f"Summarize the following search results for the query: {state['query']}\n\nResults: {state['search_results']}\n\nProvide a concise, structured summary."
        # Invoke LLM asynchronously
        response = await llm.ainvoke(prompt)
        state["summary"] = response.content
        logger.info("Summary generated")
    except Exception as e:
        # Fallback on error
        logger.error("Summary generation failed", error=str(e))
        state["summary"] = "Error generating summary. Please check logs."
    return state

# Build the graph
graph = StateGraph(ResearchState)

# Add nodes
graph.add_node("research", research_node)
graph.add_node("decide", decide_node)
graph.add_node("generate_summary", generate_summary_node)

# Add conditional edges: from decide to research or generate_summary
def routing_logic(state: ResearchState) -> str:
    return "research" if state["needs_more_research"] else "generate_summary"

graph.add_conditional_edges("decide", routing_logic)

# Set entry point and add static edges
graph.set_entry_point("research")
graph.add_edge("research", "decide")
graph.add_edge("generate_summary", "__end__")  # End the graph after summary

# Initialize checkpointer for state persistence
checkpointer = MemorySaver()

# Compile the graph with persistence
app = graph.compile(checkpointer=checkpointer)

# Example execution (uncomment to run)
# async def main():
#     initial_state = {
#         "query": "Zusammenfassen der neuesten KI-Trends",
#         "search_results": [],
#         "summary": None,
#         "needs_more_research": False,
#         "attempts": 0
#     }
#     result = await app.ainvoke(initial_state)
#     print("Final Summary:", result["summary"])

# if __name__ == "__main__":
#     asyncio.run(main())