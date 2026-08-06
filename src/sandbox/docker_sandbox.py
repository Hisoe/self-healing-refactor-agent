import logging
import os
import shutil
import tempfile
import docker
from docker.errors import DockerException
from src.sandbox.base import AbstractSandbox
from src.agent.schemas import ExecutionResult

logger = logging.getLogger(__name__)


def _force_rmtree(path: str) -> None:
    """Safely cleans up temporary directories even if created by container root user."""
    if not os.path.exists(path):
        return

    def _remove_readonly(func, path_to_remove, exc_info):
        os.chmod(path_to_remove, 0o777)
        try:
            func(path_to_remove)
        except Exception:
            pass

    shutil.rmtree(path, onerror=_remove_readonly)


class DockerSandboxEngine(AbstractSandbox):
    """Concrete Docker SDK sandbox implementation with resource limits and rich diagnostics."""

    def __init__(
        self,
        image_tag: str = "python-pytest-sandbox:latest",
        timeout_seconds: int = 15,
    ):
        self.image_tag = image_tag
        self.timeout_seconds = timeout_seconds

        try:
            self.client = docker.from_env()
            self.client.ping()
        except (DockerException, Exception) as e:
            raise RuntimeError(
                f"\n❌ Docker daemon is unreachable. Ensure Docker is running.\nUnderlying error: {e}"
            ) from e

    def run_tests(
        self, refactored_code: str, test_code: str, timeout: int = 30
    ) -> ExecutionResult:
        effective_timeout = timeout or self.timeout_seconds

        host_temp_dir = tempfile.mkdtemp(prefix="agent_sandbox_")
        os.chmod(host_temp_dir, 0o777)

        try:
            solution_path = os.path.join(host_temp_dir, "solution.py")
            test_path = os.path.join(host_temp_dir, "test_solution.py")

            with open(solution_path, "w", encoding="utf-8") as f:
                f.write(refactored_code)

            # Explicit import instead of wildcard to avoid scope pollution
            with open(test_path, "w", encoding="utf-8") as f:
                f.write("import solution\nfrom solution import *\n\n" + test_code)

            os.chmod(solution_path, 0o666)
            os.chmod(test_path, 0o666)

            container = None
            try:
                container = self.client.containers.run(
                    image=self.image_tag,
                    # Added --tb=short for rich failure feedback without cluttering token window
                    command="python -m pytest test_solution.py -v --tb=short -p no:cacheprovider -o addopts=''",
                    volumes={host_temp_dir: {"bind": "/app", "mode": "rw"}},
                    working_dir="/app",
                    network_mode="none",
                    mem_limit="256m",
                    nano_cpus=1000000000,
                    detach=True,
                )

                result = container.wait(timeout=effective_timeout)
                exit_code = result.get("StatusCode", -1)

                logs_bytes = container.logs(stdout=True, stderr=True)
                logs_str = logs_bytes.decode("utf-8", errors="replace")

                passed = exit_code == 0
                
                # CRITICAL FIX: Keep stdout/stderr captured regardless of exit code
                # Pytest outputs test failure details to STDOUT!
                return ExecutionResult(
                    passed=passed,
                    exit_code=exit_code,
                    stdout=logs_str,
                    stderr=logs_str if not passed else "",
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
                    stack_trace=f"Sandbox Execution Failure:\n{error_msg}",
                )

            finally:
                if container:
                    try:
                        container.remove(force=True)
                    except Exception:
                        pass

        finally:
            _force_rmtree(host_temp_dir)