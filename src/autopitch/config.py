"""Runtime configuration, read from environment variables or a local .env file."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

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
    pinecone_index: str = "autopitch-filings-1024"
    pinecone_namespace: str = "sec-s1"

    # Embeddings: "auto" picks Voyage if its key is set, else Gemini, else none (benchmark off).
    embedding_provider: Literal["auto", "voyage", "gemini"] = "auto"
    embedding_dim: int = 1024  # must equal the Pinecone index dimension
    voyage_api_key: str = ""
    voyage_model: str = "voyage-4"
    # Accounts without a payment method are limited to a few Voyage requests per minute.
    # Set to 0 once billing is added (the 200M free tokens still apply).
    voyage_min_interval_seconds: float = 21.0
    gemini_embedding_model: str = "gemini-embedding-001"

    # Form D rounds (built by scripts/ingest_formd.py). Needs no API key: it is a local file.
    formd_db_path: str = "data/formd.db"

    # SEC requires a User-Agent naming the requester, e.g. "Jane Doe jane@example.com"
    sec_user_agent: str = ""

    langsmith_api_key: str = ""
    langsmith_project: str = "autopitch"

    # OCR for image-only decks (Mistral). Comma-separated keys are rotated on rate limits.
    mistral_api_keys: str = ""
    ocr_enabled: bool = True
    ocr_model: str = "mistral-ocr-latest"

    max_upload_mb: int = 25
    max_pages: int = 60

    # Optional shared secret. When set, every /v1 request must send it as X-API-Key.
    api_key: str = ""
    rate_limit_per_minute: int = 10

    # Section scorers running at once. Low by default so a free-tier token-per-minute cap on
    # the scoring model is not hit by six simultaneous calls.
    scoring_concurrency: int = 2

    # Saved reports (SQLite file). Only finished reports are kept, never the uploaded PDF.
    db_path: str = "data/autopitch.db"
    retention_days: int = 30  # reports older than this are deleted at startup; 0 keeps forever
    max_concurrent_jobs: int = 2

    # Behind a reverse proxy every request has the proxy's address. Enable this only when a
    # trusted proxy appends the real client to X-Forwarded-For (the last entry is used).
    trust_proxy_headers: bool = False

    # Directory of the built web UI (frontend/dist). When set, it is served at /.
    frontend_dir: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
