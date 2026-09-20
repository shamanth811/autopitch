"""HTTP API.

Trust boundaries handled here: the uploaded file (size, type and page limits, never written
to disk by this code), the caller (optional API key, rate limit, per-browser owner id), and
model failures (logged in full, reported to the client without internals).
"""

from __future__ import annotations

import hmac
import logging
import re
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from autopitch.config import Settings, get_settings
from autopitch.jobs import JobRunner
from autopitch.llm import LLMError
from autopitch.objections import WEAK_THRESHOLD
from autopitch.parsing import DeckParseError, OcrUnavailableError, read_slides
from autopitch.ratelimit import RateLimiter
from autopitch.report import Report, build_report, render_markdown
from autopitch.scoring.rubric import _DEFAULT, CRITERIA, STAGE_WEIGHTS
from autopitch.storage import JobStore
from autopitch.tracing import configure_tracing

log = logging.getLogger("autopitch.api")

_PDF_MAGIC = b"%PDF-"
_CHUNK = 1024 * 1024
_MULTIPART_OVERHEAD = 1024 * 1024  # form boundaries and headers around the file itself
_OWNER_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def _default_graph_factory(settings: Settings):
    from autopitch.factory import (
        build_embedder,
        build_extraction_llm,
        build_formd_store,
        build_llama,
        build_store,
        embedding_provider,
    )
    from autopitch.graph import build_graph

    if not settings.llama_api_key:
        return None
    embedder = store = None
    if settings.pinecone_api_key and embedding_provider(settings):
        embedder, store = build_embedder(settings), build_store(settings)
    elif settings.pinecone_api_key:
        log.warning("Pinecone is set but no embedding key is; benchmark step disabled.")
    return build_graph(
        build_extraction_llm(settings),
        build_llama(settings),
        embedder,
        store,
        build_formd_store(settings),
    )


def _default_ocr_factory(settings: Settings):
    from autopitch.factory import build_ocr

    return build_ocr(settings)


class SPAStaticFiles(StaticFiles):
    """Serves the built web app; unknown paths get index.html so client-side routes work."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and "." not in Path(path).name:
                return await super().get_response("index.html", scope)
            raise


def _security_headers(response: Response, request_id: str) -> Response:
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


def create_app(
    settings: Settings | None = None,
    graph_factory: Callable[[Settings], object] = _default_graph_factory,
    ocr_factory: Callable[[Settings], object] = _default_ocr_factory,
) -> FastAPI:
    settings = settings or get_settings()
    if configure_tracing(settings):
        log.info("LangSmith tracing enabled, project=%s", settings.langsmith_project)
    app = FastAPI(title="AutoPitch", version="0.1.0")
    limiter = RateLimiter(settings.rate_limit_per_minute)
    state: dict[str, object] = {}
    ocr = ocr_factory(settings)  # None when OCR is off or has no keys; image-only decks then 422

    def get_graph():
        if "graph" not in state:
            state["graph"] = graph_factory(settings)
        if state["graph"] is None:
            raise HTTPException(503, "Service is not configured with model credentials.")
        return state["graph"]

    def get_store() -> JobStore:
        # Created on first use so importing the app never touches the filesystem.
        if "store" not in state:
            store = JobStore(settings.db_path)
            store.fail_interrupted()
            store.purge(settings.retention_days)
            state["store"] = store
            state["runner"] = JobRunner(
                store, settings.max_concurrent_jobs, settings.scoring_concurrency
            )
        return state["store"]  # type: ignore[return-value]

    def authenticate(x_api_key: Annotated[str | None, Header()] = None) -> None:
        if settings.api_key and not (
            x_api_key and hmac.compare_digest(x_api_key.encode(), settings.api_key.encode())
        ):
            raise HTTPException(401, "Missing or invalid API key.")

    def client_id(request: Request) -> str:
        if settings.trust_proxy_headers:
            forwarded = request.headers.get("x-forwarded-for", "")
            if forwarded:
                return forwarded.split(",")[-1].strip()
        return request.client.host if request.client else "unknown"

    def rate_limit(request: Request) -> None:
        retry_after = limiter.check(client_id(request))
        if retry_after:
            raise HTTPException(
                429, "Rate limit exceeded.", headers={"Retry-After": str(int(retry_after) + 1)}
            )

    def owner(x_owner_id: Annotated[str | None, Header()] = None) -> str:
        if not x_owner_id or not _OWNER_RE.match(x_owner_id):
            raise HTTPException(400, "Missing or malformed X-Owner-Id header.")
        return x_owner_id

    Owner = Depends(owner)  # a default value, not an annotation, so it resolves under
    # `from __future__ import annotations` even though `owner` is local to this function.

    @app.middleware("http")
    async def harden(request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        # Starlette buffers a multipart body before any handler runs, so refuse oversized
        # uploads from the declared length first.
        declared = request.headers.get("content-length", "")
        cap = settings.max_upload_mb * 1024 * 1024 + _MULTIPART_OVERHEAD
        if declared.isdigit() and int(declared) > cap:
            return _security_headers(
                JSONResponse({"detail": f"File exceeds {settings.max_upload_mb} MB."}, 413),
                request_id,
            )
        return _security_headers(await call_next(request), request_id)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    async def read_upload(file: UploadFile) -> bytes:
        limit = settings.max_upload_mb * 1024 * 1024
        data = bytearray()
        while chunk := await file.read(_CHUNK):
            data += chunk
            if len(data) > limit:  # stop reading as soon as the cap is crossed
                raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB.")
        if not data:
            raise HTTPException(400, "Empty upload.")
        if not data.startswith(_PDF_MAGIC):  # content-type headers are client-controlled
            raise HTTPException(415, "Only PDF decks are supported.")
        return bytes(data)

    async def parse_upload(file: UploadFile):
        data = await read_upload(file)
        try:
            # OCR (when a deck has image-only pages) is a network call, so keep it off the loop.
            return await run_in_threadpool(read_slides, data, settings.max_pages, ocr)
        except OcrUnavailableError as exc:
            log.error("OCR unavailable: %s", exc)
            raise HTTPException(
                502, "Text recognition for this image-based deck is unavailable. Please retry."
            ) from None
        except DeckParseError as exc:
            raise HTTPException(422, str(exc)) from exc

    # --- Synchronous analysis: one request, one report. Used by scripts and API clients. ---

    @app.post(
        "/v1/analyze",
        response_model=Report,
        dependencies=[Depends(authenticate), Depends(rate_limit)],
    )
    async def analyze(
        request: Request,
        file: Annotated[UploadFile, File(description="Pitch deck as a PDF")],
        format: Literal["json", "markdown"] = "json",
    ):
        graph = get_graph()
        slides = await parse_upload(file)
        try:
            result = await run_in_threadpool(
                graph.invoke,
                {"slides": slides},
                {"max_concurrency": settings.scoring_concurrency},
            )
        except LLMError:
            log.exception("model failure request_id=%s", request.state.request_id)
            raise HTTPException(502, "Upstream model error. Please retry.") from None

        report = build_report(result)
        if format == "markdown":
            return PlainTextResponse(render_markdown(report), media_type="text/markdown")
        return report

    # --- Background jobs: what the web app uses. Reports are saved per browser. ---

    @app.post(
        "/v1/jobs",
        status_code=202,
        dependencies=[Depends(authenticate), Depends(rate_limit)],
    )
    async def create_job(
        file: Annotated[UploadFile, File(description="Pitch deck as a PDF")],
        who: str = Owner,
    ) -> dict[str, str]:
        graph = get_graph()
        slides = await parse_upload(file)
        get_store()
        job_id = state["runner"].submit(graph, who, file.filename or "deck.pdf", slides)  # type: ignore[attr-defined]
        return {"id": job_id, "status": "queued"}

    @app.get("/v1/jobs", dependencies=[Depends(authenticate)])
    def list_jobs(who: str = Owner) -> list[dict]:
        return get_store().list(who)

    @app.get("/v1/jobs/{job_id}", dependencies=[Depends(authenticate)])
    def get_job(job_id: str, who: str = Owner) -> dict:
        row = get_store().get(job_id, who)
        if row is None:
            raise HTTPException(404, "Report not found.")
        report = row.pop("report")
        return {**row, "report": Report.model_validate_json(report) if report else None}

    @app.delete("/v1/jobs/{job_id}", status_code=204, dependencies=[Depends(authenticate)])
    def delete_job(job_id: str, who: str = Owner) -> Response:
        if not get_store().delete(job_id, who):
            raise HTTPException(404, "Report not found.")
        return Response(status_code=204)

    @app.get("/v1/rubric")
    def rubric() -> dict:
        """The scoring rubric, so the methodology page shows exactly what the code uses."""
        weights = {
            stage: {s.value: w for s, w in ws.items()} for stage, ws in STAGE_WEIGHTS.items()
        }
        weights["other"] = {s.value: w for s, w in _DEFAULT.items()}
        return {
            "sections": [
                {
                    "name": section.value,
                    "criteria": [{"name": n, "description": d} for n, d in crit.items()],
                }
                for section, crit in CRITERIA.items()
            ],
            "weights_by_stage": weights,
            "weak_threshold": WEAK_THRESHOLD,
        }

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> Response:
        request_id = getattr(request.state, "request_id", "-")
        log.exception("unhandled error request_id=%s", request_id)
        return _security_headers(
            PlainTextResponse("Internal server error.", status_code=500), request_id
        )

    if settings.frontend_dir and Path(settings.frontend_dir).is_dir():
        # Mounted last so the API routes above take precedence.
        app.mount("/", SPAStaticFiles(directory=settings.frontend_dir, html=True), name="web")

    return app


app = create_app()  # ASGI entry point: uvicorn autopitch.api:app
