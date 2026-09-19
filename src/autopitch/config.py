"""Runtime configuration, read from environment variables or a local .env file."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AUTOPITCH_", extra="ignore")

    # Extraction, objection generation and report synthesis
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-pro"

    # Section scoring runs on Llama 3.1 behind any OpenAI-compatible endpoint
    # (Groq, Together, vLLM, Ollama, ...).
    llama_base_url: str = "https://api.groq.com/openai/v1"
    llama_api_key: str = ""
    llama_model: str = "llama-3.1-70b-versatile"

    pinecone_api_key: str = ""
    pinecone_index: str = "autopitch-filings"
    pinecone_namespace: str = "sec-s1"
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768

    max_upload_mb: int = 25


@lru_cache
def get_settings() -> Settings:
    return Settings()
