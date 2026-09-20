"""HTTP API.

Trust boundaries handled here: the uploaded file (size, type and page limits, never written
to disk), the caller (optional API key, rate limit), and model failures (logged in full,
reported to the client without internals).
"""

from __future__ import annotations

import hmac
import logging
import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse, Response

from autopitch.config import Settings, get_settings
from autopitch.llm import LLMError
from autopitch.parsing import DeckParseError, read_slides
from autopitch.ratelimit import RateLimiter
from autopitch.report import Report, build_report, render_markdown
from autopitch.tracing import configure_tracing

log = logging.getLogger("autopitch.api")

_PDF_MAGIC = b"%PDF-"
_CHUNK = 1024 * 1024


def _default_graph_factory(settings: Settings):
    from autopitch.factory import build_embedder, build_gemini, build_llama, build_store
    from autopitch.graph import build_graph

    if not settings.gemini_api_key or not settings.llama_api_key:
        return None
    embedder = store = None
    if settings.pinecone_api_key:
        embedder, store = build_embedder(settings), build_store(settings)
    return build_graph(build_gemini(settings), build_llama(settings), embedder, store)


def create_app(
    settings: Settings | None = None,
    graph_factory: Callable[[Settings], object] = _default_graph_factory,
) -> FastAPI:
    settings = settings or get_settings()
    if configure_tracing(settings):
        log.info("LangSmith tracing enabled, project=%s", settings.langsmith_project)
    app = FastAPI(title="AutoPitch", version="0.1.0")
    limiter = RateLimiter(settings.rate_limit_per_minute)
    state: dict[str, object] = {}

    def get_graph():
        if "graph" not in state:
            state["graph"] = graph_factory(settings)
        if state["graph"] is None:
            raise HTTPException(503, "Service is not configured with model credentials.")
        return state["graph"]

    def authenticate(x_api_key: Annotated[str | None, Header()] = None) -> None:
        if settings.api_key and not (
            x_api_key and hmac.compare_digest(x_api_key.encode(), settings.api_key.encode())
        ):
            raise HTTPException(401, "Missing or invalid API key.")

    def rate_limit(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        retry_after = limiter.check(client)
        if retry_after:
            raise HTTPException(
                429, "Rate limit exceeded.", headers={"Retry-After": str(int(retry_after) + 1)}
            )

    @app.middleware("http")
    async def harden(request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

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

    @app.post(
        "/v1/analyze",
        response_model=Report,
        dependencies=[Depends(authenticate), Depends(rate_limit)],
    )
    async def analyze(
        request: Request,
        file: Annotated[UploadFile, File(description="Pitch deck as a PDF")],
        format: str = "json",
    ):
        graph = get_graph()
        data = await read_upload(file)
        try:
            slides = read_slides(data, max_pages=settings.max_pages)
        except DeckParseError as exc:
            raise HTTPException(422, str(exc)) from exc

        try:
            result = await run_in_threadpool(graph.invoke, {"slides": slides})
        except LLMError:
            log.exception("model failure request_id=%s", request.state.request_id)
            raise HTTPException(502, "Upstream model error. Please retry.") from None

        report = build_report(result)
        if format == "markdown":
            return PlainTextResponse(render_markdown(report), media_type="text/markdown")
        return report

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> Response:
        log.exception("unhandled error request_id=%s", getattr(request.state, "request_id", "-"))
        return PlainTextResponse("Internal server error.", status_code=500)

    return app


app = create_app()  # ASGI entry point: uvicorn autopitch.api:app
