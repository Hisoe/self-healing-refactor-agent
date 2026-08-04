"""
src/sandbox/docker_sandbox.py
------------------------------
Executes untrusted LLM-generated code and test suites inside an ephemeral
Docker container with resource constraints, zero network access, and safe log extraction.
"""

from src.sandbox.base import AbstractSandbox
import os
import tempfile
import docker
from src.agent.schemas import ExecutionResult


class DockerSandboxEngine(AbstractSandbox):
    """Concrete Docker SDK sandbox implementation with cgroup resource limits and isolation."""

    def __init__(
        self,
        image_tag: str = "python-pytest-sandbox:latest",
        timeout_seconds: int = 15,
    ):
        self.image_tag = image_tag
        self.timeout_seconds = timeout_seconds
        self.client = docker.from_env()

    def run_tests(self, refactored_code: str, test_code: str) -> ExecutionResult:
        """
        Mounts solution and test code into an ephemeral directory and executes pytest.
        """
        with tempfile.TemporaryDirectory() as host_temp_dir:
            solution_path = os.path.join(host_temp_dir, "solution.py")
            test_path = os.path.join(host_temp_dir, "test_solution.py")

            # Write generated code and unit tests to temporary host directory
            with open(solution_path, "w", encoding="utf-8") as f:
                f.write(refactored_code)

            with open(test_path, "w", encoding="utf-8") as f:
                f.write("from solution import *\n\n" + test_code)

            container = None
            try:
                # Spawn container in detached mode to control log capture and cleanup
                container = self.client.containers.run(
                    image=self.image_tag,
                    command="pytest test_solution.py -v",
                    volumes={host_temp_dir: {"bind": "/app", "mode": "rw"}},
                    working_dir="/app",
                    network_mode="none",    # Disable network completely
                    mem_limit="256m",       # Constrain RAM footprint
                    nano_cpus=1000000000,   # Cap CPU usage to 1 core
                    detach=True,            # Run detached for manual log capture
                )

                # Wait for execution completion or timeout
                result = container.wait(timeout=self.timeout_seconds)
                exit_code = result.get("StatusCode", -1)

                # Capture full terminal output BEFORE removing container
                logs_bytes = container.logs(stdout=True, stderr=True)
                logs_str = logs_bytes.decode("utf-8", errors="replace")

                passed = exit_code == 0
                return ExecutionResult(
                    passed=passed,
                    exit_code=exit_code,
                    stdout=logs_str if passed else "",
                    stderr="" if passed else logs_str,
                    stack_trace=None if passed else logs_str,
                )

            except Exception as e:
                # Handles process timeout or Docker API errors
                logs_str = ""
                if container:
                    try:
                        logs_bytes = container.logs(stdout=True, stderr=True)
                        logs_str = logs_bytes.decode("utf-8", errors="replace")
                    except Exception:
                        pass

                error_msg = logs_str or str(e)
                return ExecutionResult(
                    passed=False,
                    exit_code=-1,
                    stdout="",
                    stderr=error_msg,
                    stack_trace=f"Sandbox Execution Failure: {error_msg}",
                )

            finally:
                # Force cleanup container instance
                if container:
                    try:
                        container.remove(force=True)
                    except Exception:
                        pass