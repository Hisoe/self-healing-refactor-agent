"""
tests/test_graph.py
-------------------
End-to-end integration test and unit tests validating the self-healing agent workflow.
"""

from dotenv import load_dotenv
load_dotenv()  # Loads env vars from .env

import pytest
from typing import Dict, Any
from src.agent.schemas import AgentState
from src.agent.graph import build_graph
from src.agent.nodes import generate_tests_node, run_tests_node


@pytest.fixture
def sample_agent_state() -> AgentState:
    """Provides a initialized dummy state fixture for individual node unit testing."""
    return {
        "original_code": "def add(a, b):\n    return a + b",
        "refactored_code": "def add(a: int, b: int) -> int:\n    \"\"\"Adds two integers.\"\"\"\n    return a + b",
        "refactor_explanation": "Added type hints and docstring.",
        "test_code": "def test_add():\n    assert add(2, 3) == 5",
        "execution_result": None,
        "iteration_count": 0,
        "max_iterations": 3,
        "failure_history": [],
        "status": "INITIALIZED"
    }


def test_self_healing_graph_execution():
    """End-to-end integration test for the compiled StateGraph."""
    app = build_graph()

    buggy_code = """
def process_user_data(data):
    # Buggy and untyped processing logic
    res = []
    for x in data:
        if x['active'] == True:
            res.append(x['name'].upper())
    return res
"""

    initial_state = {
        "original_code": buggy_code,
        "refactored_code": None,
        "refactor_explanation": None,
        "test_code": None,
        "execution_result": None,
        "iteration_count": 0,
        "max_iterations": 3,
        "failure_history": [],
        "status": "INITIALIZED"
    }

    final_state = app.invoke(initial_state)

    assert final_state["execution_result"] is not None
    assert final_state["refactored_code"] is not None
    assert final_state["test_code"] is not None
    assert final_state["iteration_count"] > 0
    assert final_state["execution_result"].passed is True


def test_unit_generator_node(sample_agent_state: AgentState):
    """Unit test targeting generate_tests_node directly."""
    result = generate_tests_node(sample_agent_state)
    assert "test_code" in result
    assert result["status"] == "TESTS_GENERATED"


def test_unit_runner_node(sample_agent_state: AgentState):
    """Unit test targeting run_tests_node directly."""
    result = run_tests_node(sample_agent_state)
    assert "execution_result" in result
    assert result["execution_result"].passed is True