import os
from openai import AsyncOpenAI

PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "chat_model": "openai/gpt-oss-20b", 
        "stt_model": "whisper-large-v3-turbo",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "chat_model": "meta-llama/llama-3.3-70b-instruct:free",
        "stt_model": None,
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "chat_model": "gemini-2.5-flash",
        "stt_model": None,
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "chat_model": "llama3.1:8b",
        "stt_model": None,
    },
}

def get_llm_client(provider: str, api_key: str):
    cfg = PROVIDERS.get(provider, PROVIDERS["groq"])
    key = api_key.strip() if api_key else os.getenv("API_KEY")
    return AsyncOpenAI(base_url=cfg["base_url"], api_key=key), cfg