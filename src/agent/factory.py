"""
src/agent/factory.py
--------------------
LLM Factory with automatic rate-limit retry policy and model fallbacks.
"""

import os
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq


def get_llm_engine(
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.1,
) -> BaseChatModel:
    """
    Returns an initialized LangChain ChatModel instance based on provider configuration.
    Defaults to Groq with llama-3.1-8b-instant for high throughput and high TPD allowance.
    """
    provider = provider or os.getenv("LLM_PROVIDER", "groq").lower()

    if provider == "groq":
        model = model_name or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        api_key = os.getenv("GROQ_API_KEY")

        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable is not set.")

        return ChatGroq(
            model_name=model,
            groq_api_key=api_key,
            temperature=temperature,
            max_retries=5,  # Automatic retry policy for HTTP 429 backoff
            request_timeout=60.0,
        )

    raise ValueError(f"Unsupported LLM Provider: {provider}")