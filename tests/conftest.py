"""
tests/conftest.py
-----------------
Pytest configuration and shared fixtures for unit and integration tests.
"""

from dotenv import load_dotenv
load_dotenv()  # Load environment variables before running test fixtures

import pytest
from src.sandbox.docker_sandbox import DockerSandboxEngine
from src.agent.schemas import AgentState


@pytest.fixture
def sandbox():
    """Provides a fresh instance of the Docker execution engine."""
    return DockerSandboxEngine()


@pytest.fixture
def sample_agent_state() -> AgentState:
    """Provides a initialized AgentState schema payload for node testing."""
    return {
        "original_code": "def add(a, b):\n    return a + b",
        "refactored_code": "def add(a: int, b: int) -> int:\n    \"\"\"Adds two integers.\"\"\"\n    return a + b",
        "refactor_explanation": "Added type hints and docstring.",
        "test_code": "from solution import add\n\ndef test_add():\n    assert add(2, 3) == 5",
        "execution_result": None,
        "iteration_count": 0,
        "max_iterations": 3,
        "failure_history": [],
        "status": "INITIALIZED",
    }