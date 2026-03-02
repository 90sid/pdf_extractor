import os
from openai import OpenAI

def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Put it in .env or environment variables.")
    return OpenAI(api_key=api_key)

def get_model_name() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4.1").strip() or "gpt-4.1"
