"""
src/sandbox/base.py
-------------------
Abstract Sandbox Interface establishing the Strategy Pattern for code execution engines.
Allows seamless swapping between Docker SDK, E2B microVMs, or serverless execution containers.
"""

from abc import ABC, abstractmethod
from src.agent.schemas import ExecutionResult


class AbstractSandbox(ABC):
    """Abstract Base Class for isolated execution environments."""

    @abstractmethod
    def run_tests(
        self, refactored_code: str, test_code: str, timeout: int = 30
    ) -> ExecutionResult:
        """
        Executes code and tests in an isolated sandbox environment.

        Args:
            refactored_code: The target Python source code string.
            test_code: The pytest suite string.
            timeout: Maximum execution timeout in seconds.

        Returns:
            ExecutionResult schema containing exit code, stdout, stderr, and pass flag.
        """
        pass