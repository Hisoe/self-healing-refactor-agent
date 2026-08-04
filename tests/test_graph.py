"""
tests/test_graph.py
-------------------
Integration test suite running live LLM executions through compiled LangGraph state graph.
"""

from src.agent.graph import build_graph
from src.agent.nodes import generate_tests_node
from src.agent.schemas import AgentState


def test_unit_generator_node(sample_agent_state: AgentState):
    """Integration test targeting generate_tests_node directly using a live LLM execution."""
    result = generate_tests_node(sample_agent_state)

    assert result["status"] == "TESTS_GENERATED"
    assert result["test_code"] is not None
    assert "def test_" in result["test_code"]


def test_self_healing_graph_execution():
    """End-to-end integration test executing compiled StateGraph against a live LLM."""
    app = build_graph()

    buggy_code = """
def process_user_data(data):
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
        "status": "INITIALIZED",
    }

    final_state = app.invoke(initial_state)

    # Asserts complete end-to-end pipeline execution succeeded
    assert final_state["status"] == "PASSED"
    assert final_state["refactored_code"] is not None
    assert final_state["test_code"] is not None
    assert final_state["execution_result"].passed is True