"""
tests/test_sandbox.py
---------------------
Integration tests verifying Docker Sandbox isolation, resource limits, and execution.
"""

import pytest
from src.sandbox.docker_sandbox import DockerSandboxEngine


@pytest.fixture
def sandbox():
    return DockerSandboxEngine()


def test_sandbox_passing_execution(sandbox):
    refactored_code = "def multiply(a: int, b: int) -> int:\n    return a * b"
    # Clean test code string without duplicate import statement
    test_code = "def test_multiply():\n    assert multiply(3, 4) == 12"

    result = sandbox.run_tests(refactored_code, test_code)
    assert result.passed is True


def test_sandbox_failing_assertion(sandbox):
    refactored_code = "def multiply(a: int, b: int) -> int:\n    return a + b"
    test_code = "def test_multiply():\n    assert multiply(3, 4) == 12"

    result = sandbox.run_tests(refactored_code, test_code)
    assert result.passed is False
    assert result.exit_code != 0


def test_sandbox_network_isolation(sandbox):
    """Verifies that LLM code cannot make outbound network requests."""
    refactored_code = (
        "import urllib.request\n"
        "def fetch_data():\n"
        "    urllib.request.urlopen('https://google.com', timeout=2)\n"
    )
    test_code = "def test_fetch():\n    fetch_data()"

    result = sandbox.run_tests(refactored_code, test_code)
    assert result.passed is False