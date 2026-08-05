"""
src/agent/factory.py
--------------------
LLM Factory supporting Mistral AI (Codestral), Gemini, and Groq with active 
client-side rate limiting and fallback chains.
"""

import os
import logging
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_mistralai import ChatMistralAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

logger = logging.getLogger(__name__)

# Client-side rate limiter for Mistral Free Tier (0.83 requests/sec = 1 req / 1.2 sec)
mistral_rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.83, 
    check_every_n_seconds=0.1,
    max_bucket_size=1,
)


def get_llm_engine(
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.1,
) -> BaseChatModel:
    """
    Returns an LLM ChatModel instance with client-side rate limiting and multi-provider failover.
    """
    provider = provider or os.getenv("LLM_PROVIDER", "mistral").lower()

    # 1. Mistral AI (Codestral)
    if provider == "mistral":
        mistral_key = os.getenv("MISTRAL_API_KEY")
        if not mistral_key:
            raise ValueError("MISTRAL_API_KEY environment variable is not set.")

        model = model_name or os.getenv("MISTRAL_MODEL", "codestral-latest")

        primary_llm = ChatMistralAI(
            model=model,
            mistral_api_key=mistral_key,
            temperature=temperature,
            max_retries=5,
            rate_limiter=mistral_rate_limiter,  # Enforces 1 req per 1.2s client-side
        )

        fallbacks = []

        # Fallback 1: Gemini 2.0 Flash
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            fallbacks.append(
                ChatGoogleGenerativeAI(
                    model="gemini-2.0-flash",
                    google_api_key=gemini_key,
                    temperature=temperature,
                    max_retries=2,
                )
            )

        # Fallback 2: Groq Llama 3.1 8B Instant
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            fallbacks.append(
                ChatGroq(
                    model_name="llama-3.1-8b-instant",
                    groq_api_key=groq_key,
                    temperature=temperature,
                    max_retries=2,
                )
            )

        if fallbacks:
            return primary_llm.with_fallbacks(fallbacks)

        return primary_llm

    # 2. Gemini Primary
    elif provider == "gemini":
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        return ChatGoogleGenerativeAI(
            model=model_name or os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            google_api_key=gemini_key,
            temperature=temperature,
            max_retries=3,
        )

    # 3. Groq Primary
    elif provider == "groq":
        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            raise ValueError("GROQ_API_KEY environment variable is not set.")

        return ChatGroq(
            model_name=model_name or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            groq_api_key=groq_key,
            temperature=temperature,
            max_retries=3,
        )

    raise ValueError(f"Unsupported LLM Provider: {provider}")