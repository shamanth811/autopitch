import pytest
from fastapi.testclient import TestClient

from autopitch.api import create_app
from autopitch.config import Settings
from autopitch.graph import build_graph
from autopitch.llm import LLMError
from autopitch.llm.fake import FakeLLM
from autopitch.objections import _Objections
from autopitch.ratelimit import RateLimiter
from autopitch.schema import CriterionScore, Deck, Section
from autopitch.scoring import CRITERIA
from autopitch.scoring.nodes import _SectionJudgement
from autopitch.testing import make_pdf


def _graph(sample_deck):
    def judge(system, prompt):
        section = next(s for s in Section if f"Section under review: {s.value}" in prompt)
        return _SectionJudgement(
            criteria=[
                CriterionScore(criterion=n, score=7, reasoning="ok") for n in CRITERIA[section]
            ],
            summary="fine",
        )

    return build_graph(
        FakeLLM({Deck: sample_deck, _Objections: _Objections(objections=[])}),
        FakeLLM({_SectionJudgement: judge}),
    )


def _client(sample_deck, **overrides) -> TestClient:
    settings = Settings(_env_file=None, **overrides)
    return TestClient(create_app(settings, lambda s: _graph(sample_deck)))


def _post(client, data: bytes, **kw):
    return client.post("/v1/analyze", files={"file": ("deck.pdf", data, "application/pdf")}, **kw)


def test_healthz_and_security_headers(sample_deck):
    r = _client(sample_deck).get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-request-id"]


def test_analyze_returns_report(sample_deck):
    r = _post(_client(sample_deck), make_pdf(["Acme Grid"]))
    assert r.status_code == 200
    body = r.json()
    assert body["deck"]["company"] == "Acme Grid"
    assert body["composite"]["score"] == pytest.approx(7.0)


def test_markdown_format(sample_deck):
    r = _post(_client(sample_deck), make_pdf(["Acme Grid"]), params={"format": "markdown"})
    assert r.status_code == 200 and r.text.startswith("# Pitch analysis: Acme Grid")


def test_non_pdf_rejected_even_with_pdf_content_type(sample_deck):
    r = _post(_client(sample_deck), b"MZ\x90\x00 not a pdf")
    assert r.status_code == 415


def test_empty_upload_rejected(sample_deck):
    assert _post(_client(sample_deck), b"").status_code == 400


def test_oversize_upload_rejected(sample_deck):
    client = _client(sample_deck, max_upload_mb=1)
    r = _post(client, b"%PDF-" + b"0" * (1024 * 1024 + 1))
    assert r.status_code == 413


def test_page_limit_enforced(sample_deck):
    client = _client(sample_deck, max_pages=2)
    r = _post(client, make_pdf(["a", "b", "c"]))
    assert r.status_code == 422 and "limit is 2" in r.json()["detail"]


def test_api_key_required_when_configured(sample_deck):
    client = _client(sample_deck, api_key="s3cret")
    pdf = make_pdf(["Acme Grid"])
    assert _post(client, pdf).status_code == 401
    assert _post(client, pdf, headers={"X-API-Key": "wrong"}).status_code == 401
    assert _post(client, pdf, headers={"X-API-Key": "s3cret"}).status_code == 200


def test_rate_limit_returns_429_with_retry_after(sample_deck):
    client = _client(sample_deck, rate_limit_per_minute=2)
    pdf = make_pdf(["Acme Grid"])
    assert _post(client, pdf).status_code == 200
    assert _post(client, pdf).status_code == 200
    r = _post(client, pdf)
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1


def test_model_failure_is_502_without_leaking_details(sample_deck):
    class Broken:
        def invoke(self, _, config=None):
            raise LLMError("api key sk-secret rejected by provider")

    client = TestClient(create_app(Settings(_env_file=None), lambda s: Broken()))
    r = _post(client, make_pdf(["x"]))
    assert r.status_code == 502
    assert "sk-secret" not in r.text


def test_unconfigured_service_is_503():
    client = TestClient(create_app(Settings(_env_file=None), lambda s: None))
    assert _post(client, make_pdf(["x"])).status_code == 503


def test_rate_limiter_window_expires():
    now = [0.0]
    limiter = RateLimiter(limit=1, window_seconds=10, clock=lambda: now[0])
    assert limiter.check("a") == 0
    assert limiter.check("a") == pytest.approx(10)
    assert limiter.check("b") == 0  # separate client
    now[0] = 10.1
    assert limiter.check("a") == 0


def test_serves_built_frontend_without_shadowing_api(tmp_path):
    (tmp_path / "index.html").write_text("<title>AutoPitch</title>")
    app = create_app(Settings(frontend_dir=str(tmp_path)), graph_factory=lambda s: None)
    client = TestClient(app)
    assert "AutoPitch" in client.get("/").text
    assert client.get("/healthz").json() == {"status": "ok"}


def test_groq_only_config_builds_a_graph():
    from autopitch.api import _default_graph_factory

    # No Gemini key needed; the Groq scoring key is what gates the service.
    assert _default_graph_factory(Settings(_env_file=None, llama_api_key="k")) is not None
    assert _default_graph_factory(Settings(_env_file=None, gemini_api_key="g")) is None


def test_scoring_concurrency_is_applied(sample_deck):
    seen = {}

    class Spy:
        def invoke(self, state, config=None):
            seen["config"] = config
            raise LLMError("stop here")

    client = TestClient(
        create_app(Settings(scoring_concurrency=3), graph_factory=lambda s: Spy()),
        raise_server_exceptions=False,
    )
    _post(client, make_pdf(["x"]))
    assert seen["config"] == {"max_concurrency": 3}
