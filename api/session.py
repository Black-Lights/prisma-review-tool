"""Pipeline session manager: runs pipeline steps in a background thread.

The web API and the MCP server each have one manager. A run is also recorded
on disk (the ``pipeline`` block of review_state.json, see prisma_review.pipeline)
with its owner process and a heartbeat, so either process can show, refuse to
duplicate, or stop a run the other one started, and a run whose process died
is reported as interrupted instead of "running" forever.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Literal

from prisma_review import pipeline, workspace
from prisma_review.config import Config
from prisma_review.pipeline import RunActiveError
from prisma_review.screen import rescreen
from prisma_review.storage import update_state

PipelineStatus = Literal["idle", "running", "completed", "failed", "cancelled"]

STEP_LABELS = {
    "search": "Searching databases",
    "dedup": "Removing duplicates",
    "screen": "Keyword screening",
}

# Keys of a progress snapshot (the in-memory run, or the block on disk).
_PROGRESS_KEYS = ("session_id", "status", "current_step", "progress_message", "started_at",
                  "finished_at", "completed_steps", "warnings", "error", "result",
                  "cancel_requested")

log = logging.getLogger(__name__)


def _idle_progress() -> dict:
    return {"session_id": None, "status": "idle", "current_step": None, "progress_message": None,
            "started_at": None, "finished_at": None, "completed_steps": [], "warnings": [],
            "error": None, "result": None, "cancel_requested": False}


def _progress_from_block(block: dict) -> dict:
    progress = _idle_progress()
    for key in _PROGRESS_KEYS:
        if key in block:
            progress[key] = block[key]
    progress["completed_steps"] = list(progress["completed_steps"] or [])
    progress["warnings"] = list(progress["warnings"] or [])
    progress["cancel_requested"] = bool(progress["cancel_requested"])
    return progress


def _same_file(a: Path | None, b: Path | None) -> bool:
    if a is None or b is None:
        return a is b
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))


class SessionManager:
    """Manages the pipeline runs this process starts.

    ``_lock`` protects the in-memory progress fields; every file write goes
    through ``storage.project_lock`` / ``update_state``, which also exclude
    the other process.
    """

    def __init__(self, file_lock: object | None = None, state_file: Path | None = None) -> None:
        # ``file_lock`` is accepted for compatibility and unused: the project
        # lock in prisma_review.storage replaced the per-process locks.
        self._lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._state_file = Path(state_file) if state_file is not None else None
        self._thread: threading.Thread | None = None
        self._heartbeat_stop = threading.Event()
        self.run_config: Config | None = None

        # Progress of the last run this process started (read by the polling endpoint)
        self.session_id: str | None = None
        self.status: PipelineStatus = "idle"
        self.current_step: str | None = None
        self.progress_message: str | None = None
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.completed_steps: list[str] = []
        self.warnings: list[str] = []
        self.error: str | None = None
        self.result: dict | None = None

        # Cancellation flag: checked between steps and by the search runner
        self._cancel_requested = False

        # A run left "running" by a process that died is recorded as interrupted.
        if self._state_file is not None:
            try:
                pipeline.reconcile_stale_run(self._state_file)
            except Exception:
                log.warning("Failed to check the recorded pipeline run", exc_info=True)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """True while this process runs a pipeline (see ``pipeline.active_run`` for any process)."""
        return self.status == "running"

    @property
    def state_file(self) -> Path | None:
        return self._state_file

    def _snapshot(self) -> dict:
        with self._lock:
            return {
                "session_id": self.session_id,
                "status": self.status,
                "current_step": self.current_step,
                "progress_message": self.progress_message,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "completed_steps": list(self.completed_steps),
                "warnings": list(self.warnings),
                "error": self.error,
                "result": self.result,
                "cancel_requested": self._cancel_requested,
            }

    def get_progress(self, state_file: Path | None = None) -> dict:
        """Return a snapshot of the pipeline progress of a project (default: this manager's).

        Reconciles this process's run with the ``pipeline`` block on disk, so
        a run driven by the other process (web API or MCP server) is visible
        here too. Memory wins for this process's own run (it has the result);
        a recorded run whose owner died is reported as failed; another
        project's progress never shows this process's run.
        """
        target = Path(state_file) if state_file is not None else self._state_file
        ours = target is None or _same_file(target, self._state_file)
        local = self._snapshot()
        if ours and local["status"] == "running":
            return local

        disk = None
        block = pipeline.read_run(target)
        if block is not None:
            if block.get("status") == "running" and not pipeline.run_is_live(block):
                block = pipeline.reconcile_stale_run(target) or pipeline.interrupted(block)
            disk = _progress_from_block(block)

        if not ours:
            return disk or _idle_progress()
        if disk is None:
            return local
        if local["session_id"] and disk["session_id"] == local["session_id"]:
            return local
        if local["started_at"] is None or (disk["started_at"] or "") > local["started_at"]:
            return disk
        return local

    def request_cancel(self, state_file: Path | None = None) -> bool:
        """Ask the running pipeline of a project (default: this manager's) to stop.

        Cancels this process's run directly; otherwise sets ``cancel_requested``
        on disk for the process that owns the run. False if nothing is running.
        """
        target = Path(state_file) if state_file is not None else self._state_file
        with self._lock:
            mine = self.status == "running" and (state_file is None
                                                 or _same_file(target, self._state_file))
            if mine:
                self._cancel_requested = True
                self.progress_message = pipeline.CANCEL_MESSAGE
        if mine:
            self._persist_to_disk()
            return True
        return pipeline.request_cancel_on_disk(target)

    # ------------------------------------------------------------------
    # Start helpers
    # ------------------------------------------------------------------

    def start_full_pipeline(self, config: Config) -> str:
        """Launch search -> dedup -> screen in a background thread."""
        return self._start(list(pipeline.STEPS), config)

    def start_step(self, step: str, config: Config) -> str:
        """Launch a single step in a background thread."""
        if step not in pipeline.STEPS:
            raise ValueError(f"Unknown step: {step}")
        return self._start([step], config)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start(self, steps: list[str], config: Config) -> str:
        """Claim the project on disk and start the run.

        Raises RuntimeError if this process is already running a pipeline and
        RunActiveError if another process runs one on this project.
        """
        with self._start_lock:
            if self.is_running:
                raise RuntimeError("Pipeline is already running")
            if "search" in steps:
                # A search replaces the results under output_dir: refuse up front.
                workspace.check_output_dir(config)

            session_id = uuid.uuid4().hex[:12]
            started_at = pipeline.now_iso()
            block = {
                "session_id": session_id, "status": "running", "current_step": None,
                "progress_message": "Initializing...", "started_at": started_at,
                "finished_at": None, "completed_steps": [], "warnings": [], "error": None,
                "result": None, "cancel_requested": False, **pipeline.owner_fields(),
            }

            def claim(state: dict) -> None:
                current = state.get("pipeline")
                if pipeline.run_is_live(current):
                    raise RunActiveError(pipeline.describe_run(current))
                state["pipeline"] = block

            update_state(config.state_file, claim)

            with self._lock:
                self.session_id = session_id
                self.status = "running"
                self.current_step = None
                self.progress_message = "Initializing..."
                self.started_at = started_at
                self.finished_at = None
                self.completed_steps = []
                self.warnings = []
                self.error = None
                self.result = None
                self._cancel_requested = False
                self._state_file = Path(config.state_file)
                self.run_config = config
                self._heartbeat_stop = threading.Event()

            threading.Thread(target=self._heartbeat, args=(self._heartbeat_stop,),
                             daemon=True).start()
            thread = threading.Thread(target=self._run_pipeline, args=(steps, config), daemon=True)
            self._thread = thread
            thread.start()
            return session_id

    def _update(self, **fields: object) -> None:
        with self._lock:
            for k, v in fields.items():
                setattr(self, k, v)

    def _add_warnings(self, warnings: list[str]) -> None:
        with self._lock:
            self.warnings.extend(warnings)

    def _is_cancelled(self) -> bool:
        with self._lock:
            return self._cancel_requested

    def _disk_block(self) -> dict:
        with self._lock:
            return {
                "session_id": self.session_id,
                "status": self.status,
                "current_step": self.current_step,
                "progress_message": self.progress_message,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "completed_steps": list(self.completed_steps),
                "warnings": list(self.warnings),
                "error": self.error,
                "result": self.result,
                "cancel_requested": self._cancel_requested,
                **pipeline.owner_fields(),
            }

    def _sync(self, block: dict | None = None) -> bool:
        """Write this run's block (or only refresh the heartbeat) and pick up a cancel from disk.

        Never overwrites a live run another process started on the project.
        Returns False if the write failed.
        """
        if self._state_file is None or self.session_id is None:
            return False
        session_id = self.session_id
        seen = {"cancel": False, "superseded": False}

        def apply(state: dict) -> None:
            current = state.get("pipeline")
            if isinstance(current, dict) and current.get("session_id") != session_id:
                if pipeline.run_is_live(current):
                    seen["superseded"] = True
                    return
            elif isinstance(current, dict):
                seen["cancel"] = bool(current.get("cancel_requested"))
                if block is None and current.get("status") == "running":  # heartbeat only
                    current["heartbeat_at"] = pipeline.now_iso()
                    return
            # Write the whole block; this also restores it if another process
            # recorded this run as interrupted while it was in fact still going.
            new_block = block if block is not None else self._disk_block()
            if seen["cancel"]:
                new_block["cancel_requested"] = True
            state["pipeline"] = new_block

        try:
            update_state(self._state_file, apply)
        except Exception:
            log.warning("Failed to persist pipeline state", exc_info=True)
            return False
        if seen["cancel"] or seen["superseded"]:
            with self._lock:
                if not self._cancel_requested and self.status == "running":
                    self._cancel_requested = True
                    self.progress_message = (
                        pipeline.CANCEL_MESSAGE if seen["cancel"] else
                        "Another process started a pipeline on this project; stopping this one")
        return True

    def _persist_to_disk(self, config: Config | None = None) -> bool:
        """Write the current progress to the ``pipeline`` block of review_state.json."""
        return self._sync(self._disk_block())

    def _heartbeat(self, stop: threading.Event) -> None:
        while not stop.wait(pipeline.HEARTBEAT_SECONDS):
            if self.status != "running":
                return
            self._sync()

    def _check_disk_cancel(self) -> None:
        block = pipeline.read_run(self._state_file)
        if isinstance(block, dict) and block.get("session_id") == self.session_id \
                and block.get("cancel_requested"):
            with self._lock:
                self._cancel_requested = True

    def _finish(self, status: PipelineStatus, message: str, **fields: object) -> None:
        self._update(status=status, progress_message=message,
                     finished_at=pipeline.now_iso(), **fields)
        self._heartbeat_stop.set()
        # The final state must reach the disk, or other processes see a stale run.
        for attempt in range(3):
            if self._persist_to_disk():
                return
            time.sleep(0.2 * (attempt + 1))

    # ------------------------------------------------------------------
    # Pipeline execution (runs in background thread)
    # ------------------------------------------------------------------

    def _run_pipeline(self, steps: list[str], config: Config) -> None:
        accumulated: dict = {}
        try:
            for step in steps:
                self._check_disk_cancel()
                if self._is_cancelled():
                    self._finish("cancelled", "Pipeline cancelled by user",
                                 current_step=None, result=accumulated)
                    return

                label = STEP_LABELS.get(step, step)
                self._update(current_step=step, progress_message=f"{label}...")
                self._persist_to_disk()

                result = self._execute_step(step, config)
                accumulated[step] = result
                if isinstance(result, dict) and result.get("status") == "cancelled":
                    self._finish("cancelled", result.get("message") or "Pipeline cancelled by user",
                                 current_step=None, result=accumulated)
                    return

                with self._lock:
                    self.completed_steps.append(step)

            self._finish("completed", "Pipeline completed successfully",
                         current_step=None, result=accumulated)

        except Exception as exc:
            self._finish("failed", f"Error in step '{self.current_step}': {exc}",
                         error=traceback.format_exc())
        finally:
            self._heartbeat_stop.set()

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

    # -- Individual step implementations (shared with the CLI and sync endpoints) --

    def _run_search(self, config: Config) -> dict:
        # Per-source query transparency: report operators each source drops
        # (OR/NOT/wildcards/extra phrases) before the search runs.
        self._add_warnings(pipeline.pre_search_warnings(config))

        # A new search replaces the project's later results, but only once it
        # has finished: a cancelled or failed search keeps the previous ones.
        outcome = pipeline.search_step(config, should_cancel=self._is_cancelled,
                                       replace_downstream=True)
        self._add_warnings(outcome["warnings"])
        if outcome["status"] == "cancelled":
            return {**outcome, "message": "Pipeline cancelled during search; "
                                          "the previous results were kept"}
        if outcome["status"] == "failed":
            raise pipeline.StepError(outcome["error"])

        msg = f"Search complete: {outcome['total']} records found"
        if self.warnings:
            msg += f" ({len(self.warnings)} warning(s))"
        self._update(progress_message=msg)
        return {"status": "ok", "total": outcome["total"], "sources": outcome["sources"]}

    def _run_dedup(self, config: Config) -> dict:
        result = pipeline.dedup_step(config)
        self._update(progress_message=f"Dedup complete: {result['remaining']} unique records")
        return result

    def _run_screen(self, config: Config) -> dict:
        # Keeps manual and AI decisions and reconciles the eligibility pass.
        result = rescreen(config, check_running=False, persist_threshold=False)
        self._update(progress_message=f"Screening complete: {result['included']} included")
        if result["eligibility_set_aside"]:
            self._add_warnings([
                f"{result['eligibility_set_aside']} eligibility decision(s) are set aside because "
                f"their papers are no longer included at screening. They are kept and count "
                f"again if the papers are included again."])
        return {key: result[key] for key in ("status", "included", "excluded", "maybe",
                                             "excluded_no_required_keyword", "kept_manual",
                                             "kept_ai", "eligibility_set_aside")}
