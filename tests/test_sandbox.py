"""
tests/test_sandbox.py
----------------------
Integration tests validating DockerSandboxEngine runtime security and execution outcomes.
"""

import pytest
from src.sandbox.docker_sandbox import DockerSandboxEngine


@pytest.fixture
def sandbox():
    return DockerSandboxEngine()


def test_sandbox_passing_execution(sandbox):
    refactored_code = "def multiply(a: int, b: int) -> int:\n    return a * b"
    test_code = "def test_multiply():\n    assert multiply(3, 4) == 12"

    result = sandbox.run_tests(refactored_code, test_code)
    assert result.passed
    assert result.exit_code == 0
    assert "1 passed" in result.stdout


def test_sandbox_failing_assertion(sandbox):
    refactored_code = "def multiply(a: int, b: int) -> int:\n    return a + b"  # Intentional bug
    test_code = "def test_multiply():\n    assert multiply(3, 4) == 12"

    result = sandbox.run_tests(refactored_code, test_code)
    assert not result.passed
    assert result.exit_code != 0
    assert "AssertionError" in result.stack_trace


def test_sandbox_network_isolation(sandbox):
    """Verifies that LLM code cannot make outbound network requests."""
    refactored_code = (
        "import urllib.request\n"
        "def fetch_data():\n"
        "    urllib.request.urlopen('https://google.com', timeout=2)\n"
    )
    test_code = "def test_fetch():\n    fetch_data()"

    result = sandbox.run_tests(refactored_code, test_code)
    assert not result.passed
    # Network calls fail inside network_mode='none'
    assert "URLError" in result.stack_trace or "socket" in result.stack_trace