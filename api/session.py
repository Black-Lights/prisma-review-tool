"""Pipeline session manager — runs pipeline steps in a background thread."""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Literal

from prisma_review.config import Config
from prisma_review.models import load_papers, save_papers
from prisma_review.search.runner import run_all_searches
from prisma_review.dedup import deduplicate, save_dedup_log
from prisma_review.screen import screen_by_rules, get_by_decision
from prisma_review.diagram import load_state, save_state


PipelineStatus = Literal["idle", "running", "completed", "failed", "cancelled"]

STEP_LABELS = {
    "search": "Searching databases",
    "dedup": "Removing duplicates",
    "screen": "Keyword screening",
}


class SessionManager:
    """Manages a single background pipeline execution.

    Thread-safe: the ``_lock`` protects mutable progress fields while the
    ``_file_lock`` (shared with the rest of the API) protects JSON writes.
    """

    def __init__(self, file_lock: threading.Lock) -> None:
        self._lock = threading.Lock()
        self._file_lock = file_lock
        self._thread: threading.Thread | None = None

        # Progress state (read by the polling endpoint)
        self.session_id: str | None = None
        self.status: PipelineStatus = "idle"
        self.current_step: str | None = None
        self.progress_message: str | None = None
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.error: str | None = None
        self.result: dict | None = None

        # Cancellation flag — checked between steps
        self._cancel_requested = False

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    def get_progress(self) -> dict:
        """Return a snapshot of the current progress — fast, no I/O."""
        with self._lock:
            return {
                "session_id": self.session_id,
                "status": self.status,
                "current_step": self.current_step,
                "progress_message": self.progress_message,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "error": self.error,
                "result": self.result,
            }

    def request_cancel(self) -> bool:
        """Set the cancellation flag.  Returns False if nothing is running."""
        with self._lock:
            if self.status != "running":
                return False
            self._cancel_requested = True
            self.progress_message = "Cancellation requested — stopping after current step..."
            return True

    # ------------------------------------------------------------------
    # Start helpers
    # ------------------------------------------------------------------

    def start_full_pipeline(self, config: Config) -> str:
        """Launch search -> dedup -> screen in a background thread."""
        return self._start(["search", "dedup", "screen"], config)

    def start_step(self, step: str, config: Config) -> str:
        """Launch a single step in a background thread."""
        if step not in ("search", "dedup", "screen"):
            raise ValueError(f"Unknown step: {step}")
        return self._start([step], config)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start(self, steps: list[str], config: Config) -> str:
        with self._lock:
            if self.status == "running":
                raise RuntimeError("Pipeline is already running")

            self.session_id = uuid.uuid4().hex[:12]
            self.status = "running"
            self.current_step = None
            self.progress_message = "Initializing..."
            self.started_at = datetime.now(timezone.utc).isoformat()
            self.finished_at = None
            self.error = None
            self.result = None
            self._cancel_requested = False

        thread = threading.Thread(
            target=self._run_pipeline,
            args=(steps, config),
            daemon=True,
        )
        thread.start()
        self._thread = thread
        return self.session_id

    def _update(self, **fields: object) -> None:
        with self._lock:
            for k, v in fields.items():
                setattr(self, k, v)

    def _is_cancelled(self) -> bool:
        with self._lock:
            return self._cancel_requested

    # ------------------------------------------------------------------
    # Pipeline execution (runs in background thread)
    # ------------------------------------------------------------------

    def _run_pipeline(self, steps: list[str], config: Config) -> None:
        accumulated: dict = {}
        try:
            for step in steps:
                if self._is_cancelled():
                    self._update(
                        status="cancelled",
                        progress_message="Pipeline cancelled by user",
                        finished_at=datetime.now(timezone.utc).isoformat(),
                    )
                    return

                label = STEP_LABELS.get(step, step)
                self._update(current_step=step, progress_message=f"{label}...")

                result = self._execute_step(step, config)
                accumulated[step] = result

            self._update(
                status="completed",
                current_step=None,
                progress_message="Pipeline completed successfully",
                finished_at=datetime.now(timezone.utc).isoformat(),
                result=accumulated,
            )

        except Exception as exc:
            self._update(
                status="failed",
                progress_message=f"Error in step '{self.current_step}': {exc}",
                error=traceback.format_exc(),
                finished_at=datetime.now(timezone.utc).isoformat(),
            )

    def _execute_step(self, step: str, config: Config) -> dict:
        """Execute a single pipeline step.  Returns its result dict."""
        if step == "search":
            return self._run_search(config)
        elif step == "dedup":
            return self._run_dedup(config)
        elif step == "screen":
            return self._run_screen(config)
        else:
            raise ValueError(f"Unknown step: {step}")

    # -- Individual step implementations (mirror the sync endpoints) ------

    def _run_search(self, config: Config) -> dict:
        with self._file_lock:
            results = run_all_searches(config)

            all_papers = []
            source_counts: dict[str, int] = {}
            for key, papers in results.items():
                source_name = key.split("_")[0]
                source_counts[source_name] = source_counts.get(source_name, 0) + len(papers)
                all_papers.extend(papers)

            save_papers(all_papers, config.search_dir / "all_records.json")

            state = load_state(config.state_file)
            state["search"] = {**source_counts, "total": len(all_papers)}
            save_state(state, config.state_file)

        self._update(progress_message=f"Search complete — {len(all_papers)} records found")
        return {"status": "ok", "total": len(all_papers), "sources": source_counts}

    def _run_dedup(self, config: Config) -> dict:
        papers = load_papers(config.search_dir / "all_records.json")
        if not papers:
            raise RuntimeError("No papers found. Run search first.")

        with self._file_lock:
            unique, log = deduplicate(papers, config.doi_match, config.fuzzy_threshold)
            save_papers(unique, config.dedup_dir / "deduplicated.json")
            save_dedup_log(log, config.dedup_dir / "duplicates_log.csv")

            state = load_state(config.state_file)
            state["dedup"] = {"duplicates_removed": len(papers) - len(unique), "remaining": len(unique)}
            save_state(state, config.state_file)

        self._update(progress_message=f"Dedup complete — {len(unique)} unique records")
        return {"status": "ok", "duplicates_removed": len(papers) - len(unique), "remaining": len(unique)}

    def _run_screen(self, config: Config) -> dict:
        papers = load_papers(config.dedup_dir / "deduplicated.json")
        if not papers:
            raise RuntimeError("No papers found. Run dedup first.")

        with self._file_lock:
            papers = screen_by_rules(papers, config.include_keywords, config.exclude_keywords, config.min_include_hits)
            included = get_by_decision(papers, "include")
            excluded = get_by_decision(papers, "exclude")
            maybe = get_by_decision(papers, "maybe")

            save_papers(papers, config.screen_dir / "screen_results.json")
            save_papers(included, config.screen_dir / "included.json")
            save_papers(excluded, config.screen_dir / "excluded.json")
            save_papers(maybe, config.screen_dir / "maybe.json")

            state = load_state(config.state_file)
            state["screen"] = {
                "total_screened": len(papers),
                "included": len(included),
                "excluded": len(excluded),
                "maybe": len(maybe),
            }
            save_state(state, config.state_file)

        self._update(progress_message=f"Screening complete — {len(included)} included")
        return {"status": "ok", "included": len(included), "excluded": len(excluded), "maybe": len(maybe)}
