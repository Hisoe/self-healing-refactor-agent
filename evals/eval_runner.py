"""
evals/eval_runner.py
--------------------
Automated Asynchronous Evaluation Harness & Regression Suite.
Measures Pass@1, Pass@N, average self-healing iterations, and execution convergence.
Enforces strict CI/CD quality gates for automated Pull Request checks using async concurrency.
"""

from dotenv import load_dotenv

load_dotenv()  # MUST BE CALLED BEFORE GRAPH OR LLM IMPORTS

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

from src.agent.graph import build_graph

logger = logging.getLogger(__name__)

# --- CI/CD QUALITY GATE THRESHOLDS ---
MIN_PASS_AT_N_THRESHOLD = 80.0  # Require at least 80% Pass@N
MAX_AVG_ITERATIONS = 2.2  # Fail if loop efficiency degrades beyond 2.2 iterations

# --- CONCURRENCY CONTROL ---
# Set to 1 for rate-limited free tiers (e.g., Mistral 1 RPS); increase to 3-5 for higher tiers.
CONCURRENCY_LIMIT = int(os.getenv("EVAL_CONCURRENCY", "1"))
SEMAPHORE = asyncio.Semaphore(CONCURRENCY_LIMIT)


class BenchmarkMetric(BaseModel):
    """Execution telemetry for an individual benchmark run."""

    benchmark_id: str
    benchmark_name: str
    passed: bool
    iterations_used: int
    duration_seconds: float
    status: str
    error_message: Optional[str] = None


class EvalReport(BaseModel):
    """Aggregate performance report for the entire benchmark suite."""

    total_benchmarks: int
    pass_at_1: float
    pass_at_n: float
    avg_iterations: float
    total_duration_seconds: float
    provider_used: str = Field(default="unknown")
    results: List[BenchmarkMetric]


async def _run_single_benchmark(
    idx: int, total: int, bench: dict, app, max_iterations: int
) -> BenchmarkMetric:
    """Executes a single benchmark scenario asynchronously with semaphore rate control."""
    async with SEMAPHORE:
        print(f"[{idx}/{total}] Testing: {bench['name']} ({bench['id']})...")

        initial_state = {
            "original_code": bench["legacy_code"],
            "refactored_code": None,
            "refactor_explanation": None,
            "test_code": None,
            "execution_result": None,
            "iteration_count": 0,
            "max_iterations": max_iterations,
            "failure_history": [],
            "status": "INITIALIZED",
        }

        t0 = time.time()
        try:
            # Asynchronous state graph invocation
            final_state = await app.ainvoke(initial_state)
            t1 = time.time()

            exec_res = final_state.get("execution_result")
            passed = bool(exec_res and exec_res.passed)
            iterations = final_state.get("iteration_count", 0)
            status = final_state.get("status", "UNKNOWN")
            error_msg = exec_res.stderr if exec_res and not passed else None

        except Exception as e:
            t1 = time.time()
            logger.exception(f"Unhandled crash during benchmark scenario {bench['id']}: {e}")
            passed = False
            iterations = 0
            status = "CRASHED"
            error_msg = f"Runtime Exception: {str(e)}"

        duration = round(t1 - t0, 2)
        status_str = "PASSED" if passed else "FAILED"
        print(f"    └─ Status: {status_str} | Iterations: {iterations} | Time: {duration}s\n")

        return BenchmarkMetric(
            benchmark_id=bench["id"],
            benchmark_name=bench["name"],
            passed=passed,
            iterations_used=iterations,
            duration_seconds=duration,
            status=status,
            error_message=error_msg,
        )


async def run_evaluation_suite(
    benchmarks_path: str = "data/benchmarks/test_cases.json",
    max_iterations: int = 3,
) -> EvalReport:
    """Executes all benchmarks concurrently through the LangGraph engine and computes performance metrics."""
    bench_file = Path(benchmarks_path)
    if not bench_file.exists():
        raise FileNotFoundError(f"Benchmark dataset not found at path: {bench_file}")

    with open(bench_file, "r", encoding="utf-8") as f:
        benchmarks = json.load(f)

    app = build_graph()
    start_time = time.time()
    provider = os.getenv("LLM_PROVIDER", "mistral").lower()

    print(f"\n🚀 Running Async Evaluation Suite on {len(benchmarks)} Benchmarks...")
    print(f"⚙️ Provider: {provider.upper()} | Concurrency Limit: {CONCURRENCY_LIMIT}\n")

    # Launch benchmark tasks concurrently under semaphore control
    tasks = [
        _run_single_benchmark(idx, len(benchmarks), bench, app, max_iterations)
        for idx, bench in enumerate(benchmarks, 1)
    ]
    results: List[BenchmarkMetric] = await asyncio.gather(*tasks)

    total_time = round(time.time() - start_time, 2)
    total_count = len(benchmarks)

    pass_1_count = sum(1 for r in results if r.passed and r.iterations_used == 1)
    pass_n_count = sum(1 for r in results if r.passed)
    total_iterations = sum(r.iterations_used for r in results)

    report = EvalReport(
        total_benchmarks=total_count,
        pass_at_1=(
            round((pass_1_count / total_count) * 100, 2) if total_count > 0 else 0.0
        ),
        pass_at_n=(
            round((pass_n_count / total_count) * 100, 2) if total_count > 0 else 0.0
        ),
        avg_iterations=(
            round(total_iterations / total_count, 2) if total_count > 0 else 0.0
        ),
        total_duration_seconds=total_time,
        provider_used=provider,
        results=results,
    )

    return report


def render_report_markdown(report: EvalReport) -> str:
    """Formats evaluation metrics into a clean Markdown summary table."""
    md = []
    md.append("### 📊 Automated Evaluation Suite Summary\n")
    md.append(f"- **Provider / Engine:** `{report.provider_used.upper()}`")
    md.append(f"- **Total Benchmarks Evaluated:** `{report.total_benchmarks}`")
    md.append(f"- **Pass@1 Rate (First Attempt Pass):** `{report.pass_at_1}%`")
    md.append(f"- **Pass@N Rate (Self-Healed Pass):** `{report.pass_at_n}%`")
    md.append(f"- **Avg. Iterations to Resolution:** `{report.avg_iterations}`")
    md.append(
        f"- **Total Benchmark Execution Time:** `{report.total_duration_seconds}s`\n"
    )

    md.append("| Benchmark ID | Benchmark Name | Status | Iterations | Duration |")
    md.append("|---|---|---|---|---|")
    for r in report.results:
        status_icon = "✅ PASSED" if r.passed else "❌ FAILED"
        md.append(
            f"| `{r.benchmark_id}` | {r.benchmark_name} | {status_icon} | {r.iterations_used} | {r.duration_seconds}s |"
        )

    return "\n".join(md)


if __name__ == "__main__":
    report = asyncio.run(run_evaluation_suite())
    markdown_output = render_report_markdown(report)

    output_dir = Path("evals/results")
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "latest_run.json", "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))

    print("\n" + "=" * 60)
    print(markdown_output)
    print("=" * 60)

    # --- CI/CD QUALITY GATE ENFORCEMENT ---
    if report.pass_at_n < MIN_PASS_AT_N_THRESHOLD:
        print(
            f"\n❌ CI GATE FAILED: Pass@N ({report.pass_at_n}%) fell below required threshold ({MIN_PASS_AT_N_THRESHOLD}%)."
        )
        sys.exit(1)

    if report.avg_iterations > MAX_AVG_ITERATIONS:
        print(
            f"\n❌ CI GATE FAILED: Average iterations ({report.avg_iterations}) exceeded maximum allowable limit ({MAX_AVG_ITERATIONS})."
        )
        sys.exit(1)

    print("\n✅ ALL CI EVALUATION GATES PASSED SUCCESSFULLY.")
    sys.exit(0)