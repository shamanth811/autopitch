"""OCR for image-only pages via Mistral OCR, rotating across several API keys.

Each key has its own monthly allowance, so when one is rate limited or out of quota the
request moves on to the next. A key that failed for a key-specific reason is put on cooldown so
later requests do not waste a call on it.
"""

from __future__ import annotations

import base64
import logging
import threading
import time
from collections.abc import Callable

log = logging.getLogger(__name__)

# Seconds a key is skipped after failing. Quota and rate-limit errors may clear soon (rate limit)
# or not for weeks (monthly quota); an hour is a compromise, and cooling keys are still tried
# as a last resort, so this never makes the client refuse outright.
_COOLDOWN_LIMITED = 300.0
_COOLDOWN_REJECTED = 3600.0
_QUOTA_HINTS = ("quota", "rate limit", "limit exceeded", "insufficient", "too many requests")


class OcrError(Exception):
    """OCR could not be completed. The message is safe to show to a client."""


def _default_client(api_key: str):
    from mistralai.client import Mistral

    return Mistral(api_key=api_key)


def _classify(exc: Exception) -> str:
    """'limited' and 'rejected' are key problems; 'transient' is worth another key;
    'fatal' means the document itself is the problem."""
    status = getattr(exc, "status_code", None)
    text = str(exc).lower()
    if status == 429 or any(h in text for h in _QUOTA_HINTS):
        return "limited"
    if status in (401, 403):
        return "rejected"
    if status is None or status >= 500:  # network trouble or a provider outage
        return "transient"
    return "fatal"


class OcrClient:
    def __init__(
        self,
        api_keys: list[str],
        model: str = "mistral-ocr-latest",
        client_factory: Callable[[str], object] = _default_client,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not api_keys:
            raise ValueError("OcrClient needs at least one API key")
        self._keys = list(api_keys)
        self._model = model
        self._factory = client_factory
        self._clock = clock
        self._clients: dict[int, object] = {}
        self._cooldown_until: dict[int, float] = {}
        self._start = 0  # round-robin: each call begins one key further on
        self._lock = threading.Lock()

    def _order(self) -> list[int]:
        """Keys to try: ready ones first, round-robin from the next start, then cooling ones
        soonest-to-recover first."""
        with self._lock:
            start = self._start
            self._start = (self._start + 1) % len(self._keys)
        now = self._clock()
        rotated = [(start + i) % len(self._keys) for i in range(len(self._keys))]
        ready = [i for i in rotated if self._cooldown_until.get(i, 0) <= now]
        cooling = sorted(
            (i for i in rotated if i not in ready), key=lambda i: self._cooldown_until[i]
        )
        return ready + cooling

    def _client(self, index: int):
        if index not in self._clients:
            self._clients[index] = self._factory(self._keys[index])
        return self._clients[index]

    def ocr_pdf(self, pdf: bytes) -> list[str]:
        """Markdown for each page of `pdf`, in page order."""
        url = "data:application/pdf;base64," + base64.b64encode(pdf).decode()
        failures: list[str] = []
        for index in self._order():
            label = f"key {index + 1}"  # never log the key itself
            try:
                resp = self._client(index).ocr.process(
                    model=self._model, document={"type": "document_url", "document_url": url}
                )
            except Exception as exc:
                kind = _classify(exc)
                log.warning("Mistral OCR %s failed (%s): %s", label, kind, type(exc).__name__)
                failures.append(f"{label}: {kind}")
                if kind == "fatal":
                    raise OcrError("The document could not be read by the OCR service.") from exc
                if kind in ("limited", "rejected"):
                    cooldown = _COOLDOWN_LIMITED if kind == "limited" else _COOLDOWN_REJECTED
                    self._cooldown_until[index] = self._clock() + cooldown
                continue
            pages = sorted(resp.pages, key=lambda p: p.index)
            return [p.markdown or "" for p in pages]
        raise OcrError("The OCR service is unavailable or over its limit. " + "; ".join(failures))
