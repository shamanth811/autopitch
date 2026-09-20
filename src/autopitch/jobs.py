"""Runs analyses in the background so a request never waits on six model calls.

The graph is streamed, and the stage written to the store after each step is what the UI
polls to show real progress.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from autopitch.llm import LLMError
from autopitch.report import build_report
from autopitch.schema import Slide
from autopitch.storage import JobStore

log = logging.getLogger("autopitch.jobs")

STAGES = ("extract", "score", "benchmark", "objections")


def stage_of(state: dict) -> str:
    """Which step is about to run, judged from what the graph state already holds."""
    if "objections" in state:
        return "done"
    if "benchmark" in state:
        return "objections"
    if "composite" in state:
        return "benchmark"
    if "deck" in state:
        return "score"
    return "extract"


class JobRunner:
    def __init__(self, store: JobStore, max_workers: int, max_concurrency: int) -> None:
        self._store = store
        self._max_concurrency = max_concurrency
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")

    def submit(self, graph, owner: str, filename: str, slides: list[Slide]) -> str:
        job_id = self._store.create(owner, filename)
        self._pool.submit(self._run, graph, job_id, slides)
        return job_id

    def _run(self, graph, job_id: str, slides: list[Slide]) -> None:
        try:
            state: dict = {}
            config = {"max_concurrency": self._max_concurrency}
            for state in graph.stream({"slides": slides}, config, stream_mode="values"):
                stage = stage_of(state)
                if stage != "done":
                    self._store.set_stage(job_id, stage)
            report = build_report(state)
            self._store.complete(
                job_id, report.model_dump_json(), report.deck.company, report.composite.score
            )
        except LLMError:
            log.exception("model failure job=%s", job_id)
            self._store.fail(job_id, "Upstream model error. Please try again in a minute.")
        except Exception:
            log.exception("analysis failed job=%s", job_id)
            self._store.fail(job_id, "The analysis failed. Please try again.")

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
