"""
src/sandbox/docker_sandbox.py
------------------------------
Executes untrusted LLM-generated code and test suites inside an ephemeral
Docker container with resource constraints, zero network access, and safe log extraction.
Enforces open POSIX permissions on mounts to prevent Linux runner PermissionError (Errno 13).
"""

import logging
import os
import tempfile
import docker
from docker.errors import DockerException
from src.sandbox.base import AbstractSandbox
from src.agent.schemas import ExecutionResult

logger = logging.getLogger(__name__)


class DockerSandboxEngine(AbstractSandbox):
    """Concrete Docker SDK sandbox implementation with cgroup resource limits and isolation."""

    def __init__(
        self,
        image_tag: str = "python-pytest-sandbox:latest",
        timeout_seconds: int = 15,
    ):
        self.image_tag = image_tag
        self.timeout_seconds = timeout_seconds
        
        try:
            self.client = docker.from_env()
            # Active ping check to verify live daemon connection at startup
            self.client.ping()
        except (DockerException, Exception) as e:
            raise RuntimeError(
                f"\n❌ Docker daemon is unreachable. Ensure Docker is running.\nUnderlying error: {e}"
            ) from e

    def run_tests(
        self, refactored_code: str, test_code: str, timeout: int = 30
    ) -> ExecutionResult:
        """
        Mounts solution and test code into an ephemeral directory and executes pytest.
        Fulfills AbstractSandbox.run_tests interface contract explicitly.
        """
        effective_timeout = timeout or self.timeout_seconds

        with tempfile.TemporaryDirectory() as host_temp_dir:
            # Grant full read/write/execute permissions to mounted host directory
            os.chmod(host_temp_dir, 0o777)

            solution_path = os.path.join(host_temp_dir, "solution.py")
            test_path = os.path.join(host_temp_dir, "test_solution.py")

            # Write solution and test modules
            with open(solution_path, "w", encoding="utf-8") as f:
                f.write(refactored_code)

            with open(test_path, "w", encoding="utf-8") as f:
                f.write("from solution import *\n\n" + test_code)

            # Ensure mounted files have universal read/write permissions
            os.chmod(solution_path, 0o666)
            os.chmod(test_path, 0o666)

            container = None
            try:
                container = self.client.containers.run(
                    image=self.image_tag,
                    # Targeted pytest call suppressing inherited outer config file discovery
                    command="python -m pytest test_solution.py -o addopts=''",
                    volumes={host_temp_dir: {"bind": "/app", "mode": "rw"}},
                    working_dir="/app",
                    network_mode="none",  # Strict network isolation
                    mem_limit="256m",
                    nano_cpus=1000000000,  # 1 CPU
                    detach=True,
                )

                result = container.wait(timeout=effective_timeout)
                exit_code = result.get("StatusCode", -1)

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
                logs_str = ""
                if container:
                    try:
                        container.stop(timeout=1)
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
                if container:
                    try:
                        container.remove(force=True)
                    except Exception:
                        pass