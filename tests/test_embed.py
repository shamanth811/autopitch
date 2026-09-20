import httpx
import pytest

from autopitch.config import Settings
from autopitch.factory import build_embedder, embedding_provider
from autopitch.retrieval import VoyageEmbedder


def _embedder(handler, **kw) -> VoyageEmbedder:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return VoyageEmbedder("key", dim=3, client=client, sleep=lambda _: None, **kw)


def _ok(request: httpx.Request) -> httpx.Response:
    n = len(request_json(request)["input"])
    # Returned out of order on purpose: the client must sort by index.
    rows = [{"index": i, "embedding": [float(i + 1), 0.0, 0.0]} for i in reversed(range(n))]
    return httpx.Response(200, json={"data": rows})


def request_json(request: httpx.Request) -> dict:
    import json

    return json.loads(request.content)


def test_documents_are_batched_ordered_and_typed():
    seen = []

    def handler(request):
        seen.append(request_json(request))
        return _ok(request)

    emb = _embedder(handler)
    vectors = emb.embed_documents([f"t{i}" for i in range(130)])
    assert len(vectors) == 130
    assert [len(b["input"]) for b in seen] == [128, 2]
    assert all(b["input_type"] == "document" and b["output_dimension"] == 3 for b in seen)
    assert vectors[1] == [1.0, 0.0, 0.0]  # normalised, and index order restored


def test_query_uses_query_input_type():
    seen = []

    def handler(request):
        seen.append(request_json(request))
        return _ok(request)

    _embedder(handler).embed_query("hello")
    assert seen[0]["input_type"] == "query"


def test_retries_rate_limit_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return _ok(request)

    assert _embedder(handler).embed_query("x")
    assert len(calls) == 3


def test_gives_up_after_max_attempts():
    emb = _embedder(lambda r: httpx.Response(429), attempts=2)
    with pytest.raises(httpx.HTTPStatusError):
        emb.embed_query("x")


def test_client_errors_are_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401)

    with pytest.raises(httpx.HTTPStatusError):
        _embedder(handler).embed_query("x")
    assert len(calls) == 1


def test_provider_resolution():
    def s(**kw):
        return Settings(_env_file=None, **kw)

    assert embedding_provider(s()) is None
    assert embedding_provider(s(gemini_api_key="g")) == "gemini"
    assert embedding_provider(s(voyage_api_key="v", gemini_api_key="g")) == "voyage"
    assert embedding_provider(s(embedding_provider="gemini", voyage_api_key="v")) is None
    assert embedding_provider(s(embedding_provider="voyage", gemini_api_key="g")) is None
    assert build_embedder(s()) is None
    assert isinstance(build_embedder(s(voyage_api_key="v")), VoyageEmbedder)


def test_calls_are_spaced_by_min_interval():
    now = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        now[0] += s

    client = httpx.Client(transport=httpx.MockTransport(_ok))
    emb = VoyageEmbedder(
        "k", dim=3, client=client, min_interval=20, sleep=sleep, clock=lambda: now[0]
    )
    emb.embed_query("a")
    now[0] += 5
    emb.embed_query("b")
    assert slept == [15]  # only the remainder of the interval is waited
