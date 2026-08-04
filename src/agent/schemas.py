"""
src/agent/schemas.py
--------------------
Defines Pydantic data models for structured LLM outputs and the LangGraph shared agent state.
"""

from typing import Annotated, List, Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
import operator

# =====================================================================
# 1. Structured LLM Outputs (Contracts enforced on LLM responses)
# =====================================================================

class RefactoredCodeOutput(BaseModel):
    """Structured output specification for the Refactorer Node."""
    
    refactored_code: str = Field(
        ...,
        description="The modernized, PEP-8 compliant Python code with strict typing and docstrings."
    )
    explanation: str = Field(
        ...,
        description="Detailed summary of technical improvements, performance optimizations, and structural changes made."
    )
    imports_used: List[str] = Field(
        default_factory=list,
        description="List of standard library or third-party modules imported in the refactored code."
    )


class PytestSuiteOutput(BaseModel):
    """Structured output specification for the Test Generator Node."""
    
    test_code: str = Field(
        ...,
        description="Complete, self-contained pytest script testing happy paths, boundary constraints, and edge cases."
    )
    test_descriptions: List[str] = Field(
        default_factory=list,
        description="Brief bullet points describing what each unit test function validates."
    )


class ExecutionResult(BaseModel):
    """Deterministic result object emitted by the Sandboxed Pytest Runner."""
    
    passed: bool = Field(
        ..., 
        description="True if all pytest assertions passed (exit code 0), False otherwise."
    )
    exit_code: int = Field(
        ..., 
        description="Exit status code returned by the pytest runner subprocess."
    )
    stdout: str = Field(
        default="", 
        description="Standard output produced during pytest execution."
    )
    stderr: str = Field(
        default="", 
        description="Standard error output produced during pytest execution."
    )
    stack_trace: Optional[str] = Field(
        default=None, 
        description="Extracted traceback error message if the execution failed."
    )


# =====================================================================
# 2. LangGraph State Definition (Shared Working Memory)
# =====================================================================

class AgentState(TypedDict):
    """
    Shared state object flowing through every node in the LangGraph workflow.
    """
    original_code: str
    refactored_code: Optional[str]
    refactor_explanation: Optional[str]
    test_code: Optional[str]
    execution_result: Optional[ExecutionResult]
    iteration_count: int
    max_iterations: int
    failure_history: Annotated[List[str], operator.add]
    status: str