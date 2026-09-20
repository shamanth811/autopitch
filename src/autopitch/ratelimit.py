"""Sliding-window rate limiter.

In-process only: with several workers or replicas each keeps its own counters, so put a
shared limiter (gateway, Redis) in front for real multi-instance deployments.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0, clock=time.monotonic) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._calls = 0

    def check(self, key: str) -> float:
        """Record a request. Returns 0 if allowed, else seconds until a slot frees up."""
        now = self._clock()
        with self._lock:
            self._calls += 1
            if self._calls % 500 == 0:
                self._sweep(now)
            hits = self._hits[key]
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                return self._window - (now - hits[0])
            hits.append(now)
            return 0.0

    def _sweep(self, now: float) -> None:
        """Drop clients whose newest hit has left the window, so memory stays bounded."""
        stale = [k for k, h in self._hits.items() if not h or now - h[-1] >= self._window]
        for k in stale:
            del self._hits[k]
