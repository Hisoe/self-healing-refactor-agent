# Self-Healing Code Refactoring Agent

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)
[![Docker Sandbox](https://img.shields.io/badge/Security-Docker_Sandbox-blue.svg)](https://www.docker.com/)
[![Evals Pass@N](https://img.shields.io/badge/Pass%40N-86.67    %25-brightgreen.svg)](#-benchmark--evaluation-metrics)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)


An enterprise-grade autonomous agentic system built with **LangGraph**, **Pydantic v2**, and **Docker** that refactors legacy Python code into modern, typed Python 3.10+, automatically generates `pytest` test suites, and executes closed-loop self-healing inside an isolated execution container.

---

## 🎯 Architectural Overview

Unlike zero-shot LLM code generators that output unvalidated code, this system implements a **deterministic, closed-loop feedback control graph**:

### LangGraph State Topology

```mermaid
graph TD
    A[Start: Original Legacy Code] --> B[refactor_node]
    B --> C[generate_tests_node]
    C --> D[run_tests_node: Ephemeral Docker Execution]
    D --> E{should_continue: Sandbox Exit Code 0?}
    E -- Yes: Tests Passed --> F[__END__: Validated Refactored Code]
    E -- No: Tests Failed & Retry < Max --> G[Inject Traceback to Memory]
    G --> B
    E -- No: Max Iterations Exceeded --> H[__END__: Terminate Safely]
```

### Self-Healing Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant User as CLI / API
    participant Graph as LangGraph Engine
    participant LLM as LLM Factory (Groq / OpenAI)
    participant Parser as Multi-Stage AST Repair
    participant Docker as Ephemeral Sandbox (Docker)

    User->>Graph: Invoke State (Legacy Code)
    loop Up to Max Iterations
        Graph->>LLM: Generate Modern Refactored Code
        LLM-->>Parser: Output Raw JSON / Code Block
        Parser-->>Graph: Return Clean RefactoredCodeOutput Schema
        Graph->>LLM: Generate Pytest Suite
        LLM-->>Parser: Output Pytest Code
        Parser-->>Graph: Return Clean PytestSuiteOutput Schema
        Graph->>Docker: Execute pytest inside sandbox (256MB, network=none)
        Docker-->>Graph: Return ExecutionResult (Exit Code, stdout, stderr)
        alt Exit Code == 0 (Pass)
            Graph-->>User: Return Validated Solution & Exit
        else Exit Code != 0 (Fail)
            Graph->>Graph: Append Stack Trace to State (failure_history)
        end
    end
```

---

## 🔒 Security Architecture (Zero-Trust Sandbox)

Executing AI-generated code directly on host machines introduces severe Remote Code Execution (RCE) vulnerabilities. This project implements a hardened, non-root Docker sandbox execution engine using the Strategy Pattern (`AbstractSandbox`):

* **Zero Network Socket Exposure (`network_mode="none"`)**: Prevents socket creation or egress data exfiltration from generated code.
* **Strict Cgroup Resource Limits**: Constrains memory allocation to 256MB RAM to mitigate memory-exhaustion Denial-of-Service attacks.
* **Non-Root Execution**: Runs scripts under an unprivileged system user (`sandboxuser`).
* **Process Timeouts**: Hard termination timeouts prevent infinite loop locks inside containers.

---

## 📊 Benchmark & Evaluation Metrics

Evaluated across an un-seeded 15-scenario technical debt benchmark suite (`data/benchmarks/test_cases.json`) covering untyped dictionary accesses, recursive bottlenecks, mutable default arguments (`B006`), unclosed file handles, and bare exception handling using isolated container execution and client-side rate limiting.

### Empirical System Performance

| Metric | Empirical Measurement | Target Threshold | Status |
| :--- | :--- | :--- | :---: |
| **Total Scenarios Evaluated** | 15 / 15 | 15 | ✅ Complete |
| **Pass@1 Rate (First Attempt)** | 100.0% | > 85.0% | 🚀 Exceeds |
| **Pass@N Rate (Self-Healed)** | 100.0% | > 90.0% | 🚀 Exceeds |
| **Average Iterations to Resolution** | 1.00 iteration | < 2.20 | ⚡ Optimal |
| **Total Execution Duration** | 142.75s | - | 🏎️ Parallel |
| **AST Parse Recovery Reliability** | 100.0% via multi-stage pipeline | 100.0% | ✅ Complete |

### Detailed Test Case Matrix

| Benchmark ID | Benchmark Description | Status | Iterations | Duration |
| :--- | :--- | :---: | :---: | :---: |
| `bench_01_dictionary_filtering` | Untyped Dictionary Filtering & Comprehensions | ✅ PASSED | 1 | 11.37s |
| `bench_02_fibonacci_recursion` | Inefficient Recursive Fibonacci Modernization | ✅ PASSED | 1 | 9.61s |
| `bench_03_string_aggregation` | Inefficient String Concatenation in Loop | ✅ PASSED | 1 | 8.92s |
| `bench_04_mutable_default_args` | Mutable Default Parameter Bug (`B006`) | ✅ PASSED | 1 | 8.94s |
| `bench_05_unhandled_dict_get` | Unsafe Key Access with Missing Fallbacks | ✅ PASSED | 1 | 10.15s |
| `bench_06_unclosed_file_handle` | Unclosed File IO Handle Context Manager | ✅ PASSED | 1 | 8.84s |
| `bench_07_manual_sum_loop` | Imperative Accumulation Loop Modernization | ✅ PASSED | 1 | 13.93s |
| `bench_08_duplicate_dict_keys` | Redundant Dict Key Transformation | ✅ PASSED | 1 | 11.07s |
| `bench_09_manual_type_casting` | Unsafe String to Int Conversion | ✅ PASSED | 1 | 9.16s |
| `bench_10_imperative_filtering` | Manual Deduplication and Filtering | ✅ PASSED | 1 | 9.00s |
| `bench_11_deprecated_has_key` | Legacy Dictionary Key Verification | ✅ PASSED | 1 | 8.25s |
| `bench_12_nested_indexing` | Unsafe Deep Nested Dictionary Indexing | ✅ PASSED | 1 | 10.07s |
| `bench_13_global_state_mutation` | Global Counter Side Effect Pattern | ✅ PASSED | 1 | 8.15s |
| `bench_14_raw_exception_swallowing` | Bare Exception Catching Clean-up | ✅ PASSED | 1 | 7.53s |
| `bench_15_legacy_formatting` | Legacy Percent Formatting Modernization | ✅ PASSED | 1 | 7.71s |

---

## 🛠️ AST-Level Defensive Parsing Pipeline

Open-weights models frequently emit unescaped triple-quotes, raw markdown fences, or malformed JSON payloads when generating multi-line code.

To eliminate schema validation crashes, `src/agent/nodes.py` uses a 4-stage fallback pipeline:

1. **Explicit Regex Extraction**: Isolates JSON block boundaries (`{ ... }`).
2. **Native JSON Deserialization**: Validates payloads directly against Pydantic models.
3. **Pushdown Automata Repair (`json_repair`)**: Corrects missing brackets, raw unescaped quotes, and trailing commas.
4. **Structural Raw Code Fallback**: Extracts Python code blocks directly if the model bypasses JSON structure entirely.

---

## 🚀 Quickstart

### Prerequisites

* Python 3.10+
* Docker Desktop (running)
* Groq API Key (or OpenAI API Key)

### Installation & Setup

```bash
# 1. Clone repository
git clone https://github.com/Hisoe/self-healing-refactor-agent.git
cd self-healing-refactor-agent

# 2. Set up virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install package in editable mode
pip install -e ".[dev]"
```

### Environment Setup

Create a `.env` file in the project root:

```env
MISTRAL_API_KEY=your_mistral_api_key
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key
LLM_PROVIDER=mistral
MISTRAL_MODEL=codestral-latest
```

---

## 💻 Usage

### Command Line Interface (CLI)

Run the refactoring agent on any Python target:

```bash
refactor-agent --file sample_input.py --max-iterations 3
```

### Run Benchmark Suite

Run the quantitative evaluation harness locally:

```bash
python -m evals.eval_runner
```

### Integration Unit Tests

Run the full Pytest integration suite validating Docker isolation and state nodes:

```bash
python -m pytest tests/ -v -s
```

---

## 📁 Project Structure

```plaintext
self-healing-refactor-agent/
├── .github/workflows/
│   └── eval.yml              # Automated CI/CD Regression Evaluation Pipeline
├── data/
│   └── benchmarks/
│       └── test_cases.json   # 15 Technical Debt Benchmark Scenarios
├── evals/
│   ├── results/              # Output Metric Logs
│   └── eval_runner.py        # Quantitative Evaluation Engine
├── src/
│   ├── agent/
│   │   ├── factory.py        # LLM Engine Factory
│   │   ├── graph.py          # LangGraph Control Workflow
│   │   ├── nodes.py          # State Transformation & AST Parsers
│   │   ├── prompts.py        # Isolated System Prompt Registry
│   │   └── schemas.py        # Pydantic Memory Contracts
│   ├── sandbox/
│   │   ├── base.py           # Abstract Sandbox Strategy Interface
│   │   └── docker_sandbox.py # Docker Execution Sandbox Engine
│   └── cli.py                # Terminal UI Application
├── tests/                    # Integration Test Suite
├── pyproject.toml            # Package Specs & Dependencies
├── sample_input.py           # Sample Target Script
└── README.md                 # System Architecture & Documentation
```
## 🔄 Automated CI/CD Regression Pipeline

This repository uses GitHub Actions to run automated agent evaluations on every Pull Request:

1. **Regression Prevention:** Ensures prompt changes or graph updates don't degrade the **Pass@N** resolution rate below 90%.
2. **Resource & Latency Tracking:** Blocks PRs if average iteration counts or execution times spike unexpectedly.
3. **Sandbox Isolation:** Spins up isolated Docker execution sandboxes inside the CI runner for safe runtime code evaluation.