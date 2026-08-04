"""
tests/test_graph.py
-------------------
Unit tests for LangGraph state graph nodes and workflow execution using mocked LLM engines.
"""

from unittest.mock import MagicMock, patch
from src.agent.graph import build_graph
from src.agent.schemas import AgentState


@patch("src.agent.nodes.get_llm_engine")
def test_unit_generator_node(mock_get_llm, sample_agent_state: AgentState):
    """Unit test targeting generate_tests_node directly using a mocked ChatModel."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = (
        '{"test_code": "from solution import add\\n\\ndef test_add():\\n    assert add(1, 2) == 3",'
        ' "test_descriptions": ["Validates addition"]}'
    )
    mock_get_llm.return_value = mock_llm

    from src.agent.nodes import generate_tests_node

    result = generate_tests_node(sample_agent_state)
    assert result["status"] == "TESTS_GENERATED"
    assert "test_code" in result


@patch("src.agent.nodes.get_llm_engine")
def test_self_healing_graph_execution(mock_get_llm):
    """End-to-end integration test for the compiled StateGraph with mocked LLM outputs."""
    mock_llm = MagicMock()
    # Return structured JSON for refactoring and test generation
    mock_llm.invoke.side_effect = [
        # 1st call: refactor_node
        MagicMock(
            content='{"refactored_code": "def process_user_data(data: list) -> list:\\n    return [x[\'name\'].upper() for x in data if x.get(\'active\')]", "explanation": "Modernized", "imports_used": []}'
        ),
        # 2nd call: generate_tests_node
        MagicMock(
            content='{"test_code": "from solution import process_user_data\\n\\ndef test_process():\\n    assert process_user_data([{\\'name\\': \\'alice\\', \\'active\\': True}]) == [\\'ALICE\\']", "test_descriptions": ["Test active user"]}'
        ),
    ]
    mock_get_llm.return_value = mock_llm

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
    assert final_state["status"] == "PASSED"