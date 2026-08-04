"""
src/agent/graph.py
-------------------
Assembles and compiles the LangGraph workflow for the self-healing agent.
"""

from typing import Any
from langgraph.graph import StateGraph, START, END
from src.agent.schemas import AgentState
from src.agent.nodes import (
    refactor_node,
    generate_tests_node,
    run_tests_node,
    should_continue
)

def build_graph() -> Any:
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("refactor_node", refactor_node)
    workflow.add_node("test_generator_node", generate_tests_node)
    workflow.add_node("test_runner_node", run_tests_node)

    # Add Edges
    workflow.add_edge(START, "refactor_node")
    workflow.add_edge("refactor_node", "test_generator_node")
    workflow.add_edge("test_generator_node", "test_runner_node")

    workflow.add_conditional_edges(
        "test_runner_node",
        should_continue,
        {
            "refactor_node": "refactor_node",
            "__end__": END
        }
    )

    return workflow.compile()