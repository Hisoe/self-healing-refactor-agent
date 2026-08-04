"""
tests/test_schemas.py
---------------------
Unit tests validating Pydantic models and ExecutionResult behavior.
"""

from src.agent.schemas import ExecutionResult, RefactoredCodeOutput

def test_execution_result_failed_state():
    result = ExecutionResult(
        passed=False,
        exit_code=1,
        stdout="FF",
        stderr="AssertionError: Expected 10, got 5",
        stack_trace="Traceback (most recent call last):\n  File 'test.py', line 5"
    )
    assert not result.passed
    assert result.exit_code == 1
    assert "AssertionError" in result.stderr

def test_refactored_code_schema():
    output = RefactoredCodeOutput(
        refactored_code="def add(a: int, b: int) -> int:\n    return a + b",
        explanation="Added type annotations.",
        imports_used=[]
    )
    assert "def add" in output.refactored_code
    assert output.imports_used == []