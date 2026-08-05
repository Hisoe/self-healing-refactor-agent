"""
src/agent/nodes.py
------------------
Contains atomic LangGraph node functions and routing logic for the
self-healing code refactoring workflow with robust, multi-layer JSON parsing
and API-level Pydantic structured output enforcement.
"""

import logging
import re
import json
from typing import Dict, Any, Literal
from json_repair import repair_json

from langchain_core.prompts import ChatPromptTemplate
from src.agent.factory import get_llm_engine
from src.agent.schemas import (
    AgentState,
    RefactoredCodeOutput, 
    PytestSuiteOutput,
)
from src.agent.prompts import REFACTOR_SYSTEM_PROMPT, GENERATE_TESTS_SYSTEM_PROMPT
from src.sandbox.docker_sandbox import DockerSandboxEngine

logger = logging.getLogger(__name__)


def _safe_parse_model(raw_text: str, schema_cls: type) -> Any:
    """
    Production-grade parser with strict multi-stage fallback:
    1. Markdown fence stripping
    2. Native json.loads() + Pydantic validation
    3. json_repair fallback
    4. Structural AST/Regex fallback if model emitted raw script
    """
    text = raw_text.strip()

    # 1. Strip markdown code fences
    if "```" in text:
        text = re.sub(r"^```(?:json|python)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"```$", "", text, flags=re.MULTILINE).strip()

    # 2. Extract potential JSON object boundaries
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    json_candidate = (
        text[start_idx : end_idx + 1]
        if (start_idx != -1 and end_idx > start_idx)
        else text
    )

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
            if schema_cls == RefactoredCodeOutput:
                repaired_obj.setdefault("explanation", "Refactored to modern Python 3.10+ standards.")
                repaired_obj.setdefault("imports_used", [])
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

    # Stage D: Fallback for Refactor Node (Extract code block or raw string)
    if schema_cls == RefactoredCodeOutput:
        logger.warning("LLM emitted conversational or raw output instead of JSON. Extracting solution.")
        
        # 1. Look for explicit markdown code fence first
        code_match = re.search(r"```python\s*(.*?)\s*```", raw_text, re.DOTALL)
        if code_match:
            clean_code = code_match.group(1).strip()
        else:
            # 2. Strip leading conversational preambles
            clean_code = re.sub(r"^(.*?)(def\s+|import\s+)", r"\2", raw_text, flags=re.DOTALL)
            clean_code = re.sub(r"```$", "", clean_code, flags=re.MULTILINE).strip()

        return RefactoredCodeOutput(
            refactored_code=clean_code,
            explanation="Extracted via fallback parser.",
            imports_used=[]
        )


def _truncate_stack_trace(trace: str, max_lines: int = 40) -> str:
    """Truncates massive stack traces to prevent context window inflation."""
    if not trace:
        return ""
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

    inputs = {
        "code_to_refactor": code_to_refactor,
        "failure_context": failure_context
    }

    # Modern LCEL Invocation Pattern (Safe from raw string format collisions)
    try:
        structured_chain = prompt | llm.with_structured_output(RefactoredCodeOutput)
        result: RefactoredCodeOutput = structured_chain.invoke(inputs)
    except Exception as e:
        logger.warning(f"Structured output call failed in refactor_node ({e}). Falling back to manual parser.")
        raw_chain = prompt | llm
        response = raw_chain.invoke(inputs)
        result = _safe_parse_model(response.content, RefactoredCodeOutput)

    return {
        "refactored_code": result.refactored_code,
        "refactor_explanation": result.explanation,
        "status": "REFACTORED"
    }


def generate_tests_node(state: AgentState) -> Dict[str, Any]:
    """
    Generates unit tests targeting the refactored solution.
    Binds Pydantic structured output directly to LLM to guarantee valid JSON Schema adherence.
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

    inputs = {
        "refactored_code": state["refactored_code"],
        "failure_context": failure_context
    }

    try:
        structured_chain = prompt | llm.with_structured_output(PytestSuiteOutput)
        result: PytestSuiteOutput = structured_chain.invoke(inputs)
    except Exception as e:
        logger.warning(f"Structured output call failed in generate_tests_node ({e}). Falling back to manual parser.")
        raw_chain = prompt | llm
        response = raw_chain.invoke(inputs)
        result = _safe_parse_model(response.content, PytestSuiteOutput)

    return {
        "test_code": result.test_code,
        "status": "TESTS_GENERATED"
    }


def run_tests_node(state: AgentState) -> Dict[str, Any]:
    """
    Executes the refactored code and test suite in the isolated Docker sandbox.
    """
    sandbox_engine = DockerSandboxEngine()
    
    exec_result = sandbox_engine.run_tests(
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
        existing_history = state.get("failure_history") or []
        updates["failure_history"] = existing_history + [exec_result.stack_trace]

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