# In src/agent/factory.py
import os
from langchain_groq import ChatGroq

def get_llm_engine():
    # Use llama-3.1-8b-instant as high-throughput default to prevent TPD rate limit errors in CI
    model_name = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is not set.")
    
    return ChatGroq(
        model_name=model_name,
        groq_api_key=api_key,
        temperature=0.1,
    )