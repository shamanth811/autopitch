import time

import pytest
from fastapi.testclient import TestClient

from autopitch.api import create_app
from autopitch.config import Settings
from autopitch.jobs import stage_of
from autopitch.llm import LLMError
from autopitch.storage import JobStore
from autopitch.testing import make_pdf
from tests.test_api import _graph

ALICE = {"X-Owner-Id": "alice-owner-id-0001"}
BOB = {"X-Owner-Id": "bob-owner-id-000002"}


def _client(sample_deck, tmp_path, graph=None, **overrides) -> TestClient:
    settings = Settings(_env_file=None, db_path=str(tmp_path / "t.db"), **overrides)
    return TestClient(create_app(settings, lambda s: graph or _graph(sample_deck)))


def _submit(client, headers=ALICE, data=None):
    return client.post(
        "/v1/jobs",
        files={"file": ("acme.pdf", data or make_pdf(["Acme Grid"]), "application/pdf")},
        headers=headers,
    )


def _wait(client, job_id, headers=ALICE, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        body = client.get(f"/v1/jobs/{job_id}", headers=headers).json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_job_runs_and_report_is_saved(sample_deck, tmp_path):
    client = _client(sample_deck, tmp_path)
    r = _submit(client)
    assert r.status_code == 202
    body = _wait(client, r.json()["id"])
    assert body["status"] == "done" and body["stage"] == "done"
    assert body["company"] == "Acme Grid" and body["filename"] == "acme.pdf"
    assert body["report"]["composite"]["score"] == pytest.approx(7.0)

    listed = client.get("/v1/jobs", headers=ALICE).json()
    assert [j["id"] for j in listed] == [r.json()["id"]]
    assert "report" not in listed[0]  # summaries stay small


def test_reports_are_private_to_their_owner(sample_deck, tmp_path):
    client = _client(sample_deck, tmp_path)
    job_id = _submit(client).json()["id"]
    _wait(client, job_id)
    assert client.get(f"/v1/jobs/{job_id}", headers=BOB).status_code == 404
    assert client.get("/v1/jobs", headers=BOB).json() == []
    assert client.delete(f"/v1/jobs/{job_id}", headers=BOB).status_code == 404
    assert client.delete(f"/v1/jobs/{job_id}", headers=ALICE).status_code == 204
    assert client.get(f"/v1/jobs/{job_id}", headers=ALICE).status_code == 404


@pytest.mark.parametrize("headers", [{}, {"X-Owner-Id": "short"}, {"X-Owner-Id": "bad id!" * 4}])
def test_owner_header_is_required_and_validated(sample_deck, tmp_path, headers):
    client = _client(sample_deck, tmp_path)
    assert client.get("/v1/jobs", headers=headers).status_code == 400
    assert _submit(client, headers=headers).status_code == 400


def test_failed_job_reports_generic_error(sample_deck, tmp_path):
    class Broken:
        def stream(self, *a, **k):
            raise LLMError("api key sk-secret rejected")

    client = _client(sample_deck, tmp_path, graph=Broken())
    body = _wait(client, _submit(client).json()["id"])
    assert body["status"] == "failed"
    assert "sk-secret" not in body["error"] and body["report"] is None


def test_bad_uploads_are_rejected_before_a_job_exists(sample_deck, tmp_path):
    client = _client(sample_deck, tmp_path)
    assert _submit(client, data=b"MZ not a pdf").status_code == 415
    assert client.get("/v1/jobs", headers=ALICE).json() == []


def test_stage_is_derived_from_graph_state():
    assert stage_of({"slides": []}) == "extract"
    assert stage_of({"deck": 1}) == "score"
    assert stage_of({"deck": 1, "composite": 1}) == "benchmark"
    assert stage_of({"deck": 1, "composite": 1, "benchmark": 1}) == "objections"
    assert stage_of({"objections": []}) == "done"


def test_store_recovers_interrupted_jobs_and_purges_old_ones(tmp_path):
    store = JobStore(str(tmp_path / "s.db"))
    running = store.create("o" * 16, "a.pdf")
    store.set_stage(running, "score")
    done = store.create("o" * 16, "b.pdf")
    store.complete(done, "{}", "B", 5.0)

    assert store.fail_interrupted() == 1
    assert store.get(running, "o" * 16)["status"] == "failed"
    assert store.get(done, "o" * 16)["status"] == "done"

    store._run("UPDATE jobs SET created_at='2000-01-01T00:00:00+00:00' WHERE id=?", (done,))
    assert store.purge(30) == 1
    assert store.purge(0) == 0  # 0 means keep forever


def test_rubric_endpoint_exposes_criteria_and_weights(sample_deck, tmp_path):
    body = _client(sample_deck, tmp_path).get("/v1/rubric").json()
    assert {s["name"] for s in body["sections"]} == {
        "problem", "market", "traction", "team", "moat", "financials"
    }  # fmt: skip
    for weights in body["weights_by_stage"].values():
        assert sum(weights.values()) == pytest.approx(1.0)


def test_declared_oversize_body_is_refused_before_parsing(sample_deck, tmp_path):
    client = _client(sample_deck, tmp_path, max_upload_mb=1)
    r = client.post("/v1/analyze", content=b"x", headers={"content-length": str(5 * 1024 * 1024)})
    assert r.status_code == 413 and r.headers["x-request-id"]


def test_invalid_format_is_rejected(sample_deck, tmp_path):
    client = _client(sample_deck, tmp_path)
    r = client.post(
        "/v1/analyze?format=xml",
        files={"file": ("d.pdf", make_pdf(["x"]), "application/pdf")},
    )
    assert r.status_code == 422


def test_spa_fallback_serves_index_for_client_routes(tmp_path):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<title>App</title>")
    (web / "assets" / "a.js").write_text("1")
    client = TestClient(create_app(Settings(_env_file=None, frontend_dir=str(web)), lambda s: None))
    assert "App" in client.get("/reports/abc123").text  # deep link -> index.html
    assert client.get("/assets/a.js").text == "1"
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/v1/rubric").status_code == 200  # API not shadowed


def test_rate_limiter_forgets_idle_clients():
    from autopitch.ratelimit import RateLimiter

    now = [0.0]
    limiter = RateLimiter(limit=5, window_seconds=10, clock=lambda: now[0])
    for i in range(499):
        limiter.check(f"client-{i}")
    now[0] = 100.0
    limiter.check("late")  # 500th call triggers the sweep
    assert set(limiter._hits) == {"late"}


def test_proxy_header_is_only_trusted_when_enabled(sample_deck, tmp_path):
    def analyze(client, ip):
        return client.post(
            "/v1/analyze",
            files={"file": ("d.pdf", make_pdf(["x"]), "application/pdf")},
            headers={"x-forwarded-for": ip},
        ).status_code

    untrusted = _client(sample_deck, tmp_path, rate_limit_per_minute=1)
    assert [analyze(untrusted, "1.1.1.1"), analyze(untrusted, "2.2.2.2")] == [200, 429]
    trusted = _client(sample_deck, tmp_path, rate_limit_per_minute=1, trust_proxy_headers=True)
    assert [analyze(trusted, "1.1.1.1"), analyze(trusted, "2.2.2.2")] == [200, 200]
