"""
evals/eval_runner.py
--------------------
Automated Evaluation Harness for the Self-Healing Refactor Agent.
Measures Pass@1, Pass@N, average self-healing iterations, and execution convergence.
"""

from dotenv import load_dotenv
load_dotenv()  # MUST BE CALLED BEFORE GRAPH OR LLM IMPORTS

import json
import time
import logging
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel

from src.agent.graph import build_graph

logger = logging.getLogger(__name__)


class BenchmarkMetric(BaseModel):
    benchmark_id: str
    benchmark_name: str
    passed: bool
    iterations_used: int
    duration_seconds: float
    status: str
    error_message: Optional[str] = None


class EvalReport(BaseModel):
    total_benchmarks: int
    pass_at_1: float
    pass_at_n: float
    avg_iterations: float
    total_duration_seconds: float
    results: List[BenchmarkMetric]


def run_evaluation_suite(
    benchmarks_path: str = "data/benchmarks/test_cases.json",
    max_iterations: int = 3,
) -> EvalReport:
    """Executes all benchmarks and generates statistical performance metrics."""
    bench_file = Path(benchmarks_path)
    if not bench_file.exists():
        raise FileNotFoundError(f"Benchmark file not found: {bench_file}")

    with open(bench_file, "r", encoding="utf-8") as f:
        benchmarks = json.load(f)

    app = build_graph()
    results: List[BenchmarkMetric] = []
    
    pass_1_count = 0
    pass_n_count = 0
    total_iterations = 0
    start_time = time.time()

    print(f"\n🚀 Running Evaluation Suite on {len(benchmarks)} Benchmarks...\n")

    for idx, bench in enumerate(benchmarks, 1):
        print(f"[{idx}/{len(benchmarks)}] Testing: {bench['name']} ({bench['id']})")
        
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
        final_state = app.invoke(initial_state)
        t1 = time.time()

        exec_res = final_state.get("execution_result")
        passed = bool(exec_res and exec_res.passed)
        iterations = final_state.get("iteration_count", 0)

        if passed:
            pass_n_count += 1
            if iterations == 1:
                pass_1_count += 1

        total_iterations += iterations

        metric = BenchmarkMetric(
            benchmark_id=bench["id"],
            benchmark_name=bench["name"],
            passed=passed,
            iterations_used=iterations,
            duration_seconds=round(t1 - t0, 2),
            status=final_state.get("status", "UNKNOWN"),
            error_message=exec_res.stderr if exec_res and not passed else None,
        )
        results.append(metric)

        status_str = "PASSED" if passed else "FAILED"
        print(f"    └─ Status: {status_str} | Iterations: {iterations} | Time: {metric.duration_seconds}s\n")

    total_time = round(time.time() - start_time, 2)
    total_count = len(benchmarks)

    report = EvalReport(
        total_benchmarks=total_count,
        pass_at_1=round((pass_1_count / total_count) * 100, 2) if total_count > 0 else 0.0,
        pass_at_n=round((pass_n_count / total_count) * 100, 2) if total_count > 0 else 0.0,
        avg_iterations=round(total_iterations / total_count, 2) if total_count > 0 else 0.0,
        total_duration_seconds=total_time,
        results=results,
    )

    return report


def render_report_markdown(report: EvalReport) -> str:
    """Formats evaluation metrics into a Markdown summary table."""
    md = []
    md.append("### 📊 Automated Evaluation Suite Summary\n")
    md.append(f"- **Total Benchmarks Evaluated:** `{report.total_benchmarks}`")
    md.append(f"- **Pass@1 Rate (First Try Pass):** `{report.pass_at_1}%`")
    md.append(f"- **Pass@N Rate (Self-Healed Pass):** `{report.pass_at_n}%`")
    md.append(f"- **Avg. Iterations to Resolution:** `{report.avg_iterations}`")
    md.append(f"- **Total Benchmark Execution Time:** `{report.total_duration_seconds}s`\n")

    md.append("| Benchmark ID | Benchmark Name | Status | Iterations | Duration |")
    md.append("|---|---|---|---|---|")
    for r in report.results:
        status_icon = "✅ PASSED" if r.passed else "❌ FAILED"
        md.append(f"| `{r.benchmark_id}` | {r.benchmark_name} | {status_icon} | {r.iterations_used} | {r.duration_seconds}s |")

    return "\n".join(md)


if __name__ == "__main__":
    report = run_evaluation_suite()
    markdown_output = render_report_markdown(report)
    
    output_dir = Path("evals/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / "latest_run.json", "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))

    print("\n" + "=" * 60)
    print(markdown_output)
    print("=" * 60)