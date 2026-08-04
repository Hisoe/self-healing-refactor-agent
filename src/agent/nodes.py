"""
src/agent/nodes.py
------------------
Contains atomic LangGraph node functions and routing logic for the
self-healing code refactoring workflow with robust, multi-layer JSON parsing.
"""

import logging
import re
import json
from typing import Dict, Any, Literal
from json_repair import repair_json

from langchain_core.prompts import ChatPromptTemplate
from src.agent.factory import get_llm_engine
from src.agent.schemas import AgentState, RefactoredCodeOutput, PytestSuiteOutput
from src.agent.prompts import REFACTOR_SYSTEM_PROMPT, GENERATE_TESTS_SYSTEM_PROMPT
from src.sandbox.docker_sandbox import DockerSandboxEngine

logger = logging.getLogger(__name__)

# Shared engine instance to avoid redundant socket handshakes per loop pass
_SANDBOX_ENGINE = DockerSandboxEngine()


def _safe_parse_model(raw_text: str, schema_cls: type) -> Any:
    """
    Production-grade parser with strict multi-stage fallback:
    1. Regex extraction of explicit JSON objects ({ ... })
    2. Native json.loads() + Pydantic validation
    3. json_repair fallback
    4. Code extraction fallback if model emitted raw script
    """
    text = raw_text.strip()

    # 1. Strip markdown code fences if present (e.g. ```json or ```python)
    if "```" in text:
        text = re.sub(r"^```(?:json|python)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"```$", "", text, flags=re.MULTILINE).strip()

    # 2. Extract potential JSON object boundaries
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    json_candidate = text[start_idx : end_idx + 1] if (start_idx != -1 and end_idx > start_idx) else text

    # 3. Stage A: Standard Native JSON Parsing
    try:
        parsed_dict = json.loads(json_candidate)
        if isinstance(parsed_dict, dict):
            return schema_cls(**parsed_dict)
    except Exception:
        pass

    # 4. Stage B: Structural JSON Repair
    try:
        repaired_obj = repair_json(json_candidate, return_objects=True)
        if isinstance(repaired_obj, dict):
            # Ensure required schema fields exist before instantiation
            if schema_cls == RefactoredCodeOutput and "explanation" not in repaired_obj:
                repaired_obj["explanation"] = "Refactored to modern Python 3.10+ standards."
            if schema_cls == RefactoredCodeOutput and "imports_used" not in repaired_obj:
                repaired_obj["imports_used"] = []
            return schema_cls(**repaired_obj)
    except Exception as e:
        logger.warning(f"JSON repair failed: {e}. Falling back to raw text extraction.")

    # 5. Stage C: Fallback for Test Generator (Raw Pytest Code)
    if schema_cls == PytestSuiteOutput:
        logger.warning("LLM emitted raw Python test suite instead of JSON. Wrapping manually.")
        return PytestSuiteOutput(
            test_code=text,
            test_descriptions=["Extracted from raw model code output."]
        )

    # 6. Stage D: Fallback for Refactor Node (Raw Solution Code)
    if schema_cls == RefactoredCodeOutput:
        logger.warning("LLM emitted raw Python solution instead of JSON. Wrapping manually.")
        # Clean out any leftover JSON keys if raw string contains unparsed dict syntax
        clean_code = re.sub(r'^\s*"refactored_code":\s*"', '', text)
        clean_code = re.sub(r'"\s*,\s*"explanation".*$', '', clean_code, flags=re.DOTALL)
        return RefactoredCodeOutput(
            refactored_code=clean_code.strip(),
            explanation="Extracted from raw model code output.",
            imports_used=[]
        )

    raise ValueError(f"Could not parse valid schema from LLM response: {raw_text[:200]}...")


def _truncate_stack_trace(trace: str, max_lines: int = 40) -> str:
    """Truncates massive stack traces to prevent context window inflation."""
    lines = trace.splitlines()
    if len(lines) <= max_lines:
        return trace
    return "\n".join(lines[-max_lines:])


def refactor_node(state: AgentState) -> Dict[str, Any]:
    """
    Refactors original code into typed, modern Python 3.10+.
    Injects previous sandbox execution errors and failing refactored code if retrying.
    """
    llm = get_llm_engine()

    failure_context = ""
    code_to_refactor = state.get("refactored_code") or state["original_code"]

    if state.get("failure_history"):
        latest_error = _truncate_stack_trace(state["failure_history"][-1])
        failure_context = (
            f"\n\n### CRITICAL: PREVIOUS ATTEMPT FAILED IN SANDBOX EXECUTION ###\n"
            f"Your previous solution failed unit tests with this output:\n"
            f"```text\n{latest_error}\n```\n"
            f"Examine the failure trace and update the implementation to satisfy the test assertions.\n"
        )

    prompt = ChatPromptTemplate.from_messages([
        ("system", REFACTOR_SYSTEM_PROMPT),
        ("human", "Refactor or fix the following Python code:\n\n```python\n{code_to_refactor}\n```")
    ])

    formatted_prompt = prompt.format_messages(
        code_to_refactor=code_to_refactor,
        failure_context=failure_context
    )

    response = llm.invoke(formatted_prompt)
    result: RefactoredCodeOutput = _safe_parse_model(response.content, RefactoredCodeOutput)

    return {
        "refactored_code": result.refactored_code,
        "refactor_explanation": result.explanation,
        "status": "REFACTORED"
    }


def generate_tests_node(state: AgentState) -> Dict[str, Any]:
    """
    Generates unit tests targeting the refactored solution.
    Strictly enforces boolean literals and explicit imports.
    """
    llm = get_llm_engine()

    failure_context = ""
    if state.get("failure_history"):
        latest_error = _truncate_stack_trace(state["failure_history"][-1])
        failure_context = (
            f"\n\n### CRITICAL: PREVIOUS TEST EXECUTION FAILED ###\n"
            f"The previous test run failed with this output:\n"
            f"```text\n{latest_error}\n```\n"
            f"Fix any failing test assertions. Ensure dictionary boolean flags use real Python booleans (True/False) rather than string representations ('True'/'False').\n"
        )

    prompt = ChatPromptTemplate.from_messages([
        ("system", GENERATE_TESTS_SYSTEM_PROMPT),
        ("human", "Write pytest unit tests for this solution:\n\n```python\n{refactored_code}\n```")
    ])

    formatted_prompt = prompt.format_messages(
        refactored_code=state["refactored_code"],
        failure_context=failure_context
    )

    response = llm.invoke(formatted_prompt)
    result: PytestSuiteOutput = _safe_parse_model(response.content, PytestSuiteOutput)

    return {
        "test_code": result.test_code,
        "status": "TESTS_GENERATED"
    }


def run_tests_node(state: AgentState) -> Dict[str, Any]:
    """
    Executes the refactored code and test suite in the isolated Docker sandbox.
    """
    exec_result = _SANDBOX_ENGINE.run_tests(
        refactored_code=state["refactored_code"],
        test_code=state["test_code"]
    )

    new_iteration = state["iteration_count"] + 1

    updates: Dict[str, Any] = {
        "execution_result": exec_result,
        "iteration_count": new_iteration,
        "status": "PASSED" if exec_result.passed else "FAILED"
    }

    if not exec_result.passed and exec_result.stack_trace:
        updates["failure_history"] = [exec_result.stack_trace]

    return updates


def should_continue(state: AgentState) -> Literal["refactor_node", "__end__"]:
    """
    Conditional edge router that determines whether to terminate or self-heal.
    """
    exec_result = state.get("execution_result")

    if exec_result and exec_result.passed:
        logger.info("Sandbox tests passed successfully.")
        return "__end__"

    if state["iteration_count"] >= state["max_iterations"]:
        logger.warning(
            f"Reached max self-healing iterations ({state['max_iterations']}). Terminating."
        )
        return "__end__"

    logger.info(
        f"Tests failed on iteration {state['iteration_count']}. Routing to refactor_node for self-healing."
    )
    return "refactor_node"