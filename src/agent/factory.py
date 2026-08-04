"""
src/agent/factory.py
---------------------
Provider-agnostic LLM Factory supporting dynamic model initialization.
"""

import os
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

def get_llm_engine(
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.1
) -> BaseChatModel:
    """
    Returns an initialized LangChain ChatModel instance based on provider configuration.
    Defaults to Groq with Llama-3.3-70b.
    """
    provider = provider or os.getenv("LLM_PROVIDER", "groq").lower()

    if provider == "groq":
        model = model_name or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable is not set.")
            
        return ChatGroq(
            model=model,
            temperature=temperature,
            api_key=api_key,
            max_retries=2
        )

    elif provider == "openai":
        model = model_name or os.getenv("OPENAI_MODEL", "gpt-4o")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")
            
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=api_key
        )

    else:
        raise ValueError(f"Unsupported LLM Provider: {provider}")