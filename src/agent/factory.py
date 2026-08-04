"""
src/agent/factory.py
--------------------
LLM Factory with automatic rate-limit retries and fallback handling.
"""

import os
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq


def get_llm_engine() -> BaseChatModel:
    """Returns an LLM ChatModel engine with automated fallback for rate limits."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is not set.")

    primary_model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # Primary 70B Model
    primary_llm = ChatGroq(
        model_name=primary_model_name,
        groq_api_key=api_key,
        temperature=0.1,
        max_retries=3,
    )

    # High-Throughput Fallback Model (500k TPD quota)
    fallback_llm = ChatGroq(
        model_name="llama-3.1-8b-instant",
        groq_api_key=api_key,
        temperature=0.1,
        max_retries=3,
    )

    # Automatically failover to 8B model if 70B hits 429 rate limits
    return primary_llm.with_fallbacks([fallback_llm])