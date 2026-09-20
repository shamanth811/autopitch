"""Builds concrete clients from settings, so entry points share one wiring path."""

from __future__ import annotations

from autopitch.config import Settings
from autopitch.llm import LLMClient
from autopitch.llm.gemini import GeminiClient
from autopitch.llm.llama import LlamaClient
from autopitch.llm.retry import RetryingLLM
from autopitch.retrieval import Embedder, GeminiEmbedder, PineconeStore, VectorStore
from autopitch.tracing import TracedLLM


def build_gemini(s: Settings) -> LLMClient:
    return TracedLLM(RetryingLLM(GeminiClient(api_key=s.gemini_api_key, model=s.gemini_model)))


def build_llama(s: Settings) -> LLMClient:
    return TracedLLM(
        RetryingLLM(
            LlamaClient(base_url=s.llama_base_url, api_key=s.llama_api_key, model=s.llama_model)
        )
    )


def build_embedder(s: Settings) -> Embedder:
    return GeminiEmbedder(api_key=s.gemini_api_key, model=s.embedding_model, dim=s.embedding_dim)


def build_store(s: Settings) -> VectorStore:
    return PineconeStore(
        api_key=s.pinecone_api_key,
        index_name=s.pinecone_index,
        namespace=s.pinecone_namespace,
        dim=s.embedding_dim,
    )
