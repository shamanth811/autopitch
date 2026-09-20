"""Builds concrete clients from settings, so entry points share one wiring path."""

from __future__ import annotations

from pathlib import Path

from autopitch.config import Settings
from autopitch.llm import LLMClient
from autopitch.llm.gemini import GeminiClient
from autopitch.llm.llama import LlamaClient
from autopitch.llm.retry import RetryingLLM
from autopitch.parsing.ocr import OcrClient
from autopitch.retrieval import Embedder, GeminiEmbedder, PineconeStore, VectorStore, VoyageEmbedder
from autopitch.retrieval.formd import FormDStore
from autopitch.tracing import TracedLLM


def build_gemini(s: Settings) -> LLMClient:
    return TracedLLM(RetryingLLM(GeminiClient(api_key=s.gemini_api_key, model=s.gemini_model)))


def build_llama(s: Settings) -> LLMClient:
    # More patience than the default: free-tier 429s ask for waits of several seconds.
    return TracedLLM(
        RetryingLLM(
            LlamaClient(base_url=s.llama_base_url, api_key=s.llama_api_key, model=s.llama_model),
            attempts=5,
            base_delay=2.0,
        )
    )


def build_extraction_llm(s: Settings) -> LLMClient:
    """Gemini when configured, otherwise the scoring model."""
    return build_gemini(s) if s.gemini_api_key else build_llama(s)


def embedding_provider(s: Settings) -> str | None:
    """Resolve the provider, or None when no embedding credentials are configured."""
    auto = s.embedding_provider == "auto"
    if (s.embedding_provider == "voyage" or auto) and s.voyage_api_key:
        return "voyage"
    if (s.embedding_provider == "gemini" or auto) and s.gemini_api_key:
        return "gemini"
    return None


def build_embedder(s: Settings) -> Embedder | None:
    provider = embedding_provider(s)
    if provider == "voyage":
        return VoyageEmbedder(
            s.voyage_api_key,
            model=s.voyage_model,
            dim=s.embedding_dim,
            min_interval=s.voyage_min_interval_seconds,
        )
    if provider == "gemini":
        return GeminiEmbedder(
            api_key=s.gemini_api_key, model=s.gemini_embedding_model, dim=s.embedding_dim
        )
    return None


def build_store(s: Settings) -> VectorStore:
    return PineconeStore(
        api_key=s.pinecone_api_key,
        index_name=s.pinecone_index,
        namespace=s.pinecone_namespace,
        dim=s.embedding_dim,
    )


def build_ocr(s: Settings) -> OcrClient | None:
    """None when OCR is disabled or no Mistral keys are set (image-only decks are then rejected)."""
    keys = [k.strip() for k in s.mistral_api_keys.split(",") if k.strip()]
    if not s.ocr_enabled or not keys:
        return None
    return OcrClient(keys, model=s.ocr_model)


def build_formd_store(s: Settings) -> FormDStore | None:
    """The Form D store, or None if it has not been built yet (nothing to benchmark against)."""
    if not Path(s.formd_db_path).is_file():
        return None
    store = FormDStore(s.formd_db_path)
    return store if store.coverage()[0] else None
