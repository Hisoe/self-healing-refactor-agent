"""
src/agent/nodes.py
------------------
Contains atomic LangGraph node functions and routing logic with AST-guided 
un-squashing guards and pre-JSON control character escaping.
"""

import ast
import json
import logging
import re
from typing import Any, Dict, Literal
from json_repair import repair_json

from langchain_core.prompts import ChatPromptTemplate
from src.agent.factory import get_llm_engine
from src.agent.schemas import (
    AgentState,
    PytestSuiteOutput,
    RefactoredCodeOutput,
)
from src.agent.prompts import GENERATE_TESTS_SYSTEM_PROMPT, REFACTOR_SYSTEM_PROMPT
from src.sandbox.docker_sandbox import DockerSandboxEngine

logger = logging.getLogger(__name__)


def _sanitize_python_code(code: str) -> str:
    """
    AST-Guided Python Code Sanitizer.
    If valid Python, returns code untouched. If flattened onto a single line by JSON repair,
    restores linebreaks and indentation losslessly before AST parsing.
    """
    if not code or not code.strip():
        return code

    code = code.strip()

    # 1. Fast Path: Valid Python AST as-is
    try:
        ast.parse(code)
        return code
    except SyntaxError:
        pass

    # 2. Repair Path A: Handle literal '\n' text representations
    if "\\n" in code:
        candidate = code.replace("\\n", "\n").replace("\\t", "    ")
        try:
            ast.parse(candidate)
            return candidate
        except SyntaxError:
            pass

    # 3. Repair Path B: Lossless Un-squashing for single-line code created by json_repair
    if "\n" not in code and "def " in code:
        # Converts 4+ consecutive spaces after non-whitespace characters into \n + spaces
        candidate = re.sub(r"(\S)(\s{4,})", r"\1\n\2", code)
        try:
            ast.parse(candidate)
            return candidate
        except SyntaxError:
            pass

    return code


def _ensure_typing_imports(code: str) -> str:
    """Safely prepends missing `typing` module imports without breaking AST validity."""
    if not code or not code.strip():
        return code

    needed_symbols = []
    typing_symbols = ["Any", "Optional", "Union", "Dict", "List", "Tuple", "Callable"]

    for symbol in typing_symbols:
        if re.search(rf"\b{symbol}\b", code) and not re.search(rf"\bimport\s+.*\b{symbol}\b", code):
            needed_symbols.append(symbol)

    if needed_symbols and "from typing import" not in code:
        import_stmt = f"from typing import {', '.join(needed_symbols)}\n"
        return import_stmt + code

    return code


def _ensure_test_imports(test_code: str) -> str:
    """Safely prepends missing test framework modules (pytest, os, sys, pathlib)."""
    if not test_code or not test_code.strip():
        return test_code

    imports_to_add = []

    if "pytest" in test_code and not re.search(r"\bimport\s+pytest\b", test_code):
        imports_to_add.append("import pytest")
    if re.search(r"\bos\.", test_code) and not re.search(r"\bimport\s+os\b", test_code):
        imports_to_add.append("import os")
    if re.search(r"\bsys\.", test_code) and not re.search(r"\bimport\s+sys\b", test_code):
        imports_to_add.append("import sys")
    if "Path(" in test_code and not re.search(r"\bfrom\s+pathlib\s+import\s+Path\b", test_code):
        imports_to_add.append("from pathlib import Path")

    if imports_to_add:
        return "\n".join(imports_to_add) + "\n\n" + test_code

    return test_code


def _safe_parse_model(raw_text: str, schema_cls: type) -> Any:
    """
    Production-grade parser with pre-JSON control character escaping.
    Prevents json_repair from squashing code onto a single line.
    """
    text = raw_text.strip()

    if "```" in text:
        text = re.sub(r"^```(?:json|python)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"```$", "", text, flags=re.MULTILINE).strip()

    start_idx = text.find("{")
    end_idx = text.rfind("}")
    json_candidate = (
        text[start_idx : end_idx + 1]
        if (start_idx != -1 and end_idx > start_idx)
        else text
    )

    # Stage A1: Native JSON Parsing
    try:
        parsed_dict = json.loads(json_candidate, strict=False)
        if isinstance(parsed_dict, dict):
            return schema_cls(**parsed_dict)
    except Exception:
        pass

    # Stage A2: Pre-escape raw unescaped newlines inside JSON strings
    try:
        escaped_candidate = re.sub(r"(?<!\\)\n", r"\\n", json_candidate)
        parsed_dict = json.loads(escaped_candidate, strict=False)
        if isinstance(parsed_dict, dict):
            return schema_cls(**parsed_dict)
    except Exception:
        pass

    # Stage B: Repair Fallback
    try:
        repaired_obj = repair_json(json_candidate, return_objects=True)
        if isinstance(repaired_obj, dict):
            if schema_cls == RefactoredCodeOutput:
                repaired_obj.setdefault("explanation", "Refactored to modern Python 3.10+ standards.")
                repaired_obj.setdefault("imports_used", [])
            return schema_cls(**repaired_obj)
    except Exception as e:
        logger.warning(f"JSON repair failed: {e}. Falling back to raw text extraction.")

    # Stage C: Raw String Extraction Fallback
    if schema_cls == PytestSuiteOutput:
        return PytestSuiteOutput(
            test_code=_sanitize_python_code(text),
            test_descriptions=["Extracted from raw model code output."]
        )

    if schema_cls == RefactoredCodeOutput:
        code_match = re.search(r"```python\s*(.*?)\s*```", raw_text, re.DOTALL)
        if code_match:
            clean_code = code_match.group(1).strip()
        else:
            clean_code = re.sub(r"^(.*?)(def\s+|import\s+)", r"\2", raw_text, flags=re.DOTALL)
            clean_code = re.sub(r"```$", "", clean_code, flags=re.MULTILINE).strip()

        return RefactoredCodeOutput(
            refactored_code=_sanitize_python_code(clean_code),
            explanation="Extracted via fallback parser.",
            imports_used=[]
        )


def refactor_node(state: AgentState) -> Dict[str, Any]:
    """Refactors original code into typed, modern Python 3.10+."""
    llm = get_llm_engine()

    failure_context = ""
    code_to_refactor = state.get("refactored_code") or state["original_code"]

    if state.get("failure_history"):
        latest_error = state["failure_history"][-1][:1000]
        failure_context = (
            f"\n\n============================================================\n"
            f"⚠️ PREVIOUS ATTEMPT FAILED WITH THIS ERROR:\n"
            f"```text\n{latest_error}\n```\n"
            f"Address syntax errors, missing imports (e.g. from typing import Any), or bad logic.\n"
            f"============================================================\n"
        )

    prompt = ChatPromptTemplate.from_messages([
        ("system", REFACTOR_SYSTEM_PROMPT),
        ("human", "Refactor or fix the following Python code:\n\n```python\n{code_to_refactor}\n```")
    ])

    inputs = {
        "code_to_refactor": code_to_refactor,
        "failure_context": failure_context
    }

    try:
        structured_chain = prompt | llm.with_structured_output(RefactoredCodeOutput)
        result: RefactoredCodeOutput = structured_chain.invoke(inputs)
    except Exception as e:
        logger.warning(f"Structured output call failed in refactor_node ({e}). Falling back to manual parser.")
        raw_chain = prompt | llm
        response = raw_chain.invoke(inputs)
        result = _safe_parse_model(response.content, RefactoredCodeOutput)

    final_code = _sanitize_python_code(result.refactored_code)
    final_code = _ensure_typing_imports(final_code)

    return {
        "refactored_code": final_code,
        "refactor_explanation": result.explanation,
        "status": "REFACTORED"
    }


def generate_tests_node(state: AgentState) -> Dict[str, Any]:
    """Generates unit tests targeting the refactored solution."""
    llm = get_llm_engine()

    failure_context = ""
    if state.get("failure_history"):
        latest_error = state["failure_history"][-1][:1000]
        failure_context = (
            f"\n\n### PREVIOUS TEST EXECUTION FAILED ###\n"
            f"```text\n{latest_error}\n```\n"
            f"Double-check your mathematical calculations and ensure all test modules (os, pytest) are properly imported.\n"
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

    final_test_code = _sanitize_python_code(result.test_code)
    final_test_code = _ensure_test_imports(final_test_code)

    return {
        "test_code": final_test_code,
        "status": "TESTS_GENERATED"
    }


def run_tests_node(state: AgentState) -> Dict[str, Any]:
    """Executes the refactored code and test suite in the isolated Docker sandbox."""
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
    """Conditional edge router that determines whether to terminate or self-heal."""
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